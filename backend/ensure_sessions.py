import sqlite3
from datetime import datetime

def ensure_specific_session(room_id):
    conn = sqlite3.connect('interview_system.db')
    cursor = conn.cursor()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # Check if exists
    cursor.execute('SELECT room_id FROM interview_sessions WHERE room_id = ?', (room_id,))
    if cursor.fetchone():
        print(f"Session {room_id} exists. Updating to ACTIVE.")
        cursor.execute('''
            UPDATE interview_sessions SET status = 'ACTIVE', activated_at = ?, completed_at = NULL 
            WHERE room_id = ?
        ''', (now, room_id))
    else:
        print(f"Creating new session {room_id} as ACTIVE.")
        cursor.execute('''
            INSERT INTO interview_sessions 
            (room_id, candidate_name, candidate_email, job_role, company, interviewer_designation, status, scheduled_at, activated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (room_id, 'Chander', 'chander@example.com', 'React Developer', 'Adobe', 'Senior Engineer', 'ACTIVE', now, now))
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    # The ID I saw in the logs earlier
    ensure_specific_session('707106cf-817f-410a-ae83-8a3962650041')
    # Also ensure the other one I saw
    ensure_specific_session('2996eced-d7b7-4b0f-8138-b57f450a2512')
