"""
Voice MCP Server - Speech-to-text and text-to-speech.
Uses Whisper (tiny) for transcription (lazy loading) and Edge-TTS for synthesis.
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
import io
import logging
import random
import re
import tempfile
import os
import edge_tts

logger = logging.getLogger(__name__)


# Tool Input Schemas (Pydantic models)
class TranscribeAudioInput(BaseModel):
    """Input schema for transcribe_audio tool."""

    audio_b64: str = Field(..., description="Base64 encoded audio data")


class SynthesizeSpeechInput(BaseModel):
    """Input schema for synthesize_speech tool."""

    text: str = Field(..., description="Text to synthesize into speech")
    voice: str = Field("en-US-AriaNeural", description="Edge-TTS voice ID")
    output_path: Optional[str] = Field(
        None, description="Path where to save audio file"
    )
    rate: Optional[str] = Field(
        None,
        description=(
            "Edge-TTS rate override, e.g. '+5%'. If not provided, a small "
            "natural jitter is applied so cadence isn't perfectly uniform "
            "turn-to-turn."
        ),
    )


class DetectSilenceInput(BaseModel):
    """Input schema for detect_silence tool."""

    audio_file_path: str = Field(..., description="Path to the audio file to analyze")
    threshold_db: float = Field(-40.0, description="Silence threshold in dB")
    min_silence_duration: float = Field(
        0.5, description="Minimum silence duration in seconds"
    )


_APOSTROPHE_RE = re.compile(r"['’]")  # straight and curly apostrophes
_PUNCT_RE = re.compile(r"[^\w\s]")


def normalize_transcript(text: str) -> str:
    """
    Lowercase, strip ALL punctuation (not just leading/trailing), and collapse
    whitespace. Fixes a live-confirmed bug where `.strip(".,!? ")` only
    trimmed the ends of the string, so "Thank you. Thank you." tokenized as
    4 distinct words (["thank", "you.", "thank", "you"]) instead of being
    recognized as "thank you" repeated. All phrase-matching below is done
    against this normalized form.

    Apostrophes are removed WITHOUT inserting a space (contractions collapse
    into one word: "I'm" -> "im", "let's" -> "lets") -- otherwise a naive
    "replace all punctuation with a space" pass splits contractions into
    separate letter tokens ("i m", "let s"), which was confirmed live to
    make "I'm going to go to the next slide." and "So, let's go." miss the
    phrase list entirely.
    """
    if not text:
        return ""
    no_apostrophes = _APOSTROPHE_RE.sub("", text.lower())
    no_punct = _PUNCT_RE.sub(" ", no_apostrophes)
    return " ".join(no_punct.split())


# Phrases that are near-certainly NEVER a genuine interview answer on their
# own -- classic Whisper video-outro / presentation-style hallucinations,
# plus a few bare connective fragments carried over from the original list.
# Deliberately EXCLUDES "yes"/"no" and punctuated variants -- those are
# legitimate short answers to yes/no interview questions and must never be
# blanket-filtered (the old main.py echo_phrases set had this bug). Entries
# are written in normalized form (no punctuation) since they're compared
# against normalize_transcript() output.
HALLUCINATION_PHRASES = {
    # video outro / subscribe boilerplate (Whisper is trained partly on
    # YouTube subtitles and hallucinates these on silence)
    "thank you",
    "thanks",
    "thank you for watching",
    "thanks for watching",
    "thank you very much",
    "please subscribe",
    "subscribe",
    "like and subscribe",
    "please like and subscribe",
    "dont forget to subscribe",
    "see you next time",
    "see you in the next video",
    "bye",
    "goodbye",
    "music",
    # presentation / screen-share hallucinations (live-confirmed misses)
    "next slide",
    "go to the next slide",
    "im going to go to the next slide",
    "moving on to the next slide",
    "lets go",
    "okay lets go",
    "so lets go",
    # bare acknowledgements / connective fragments -- only meaningful when
    # they are the ENTIRE utterance for a complete recorded blob, which is
    # far more likely a stray fragment than a real answer
    "okay",
    "you",
    "so",
    "the",
    "i",
    "a",
    "and",
    "is it",
    "what is it",
    "on behalf of me",
    "what is it on behalf of me",
}

# Filler-only tokens: genuinely ambiguous (real mid-answer hesitation vs.
# pure hallucination filler on near-silence). NOT blanket-filtered by phrase
# match alone -- only dropped when a low-confidence corroborating signal is
# also present, or when no signal is available at all (conservative default,
# matches this filter's pre-existing behavior). See is_hallucinated_transcript().
FILLER_ONLY_PHRASES = {"um", "uh", "umm", "uhh"}

# Corroborating-signal thresholds for the filler/repetition checks below.
# FILLER_NO_SPEECH_THRESHOLD (0.4) is deliberately lower than the 0.7
# whole-clip-silence bar used elsewhere, since it only has to corroborate an
# ALREADY-ambiguous filler-only transcript, not stand alone. AVG_LOGPROB/
# COMPRESSION_RATIO thresholds reuse OpenAI's own Whisper CLI defaults as a
# starting point -- provisional pending confirmation of what Groq's API
# actually populates (see _extract_segment_metrics).
FILLER_NO_SPEECH_THRESHOLD = 0.4
AVG_LOGPROB_THRESHOLD = -1.0
COMPRESSION_RATIO_THRESHOLD = 2.4
COMPRESSION_RATIO_MAX_WORDS = (
    12  # only apply to short clips, to avoid false positives on long legitimate answers
)


def _find_repeated_phrase(words: List[str]) -> Optional[str]:
    """
    Detect whether `words` is entirely composed of a short (1-4 word)
    sub-phrase repeated verbatim 2+ times, e.g.
    ["thank", "you", "thank", "you"] -> "thank you". Returns the repeated
    sub-phrase (joined) or None. Combined with normalize_transcript(), this
    catches punctuated repeats like "Thank you. Thank you." that a
    single-token-only repetition check would miss.
    """
    n = len(words)
    if n < 2:
        return None
    for k in range(1, min(4, n // 2) + 1):
        if n % k != 0:
            continue
        pattern = words[:k]
        if pattern * (n // k) == words:
            return " ".join(pattern)
    return None


_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


def _all_sentences_are_hallucinations(text: str) -> bool:
    """
    Live-confirmed gap: Whisper can concatenate multiple DIFFERENT
    hallucination fragments into one longer sentence, e.g. "I'm going to go
    to the next slide. Thank you. Thank you." -- the combined normalized
    string ("im going to go to the next slide thank you thank you") doesn't
    exact-match any single HALLUCINATION_PHRASES entry, and isn't a clean
    periodic repetition either, so neither check #1 nor #2 catches it.

    Splits on sentence-ending punctuation BEFORE normalization (normalizing
    first would destroy the sentence boundaries), normalizes each piece
    separately, and returns True only if there are at least TWO non-empty
    sentences and EVERY one of them individually matches a known
    hallucination/filler phrase. Requiring 2+ sentences means a lone filler
    word ("um") is NOT caught here -- it falls through to the dedicated
    filler-corroboration check instead, which is deliberately more
    conservative (needs a corroborating confidence signal) than this
    concatenation check. A transcript with even one sentence that isn't on
    the list is left alone, so this can't over-filter a real multi-sentence
    answer that happens to include an actual "thank you".
    """
    pieces = [normalize_transcript(p) for p in _SENTENCE_SPLIT_RE.split(text)]
    sentences = [p for p in pieces if p]
    if len(sentences) < 2:
        return False
    known = HALLUCINATION_PHRASES | FILLER_ONLY_PHRASES
    return all(s in known for s in sentences)


def is_hallucinated_transcript(
    text: str,
    avg_no_speech_prob: Optional[float] = None,
    avg_logprob: Optional[float] = None,
    compression_ratio: Optional[float] = None,
) -> bool:
    """
    Pure decision function: should `text` (raw Whisper output for one audio
    chunk) be treated as a hallucination/echo rather than a real candidate
    answer? Side-effect free (no network, no logging, no I/O) so it is
    directly unit-testable -- see test_voice_hallucination_filter.py.
    """
    normalized = normalize_transcript(text)
    if not normalized:
        return True

    words = normalized.split()

    # 1. Exact match against phrases that are never a genuine answer alone.
    if normalized in HALLUCINATION_PHRASES:
        return True

    # 2. Repeated short sub-phrase, e.g. "thank you thank you".
    if _find_repeated_phrase(words) is not None:
        return True

    # 2.5. Multiple concatenated hallucination fragments, e.g. "I'm going to
    #      go to the next slide. Thank you. Thank you." -- each sentence is
    #      individually a known phrase even though the combined string isn't.
    if _all_sentences_are_hallucinations(text):
        return True

    # 3. Filler-only utterance -- ambiguous alone, filtered only when
    #    corroborated by a low-confidence signal (or when no signal is
    #    available at all, preserving this filter's existing conservative
    #    behavior).
    if normalized in FILLER_ONLY_PHRASES:
        no_signal_available = avg_no_speech_prob is None and avg_logprob is None
        low_confidence = (
            avg_no_speech_prob is not None
            and avg_no_speech_prob > FILLER_NO_SPEECH_THRESHOLD
        ) or (avg_logprob is not None and avg_logprob < AVG_LOGPROB_THRESHOLD)
        return no_signal_available or low_confidence

    # 4. Abnormally repetitive/low-entropy text for its length -- OpenAI's
    #    own Whisper CLI heuristic for hallucinated loops that aren't exact
    #    verbatim repeats. Capped to short clips to limit false positives on
    #    long legitimate answers with naturally repetitive phrasing.
    if (
        compression_ratio is not None
        and compression_ratio > COMPRESSION_RATIO_THRESHOLD
        and len(words) <= COMPRESSION_RATIO_MAX_WORDS
    ):
        return True

    return False


def _extract_segment_metrics(segments) -> Dict[str, Optional[float]]:
    """
    Defensively extract average no_speech_prob / avg_logprob and max
    compression_ratio across verbose_json segments. Groq's SDK only strongly
    types `text` on Transcription -- segments and their fields are untyped,
    so every access must tolerate dict-or-attribute segments AND a field
    being entirely absent (unconfirmed whether Groq's API populates
    avg_logprob/compression_ratio at all). Returns None per metric rather
    than a numeric default, so callers never silently bias filtering
    decisions off a fabricated value.
    """
    if not segments:
        return {"no_speech_prob": None, "avg_logprob": None, "compression_ratio": None}

    def _get(seg, field):
        return seg.get(field) if isinstance(seg, dict) else getattr(seg, field, None)

    def _avg(field):
        vals = [v for v in (_get(s, field) for s in segments) if v is not None]
        return (sum(vals) / len(vals)) if vals else None

    compression_vals = [
        v for v in (_get(s, "compression_ratio") for s in segments) if v is not None
    ]

    return {
        "no_speech_prob": _avg("no_speech_prob"),
        "avg_logprob": _avg("avg_logprob"),
        "compression_ratio": max(compression_vals) if compression_vals else None,
    }


def _is_silent_dbfs(dbfs: float, threshold_db: float = -40.0) -> bool:
    """Pure threshold check, factored out so it's testable without pydub/ffmpeg."""
    return dbfs < threshold_db  # dBFS is float('-inf') for pure digital silence


