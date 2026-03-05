import sqlite3
from datetime import datetime

def activate_session(room_id):
    conn = sqlite3.connect('interview_system.db')
    cursor = conn.cursor()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Reset status to ACTIVE and update activation time
    cursor.execute('''
        UPDATE interview_sessions 
        SET status = ?, activated_at = ?, completed_at = NULL 
        WHERE room_id = ?
    ''', ('ACTIVE', now, room_id))
    
    if cursor.rowcount > 0:
        print(f"Successfully activated session {room_id}")
    else:
        print(f"Session {room_id} not found")
        
    conn.commit()
    conn.close()

if __name__ == "__main__":
    activate_session('2996eced-d7b7-4b0f-8138-b57f450a2512')
