import requests
try:
    print("Testing cancel endpoint...")
    # Fetch a room ID first
    res = requests.get('http://127.0.0.1:8001/api/interviews')
    if not res.ok:
        print(f"Failed to fetch interviews: {res.status_code}")
        print(res.text)
        exit(1)
    
    sessions = res.json().get('sessions', [])
    if not sessions:
        print("No sessions found to cancel!")
        exit(1)
        
    room_id = sessions[0]['room_id']
    print(f"Cancelling room: {room_id}")
    
    # Try to cancel
    res = requests.post(f'http://127.0.0.1:8001/api/interviews/{room_id}/cancel')
    print(f"Status Code: {res.status_code}")
    print(f"Response: {res.text}")
    print(f"Headers: {res.headers}")

except Exception as e:
    print(f"Script error: {e}")
