import sys
import os

# Create dummy webm audio
import tempfile
import edge_tts
import asyncio

async def test():
    from mcp_servers.voice_mcp import voice_mcp, TranscribeAudioInput, SynthesizeSpeechInput
    print("Testing TTS...")
    tts_result = await voice_mcp.synthesize_speech(SynthesizeSpeechInput(text="Hello, testing transcription!"))
    if not tts_result.get("success"):
        print("TTS failed:", tts_result)
        return
        
    audio_path = tts_result["audio_path"]
    print(f"TTS succeeded, audio saved to {audio_path}. Testing STT...")
    
    stt_result = voice_mcp.transcribe_audio(TranscribeAudioInput(audio_file_path=audio_path))
    print("STT result:", stt_result)

if __name__ == "__main__":
    asyncio.run(test())
