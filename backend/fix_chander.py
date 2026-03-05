import sqlite3
from datetime import datetime

def fix_all_chander_sessions():
    conn = sqlite3.connect('interview_system.db')
    cursor = conn.cursor()
    now = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    
    # List all
    print("CURRENT SESSIONS:")
    cursor.execute('SELECT room_id, candidate_name, status FROM interview_sessions')
    for row in cursor.fetchall():
        print(f"  {row[0]} | {row[1]} | {row[2]}")
    
    # Activate all for Chander
    cursor.execute('''
        UPDATE interview_sessions 
        SET status = 'ACTIVE', activated_at = ?, completed_at = NULL 
        WHERE candidate_name LIKE '%Chander%'
    ''', (now,))
    
    print(f"Updated {cursor.rowcount} sessions for Chander to ACTIVE")
    
    conn.commit()
    conn.close()

if __name__ == "__main__":
    fix_all_chander_sessions()
