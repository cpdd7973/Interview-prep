"""
Regression tests for the consolidated Whisper hallucination filter
(mcp_servers/voice_mcp.py). Live testing with a real microphone surfaced
Groq Whisper hallucinating short phrases from near-silent/ambient audio
during idle periods ("Music", "I'm going to go to the next slide.",
"So, let's go.", "Thank you. Thank you.") that slipped past the previous
two-layer, two-file, divergent-phrase-list filter. Also guards against the
opposite regression an earlier audit flagged: legitimate short answers like
"yes"/"no" must never be blanket-filtered.

Follows the test_end_interview_gate.py convention: plain functions, direct
asserts, no pytest (not installed in this dev environment), run directly
via `python test_voice_hallucination_filter.py`.
"""

import io

from mcp_servers.voice_mcp import (
    normalize_transcript,
    _find_repeated_phrase,
    is_hallucinated_transcript,
    _is_silent_dbfs,
    is_near_silent_audio,
)


def test_normalize_transcript():
    # The exact live-observed doubled hallucination -- internal punctuation
    # must be stripped, not just the ends (the original bug).
    assert normalize_transcript("Thank you. Thank you.") == "thank you thank you"
    # Contractions collapse into one word (apostrophe removed, no space
    # inserted) -- a naive "replace all punctuation with a space" pass would
    # split "I'm" into "i" + "m", which was confirmed to make two of the
    # live-observed hallucinations miss the phrase list entirely.
    assert normalize_transcript("I'm going to go to the next slide.") == (
        "im going to go to the next slide"
    )
    assert normalize_transcript("So, let's go.") == "so lets go"
    assert normalize_transcript("") == ""
    assert normalize_transcript("   Multiple   spaces  ") == "multiple spaces"


def test_find_repeated_phrase():
    assert (
        _find_repeated_phrase(normalize_transcript("Thank you. Thank you.").split())
        == "thank you"
    )
    assert _find_repeated_phrase(["thankyou"] * 3) == "thankyou"
    # Genuine non-repeating answer must not be flagged.
    assert (
        _find_repeated_phrase(normalize_transcript("It's the Big O notation.").split())
        is None
    )
    assert _find_repeated_phrase([]) is None
    assert _find_repeated_phrase(["one"]) is None


def test_live_confirmed_hallucinations_are_filtered():
    """The exact four transcripts observed live that the old filter missed."""
    assert is_hallucinated_transcript("Music") is True
    assert is_hallucinated_transcript("I'm going to go to the next slide.") is True
    assert is_hallucinated_transcript("So, let's go.") is True
    assert is_hallucinated_transcript("Thank you. Thank you.") is True


def test_concatenated_hallucination_fragments_are_filtered():
    """
    Second live-discovered gap, found on a follow-up live test AFTER the
    first fix shipped: Whisper concatenated two different hallucination
    fragments into one longer sentence -- "I'm going to go to the next
    slide. Thank you. Thank you." The combined normalized string doesn't
    exact-match any single HALLUCINATION_PHRASES entry and isn't a clean
    periodic repetition, so it slipped through checks #1 and #2 and got
    sent to the interviewer as a real candidate answer.
    """
    assert (
        is_hallucinated_transcript(
            "I'm going to go to the next slide. Thank you. Thank you."
        )
        is True
    )
    # A lone filler word must NOT be caught by the same mechanism -- it
    # needs to fall through to the dedicated (corroboration-based) filler
    # check instead, which is deliberately more conservative.
    assert is_hallucinated_transcript("um", avg_no_speech_prob=0.1) is False
    # A real multi-sentence answer that happens to include a genuine
    # "thank you" must not be swept up just because it's multi-sentence.
    assert (
        is_hallucinated_transcript(
            "Thank you. My experience is mostly with FastAPI and PostgreSQL."
        )
        is False
    )
    assert (
        is_hallucinated_transcript("I use REST APIs. I also use GraphQL sometimes.")
        is False
    )


