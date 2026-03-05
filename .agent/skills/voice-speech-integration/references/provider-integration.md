---
name: provider-integration
description: Full setup guides for Deepgram, OpenAI Whisper, ElevenLabs, and Azure Speech. Covers WebSocket reconnection, cost optimisation, error handling, and fallback strategies per provider.
---

# Provider Integration Reference

---

## Deepgram — Full Setup

```typescript
import { createClient, LiveTranscriptionEvents } from '@deepgram/sdk'

const dg = createClient(process.env.DEEPGRAM_API_KEY!)

export class DeepgramSession {
  private conn: ReturnType<typeof dg.listen.live> | null = null
  private reconnectAttempts = 0
  private readonly MAX_RECONNECTS = 3

  constructor(
    private sessionId: string,
    private onTranscript: (text: string, isFinal: boolean) => void,
    private onError: (err: Error) => void,
  ) {}

  async connect() {
    this.conn = dg.listen.live({
      model: 'nova-2', language: 'en-US',
      smart_format: true, punctuate: true,
      interim_results: true, endpointing: 500,
      encoding: 'opus', sample_rate: 16000, channels: 1,
    })

    this.conn.on(LiveTranscriptionEvents.Transcript, (data) => {
      const text = data.channel?.alternatives?.[0]?.transcript ?? ''
      if (text) this.onTranscript(text, data.is_final && data.speech_final)
    })

    this.conn.on(LiveTranscriptionEvents.Error, async (err) => {
      if (this.reconnectAttempts < this.MAX_RECONNECTS) {
        this.reconnectAttempts++
        await new Promise(r => setTimeout(r, 1000 * this.reconnectAttempts))
        await this.connect()
      } else {
        this.onError(new Error(`Deepgram failed after ${this.MAX_RECONNECTS} retries`))
      }
    })

    return new Promise<void>(resolve =>
      this.conn!.on(LiveTranscriptionEvents.Open, resolve)
    )
  }

  send(chunk: Buffer) { this.conn?.send(chunk) }
  close() { this.conn?.finish() }
}
```

---

## ElevenLabs — Streaming with First-Chunk Optimisation

```python
import asyncio
from elevenlabs.client import AsyncElevenLabs

eleven = AsyncElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

# Cache common phrases to avoid re-synthesising them
_PHRASE_CACHE: dict[str, bytes] = {}

async def synthesise_with_cache(
    text: str,
    voice_id: str,
    use_cache: bool = True,
) -> bytes:
    cache_key = f"{voice_id}:{text}"
    if use_cache and cache_key in _PHRASE_CACHE:
        return _PHRASE_CACHE[cache_key]

    audio = b""
    async for chunk in await eleven.text_to_speech.convert_as_stream(
        voice_id=voice_id,
        text=text,
        model_id="eleven_turbo_v2",
        output_format="mp3_44100_128",
    ):
        if isinstance(chunk, bytes):
            audio += chunk

    # Cache short phrases (< 100 chars) — questions, greetings
    if use_cache and len(text) < 100:
        _PHRASE_CACHE[cache_key] = audio

    return audio
```

---

## OpenAI TTS — Streaming Playback

```python
from openai import AsyncOpenAI

oai = AsyncOpenAI()

async def openai_tts_stream(
    text: str,
    on_chunk: callable,
    voice: str = "alloy",        # alloy, echo, fable, onyx, nova, shimmer
    model: str = "tts-1",        # tts-1 (fast) or tts-1-hd (quality)
    speed: float = 1.0,
):
    async with oai.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        speed=speed,
        response_format="mp3",
    ) as response:
        async for chunk in response.iter_bytes(chunk_size=4096):
            await on_chunk(chunk)
```

---

## Provider Cost Comparison (2025 estimates)

| Provider | Model | Cost | Best For |
|---|---|---|---|
| Deepgram | Nova-2 | $0.0059/min | Real-time STT |
| OpenAI | Whisper | $0.006/min | Batch STT |
| AssemblyAI | Best | $0.0108/min | Diarisation |
| ElevenLabs | Turbo v2 | $0.18/1K chars | Low-latency TTS |
| OpenAI | TTS-1 | $0.015/1K chars | Cost-effective TTS |
| OpenAI | TTS-1-HD | $0.030/1K chars | High-quality TTS |

**Cost for one 45-min interview session (estimate):**
- STT (Deepgram): ~$0.27
- TTS (ElevenLabs, ~5000 chars): ~$0.90
- Total voice cost: ~$1.17/session

---

## Fallback Strategy

```typescript
async function transcribeWithFallback(
  audioChunk: Buffer,
  primary: 'deepgram' | 'assemblyai' = 'deepgram'
): Promise<string> {
  try {
    if (primary === 'deepgram') {
      return await deepgramTranscribe(audioChunk)
    }
    return await assemblyaiTranscribe(audioChunk)
  } catch (err) {
    console.warn(`Primary STT failed, falling back: ${err}`)
    // Fall back to Whisper batch transcription
    return await whisperTranscribe(audioChunk)
  }
}
```
