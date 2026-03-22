from database import SessionLocal, InterviewSession, SessionStatus
db = SessionLocal()
sessions = db.query(InterviewSession).all()
for s in sessions:
    print(f"Room ID: {s.room_id}, Status: {s.status}, Scheduled: {s.scheduled_at}")
db.close()