def is_near_silent_audio(
    audio_bytes: bytes, silence_threshold_db: float = -40.0, audio_format: str = "webm"
) -> Optional[bool]:
    """
    Lightweight RMS-loudness precheck using pydub/ffmpeg (already a project
    dependency -- see Dockerfile's ffmpeg install) run BEFORE the Groq API
    call, so near-silent/ambient chunks never hit the network at all. This
    saves latency + API cost and catches hallucination-prone clips
    independent of guessing Whisper's hallucination vocabulary.

    Returns True if near-silent, False if it has meaningful energy, or None
    if the audio could not be decoded -- callers MUST fail OPEN on None
    (proceed to Groq) so a decode hiccup never silently drops a real answer.
    """
    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(io.BytesIO(audio_bytes), format=audio_format)
        return _is_silent_dbfs(audio.dBFS, silence_threshold_db)
    except Exception as e:
        logger.debug(f"is_near_silent_audio: decode failed, failing open: {e}")
        return None


class VoiceMCPServer:
    """
    Voice processing MCP server.
    Provides tools for TTS, STT and VAD operations.
    """

    def __init__(self):
        self.name = "voice-mcp-server"
        self.version = "1.0.0"
        self.tools = {
            "transcribe_audio": self.transcribe_audio,
            "synthesize_speech": self.synthesize_speech,
            "detect_silence": self.detect_silence,
        }

    def transcribe_audio(self, input_data: TranscribeAudioInput) -> Dict[str, Any]:
        """
        Transcribe audio using Groq cloud STT.
        Eliminates local Whisper/Torch dependencies to save disk/RAM.
        """
        try:
            import base64

            audio_bytes = base64.b64decode(input_data.audio_b64)

            # Delegate to the Groq implementation
            return self.transcribe_audio_groq(audio_bytes)

        except Exception as e:
            logger.error(f"Error in transcribe_audio: {e}")
            return {"success": False, "error": str(e)}

    def transcribe_audio_groq(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Transcribe audio using Groq's cloud Whisper API.
        Priya's recommendation: server-side STT is the only reliable path.
        """
        try:
            from config import settings

            # Audio-energy precheck: skip the Groq call entirely for
            # near-silent/ambient chunks. Feature-flagged so it can be
            # disabled in prod without a code change if it ever proves too
            # aggressive. Fails open (proceeds to Groq) on decode errors.
            if getattr(settings, "enable_audio_energy_precheck", True):
                if is_near_silent_audio(audio_bytes) is True:
                    logger.debug(
                        "Audio-energy precheck: near-silent clip, skipping Groq call"
                    )
                    return {"success": True, "text": ""}

            from groq import Groq

            client = Groq(api_key=settings.groq_api_key)

            # Save audio bytes to temp file (Groq API needs a file-like object)
            with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp.flush()
                tmp_path = tmp.name

            try:
                with open(tmp_path, "rb") as audio_file:
                    transcription = client.audio.transcriptions.create(
                        file=("audio.webm", audio_file),
                        model="whisper-large-v3-turbo",
                        language="en",
                        response_format="verbose_json",
                        # Whisper hallucination prevention:
                        # - prompt guides the model to expect interview answers
                        # - temperature=0 reduces randomness/hallucination
                        prompt="The candidate is answering technical interview questions about software engineering.",
                        temperature=0.0,
                        timeout=30.0,  # don't let a hung upstream call tie up the worker indefinitely
                    )

                # With verbose_json, we get segments with no_speech_prob
                if hasattr(transcription, "text"):
                    text = transcription.text.strip()
                else:
                    text = str(transcription).strip()

                metrics = _extract_segment_metrics(
                    getattr(transcription, "segments", None)
                )

                # Whole-clip silence gate (unchanged threshold/logic).
                if (
                    metrics["no_speech_prob"] is not None
                    and metrics["no_speech_prob"] > 0.7
                ):
                    logger.debug(
                        f"Groq Whisper detected silence (no_speech_prob="
                        f"{metrics['no_speech_prob']:.2f}): '{text}'"
                    )
                    return {"success": True, "text": ""}  # Return empty, it's silence

                if is_hallucinated_transcript(
                    text,
                    avg_no_speech_prob=metrics["no_speech_prob"],
                    avg_logprob=metrics["avg_logprob"],
                    compression_ratio=metrics["compression_ratio"],
                ):
                    logger.debug(
                        f"Groq Whisper hallucination filtered: '{text}' (metrics={metrics})"
                    )
                    return {"success": True, "text": ""}

                logger.info(f"Groq Whisper transcribed: '{text}'")
                return {"success": True, "text": text}
            finally:
                if os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except Exception:  # noqa: E722
                        pass  # nosec
        except Exception as e:
            logger.error(f"Error in Groq Whisper transcription: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    async def synthesize_speech(
        self, input_data: SynthesizeSpeechInput
    ) -> Dict[str, Any]:
        """
        Synthesize speech using Edge-TTS.
        """
        try:
            out_path = input_data.output_path
            if not out_path:
                fd, out_path = tempfile.mkstemp(suffix=".mp3")
                os.close(fd)

            rate = input_data.rate
            if rate is None:
                # Small natural jitter so consecutive responses don't all play
                # at an identical, robotic cadence. Biased slightly toward
                # slower rather than faster, since rushed TTS reads worse
                # than a mildly relaxed pace.
                rate = f"{random.uniform(-6, 4):+.0f}%"

            communicate = edge_tts.Communicate(
                input_data.text, input_data.voice, rate=rate
            )
            await communicate.save(out_path)

            logger.info(f"Synthesized text to {out_path}")

            return {"success": True, "audio_path": out_path, "text": input_data.text}
        except Exception as e:
            logger.error(f"Error synthesizing speech: {e}")
            return {"success": False, "error": str(e)}

    def detect_silence(self, input_data: DetectSilenceInput) -> Dict[str, Any]:
        """
        Detect if an audio file contains silence at the end using pydub.
        """
        try:
            from pydub import AudioSegment
            from pydub.silence import detect_silence as pydub_detect_silence

            if not os.path.exists(input_data.audio_file_path):
                return {
                    "success": False,
                    "error": f"File not found: {input_data.audio_file_path}",
                }

            audio = AudioSegment.from_file(input_data.audio_file_path)

            silences = pydub_detect_silence(
                audio,
                min_silence_len=int(input_data.min_silence_duration * 1000),
                silence_thresh=input_data.threshold_db,
            )

            is_silent_at_end = False
            total_duration = len(audio)

            if silences:
                last_silence_start, last_silence_end = silences[-1]
                # If the silence ends within 100ms of the audio file end, consider it silent at end
                if total_duration - last_silence_end < 100:
                    is_silent_at_end = True

            return {
                "success": True,
                "is_silent_at_end": is_silent_at_end,
                "silences_ms": silences,
                "total_duration_ms": total_duration,
            }
        except Exception as e:
            logger.error(f"Error detecting silence: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
voice_mcp = VoiceMCPServer()
