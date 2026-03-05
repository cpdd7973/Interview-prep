---
name: audio-processing
description: Audio format guide, chunking strategies, browser MediaRecorder patterns, noise suppression, WebRTC audio pipeline, and client-side preprocessing for voice interview applications.
---

# Audio Processing Reference

---

## Audio Format Decision

| Format | Use Case | Size | Browser Support | Notes |
|---|---|---|---|---|
| **Opus/WebM** | Real-time streaming | Small | Chrome, Firefox, Edge | Best for STT streaming |
| **MP3** | TTS playback, storage | Medium | Universal | Good for stored audio |
| **WAV/PCM** | High-accuracy batch STT | Large | Universal | Whisper prefers this |
| **OGG** | Alternative streaming | Small | Firefox-first | Avoid for Safari |
| **AAC/M4A** | iOS/Safari recording | Medium | Safari-native | Required for Safari |

**Rule:** Capture in Opus/WebM (or AAC on Safari). Convert server-side for STT if needed.

---

## Browser MediaRecorder Pipeline

```typescript
export class AudioRecorder {
  private mediaRecorder: MediaRecorder | null = null
  private stream: MediaStream | null = null
  private chunks: Blob[] = []

  async start(onChunk: (chunk: Blob) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount:    1,       // Mono — STT doesn't need stereo
        sampleRate:      16000,   // 16kHz — optimal for STT
        echoCancellation: true,   // Browser-native echo cancellation
        noiseSuppression: true,   // Browser-native noise suppression
        autoGainControl:  true,   // Normalise mic input level
      }
    })

    // Choose best supported format
    const mimeType = this.getSupportedMimeType()

    this.mediaRecorder = new MediaRecorder(this.stream, {
      mimeType,
      audioBitsPerSecond: 16000,  // 16kbps — sufficient for voice
    })

    // Stream chunks every 250ms — good balance of latency vs overhead
    this.mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) onChunk(e.data)
    }

    this.mediaRecorder.start(250)  // timeslice = chunk interval ms
  }

  stop(): Promise<Blob> {
    return new Promise((resolve) => {
      if (!this.mediaRecorder) return resolve(new Blob([]))

      this.mediaRecorder.onstop = () => {
        const fullAudio = new Blob(this.chunks, {
          type: this.mediaRecorder!.mimeType
        })
        this.chunks = []
        resolve(fullAudio)
      }

      this.mediaRecorder.stop()
      this.stream?.getTracks().forEach(t => t.stop())
    })
  }

  private getSupportedMimeType(): string {
    const types = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',              // Safari fallback
    ]
    return types.find(t => MediaRecorder.isTypeSupported(t)) ?? ''
  }
}
```

---

## Server-Side Audio Conversion

```python
import subprocess, io, tempfile, os

def convert_to_whisper_format(audio_bytes: bytes, input_format: str = "webm") -> bytes:
    """
    Convert browser audio (WebM/Opus) to WAV 16kHz mono for Whisper.
    Requires: ffmpeg installed
    """
    with tempfile.NamedTemporaryFile(suffix=f".{input_format}", delete=False) as inp:
        inp.write(audio_bytes)
        inp_path = inp.name

    out_path = inp_path.replace(f".{input_format}", ".wav")

    try:
        subprocess.run([
            "ffmpeg", "-y",
            "-i",    inp_path,
            "-ar",   "16000",    # 16kHz sample rate
            "-ac",   "1",        # Mono
            "-f",    "wav",
            out_path
        ], check=True, capture_output=True)

        with open(out_path, "rb") as f:
            return f.read()
    finally:
        os.unlink(inp_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def get_audio_duration(audio_bytes: bytes, format: str = "wav") -> float:
    """Returns duration in seconds using ffprobe."""
    with tempfile.NamedTemporaryFile(suffix=f".{format}") as f:
        f.write(audio_bytes)
        result = subprocess.run([
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            f.name
        ], capture_output=True, text=True)
    return float(result.stdout.strip() or 0)
```

---

## Noise Quality Detection

```python
import numpy as np

def assess_audio_quality(audio_bytes: bytes, sample_rate: int = 16000) -> dict:
    """
    Detect common audio quality issues before sending to STT.
    Returns quality assessment and recommendation.
    """
    import wave, struct

    # Parse WAV samples
    with wave.open(io.BytesIO(audio_bytes)) as wav:
        frames = wav.readframes(wav.getnframes())
        samples = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    duration = len(samples) / sample_rate
    rms = np.sqrt(np.mean(samples ** 2))
    peak = np.max(np.abs(samples))

    issues = []

    if duration < 0.5:
        issues.append("too_short")
    if rms < 0.005:
        issues.append("too_quiet")    # Likely muted or mic too far
    if rms > 0.8:
        issues.append("too_loud")     # Clipping likely
    if peak > 0.99:
        issues.append("clipping")
    if duration > 120:
        issues.append("too_long")     # Chunk before sending

    snr_estimate = 20 * np.log10(rms / 0.002) if rms > 0 else 0

    return {
        "duration_seconds": round(duration, 2),
        "rms_level":        round(float(rms), 4),
        "peak_level":       round(float(peak), 4),
        "snr_estimate_db":  round(snr_estimate, 1),
        "issues":           issues,
        "quality":          "good" if not issues else "poor",
        "send_to_stt":      len(issues) == 0 or issues == ["too_long"],
    }
```

---

## Audio Storage Pattern

```python
import boto3, hashlib

s3 = boto3.client("s3")
AUDIO_BUCKET = "interview-audio-recordings"

async def store_audio(
    session_id: str,
    turn_index: int,
    audio_bytes: bytes,
    format: str = "webm",
) -> str:
    """Store audio in S3, return the S3 key."""
    # Content-addressed key — deduplicates identical audio
    content_hash = hashlib.sha256(audio_bytes).hexdigest()[:16]
    key = f"sessions/{session_id}/turns/{turn_index:04d}_{content_hash}.{format}"

    s3.put_object(
        Bucket=AUDIO_BUCKET,
        Key=key,
        Body=audio_bytes,
        ContentType=f"audio/{format}",
        ServerSideEncryption="aws:kms",    # Encrypt at rest
        Metadata={
            "session-id":  session_id,
            "turn-index":  str(turn_index),
        }
    )
    return key


def get_audio_url(s3_key: str, expires_in: int = 3600) -> str:
    """Generate a pre-signed URL for audio playback (1 hour TTL)."""
    return s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": AUDIO_BUCKET, "Key": s3_key},
        ExpiresIn=expires_in,
    )
```
