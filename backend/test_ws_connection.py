import asyncio
import websockets
import json

async def test_ws():
    uri = "ws://localhost:8000/api/interviews/2996eced-d7b7-4b0f-8138-b57f450a2512/ws"
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected to WebSocket!")
            # Should receive initial greeting text
            greeting = await websocket.recv()
            print(f"Received: {greeting}")
            
            # Should receive initial greeting audio (Binary)
            audio = await websocket.recv()
            print(f"Received audio blob of size {len(audio)}")
            
    except Exception as e:
        print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_ws())