def test_legitimate_short_answers_are_not_filtered():
    """
    Regression guard for the earlier audit's finding: the old main.py
    echo_phrases set blanket-filtered "yes"/"no", which are legitimate
    answers to yes/no interview questions. Must never be filtered again.
    """
    assert is_hallucinated_transcript("Yes") is False
    assert is_hallucinated_transcript("No") is False
    assert is_hallucinated_transcript("Yes.") is False
    assert is_hallucinated_transcript("No.") is False
    # A plausible genuine short answer, sanity check against over-filtering.
    assert is_hallucinated_transcript("It's the Big O notation.") is False


def test_filler_word_corroboration():
    # No corroborating signal at all -> conservative default, filtered
    # (matches this filter's pre-existing behavior).
    assert is_hallucinated_transcript("um") is True
    # A low no_speech_prob means Whisper is confident there IS speech --
    # don't filter, this is probably genuine hesitation mid-answer.
    assert is_hallucinated_transcript("um", avg_no_speech_prob=0.1) is False
    # A high no_speech_prob corroborates it's hallucinated filler.
    assert is_hallucinated_transcript("uh", avg_no_speech_prob=0.6) is True
    # avg_logprob corroboration works the same way.
    assert is_hallucinated_transcript("um", avg_logprob=-2.0) is True
    assert is_hallucinated_transcript("um", avg_logprob=-0.1) is False


def test_compression_ratio_branch_respects_word_count_cap():
    # Distinct words (not caught by phrase-match or repetition-match) with a
    # manually supplied high compression_ratio -- isolates this branch from
    # the others, which would otherwise catch simple repeated-word cases
    # before this check is ever reached.
    short_text = "hello world foo bar baz qux"
    assert is_hallucinated_transcript(short_text, compression_ratio=3.0) is True
    assert is_hallucinated_transcript(short_text, compression_ratio=2.0) is False

    long_text = " ".join(f"distinctword{i}" for i in range(20))
    # Same high ratio, but too long -- word-count cap means this branch
    # must not fire, avoiding false positives on long legitimate answers.
    assert is_hallucinated_transcript(long_text, compression_ratio=3.0) is False


def test_is_silent_dbfs_pure_thresholds():
    assert (
        _is_silent_dbfs(float("-inf")) is True
    )  # pydub reports this for pure digital silence
    assert _is_silent_dbfs(-45.0) is True
    assert _is_silent_dbfs(-40.0) is False  # exactly at threshold -> not silent
    assert _is_silent_dbfs(-10.0) is False


def test_is_near_silent_audio_fails_open_on_bad_input():
    # Garbage bytes can't be decoded -- must return None (fail open), never
    # raise and never incorrectly claim "near-silent".
    assert is_near_silent_audio(b"not real audio data") is None


def test_is_near_silent_audio_with_synthetic_clips():
    """
    Only runs the pydub-integration assertions if pydub can actually be
    imported in this environment. Confirmed during design: pydub depends on
    the stdlib `audioop` module, removed in Python 3.13 (this dev machine) --
    production's Dockerfile pins Python 3.11, where it works fine. Skipping
    gracefully here still leaves every other test in this file exercised.
    """
    try:
        from pydub import AudioSegment
        from pydub.generators import Sine
    except Exception as e:
        print(f"  (skipped: pydub unavailable in this environment: {e})")
        return

    silent_buf = io.BytesIO()
    AudioSegment.silent(duration=500).export(silent_buf, format="wav")
    assert is_near_silent_audio(silent_buf.getvalue(), audio_format="wav") is True

    loud_buf = io.BytesIO()
    Sine(440).to_audio_segment(duration=500).export(loud_buf, format="wav")
    assert is_near_silent_audio(loud_buf.getvalue(), audio_format="wav") is False


if __name__ == "__main__":
    test_normalize_transcript()
    test_find_repeated_phrase()
    test_live_confirmed_hallucinations_are_filtered()
    test_concatenated_hallucination_fragments_are_filtered()
    test_legitimate_short_answers_are_not_filtered()
    test_filler_word_corroboration()
    test_compression_ratio_branch_respects_word_count_cap()
    test_is_silent_dbfs_pure_thresholds()
    test_is_near_silent_audio_fails_open_on_bad_input()
    test_is_near_silent_audio_with_synthetic_clips()
    print("All voice hallucination filter tests passed.")
