"""
Voice MCP Server - Speech-to-text and text-to-speech.
Uses Whisper (tiny) for transcription (lazy loading) and Edge-TTS for synthesis.
"""

from typing import Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
import random
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
        No ffmpeg, no local model — just sends audio over HTTP.
        Priya's recommendation: server-side STT is the only reliable path.
        """
        try:
            from groq import Groq
            from config import settings

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
                    )

                # With verbose_json, we get segments with no_speech_prob
                if hasattr(transcription, "text"):
                    text = transcription.text.strip()
                else:
                    text = str(transcription).strip()

                # Check no_speech_prob from segments — if too high, it's silence
                if hasattr(transcription, "segments") and transcription.segments:
                    avg_no_speech = sum(
                        (
                            s.get("no_speech_prob", 0)
                            if isinstance(s, dict)
                            else getattr(s, "no_speech_prob", 0)
                        )
                        for s in transcription.segments
                    ) / len(transcription.segments)
                    if avg_no_speech > 0.7:
                        logger.debug(
                            f"Groq Whisper detected silence (no_speech_prob={avg_no_speech:.2f}): '{text}'"
                        )
                        return {
                            "success": True,
                            "text": "",
                        }  # Return empty, it's silence

                # Hallucination filter — Whisper generates these on silent audio
                # Using a set for exact matches and checking for repetitive hallucinations
                HALLUCINATION_PHRASES = {
                    "thank you",
                    "thank you.",
                    "thanks.",
                    "thanks",
                    "thank you for watching",
                    "thank you for watching.",
                    "thanks for watching",
                    "thanks for watching.",
                    "please subscribe",
                    "subscribe",
                    "like and subscribe",
                    "bye",
                    "bye.",
                    "you",
                    "okay",
                    "okay.",
                    "um",
                    "uh",
                    "so",
                    "the",
                    "i",
                    "a",
                    "and",
                    "what is it on behalf of me",
                    "what is it",
                    "is it",
                    "on behalf of me",
                    "thankyou",
                    "thankyou thankyou",
                    "thankyou thankyou thankyou",
                }

                clean_text = text.lower().strip(".,!? ")

                # Check for repetitive single-word hallucinations like "thankyou thankyou thankyou"
                words = clean_text.split()
                if (
                    len(words) > 1
                    and all(w == words[0] for w in words)
                    and words[0] in {"thankyou", "thank", "you", "thanks"}
                ):
                    logger.debug(
                        f"Groq Whisper repetitive hallucination filtered: '{text}'"
                    )
                    return {"success": True, "text": ""}

                if clean_text in HALLUCINATION_PHRASES:
                    logger.debug(f"Groq Whisper hallucination filtered: '{text}'")
                    return {"success": True, "text": ""}

                # If the text is just "Thank you" followed by something very short, it's often an echo
                if clean_text.startswith("thank you") and len(words) < 4:
                    logger.debug(f"Groq Whisper short 'thank you' filter: '{text}'")
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

            communicate = edge_tts.Communicate(input_data.text, input_data.voice, rate=rate)
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
