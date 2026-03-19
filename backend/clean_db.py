import sys
import os

# Add backend directory to path so we can import modules
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, InterviewSession, Evaluation, TranscriptChunk

def clean_database():
    db = SessionLocal()
    try:
        # Delete evaluations
        eval_count = db.query(Evaluation).delete()
        print(f"Deleted {eval_count} evaluations.")
        
        # Delete transcript chunks
        chunk_count = db.query(TranscriptChunk).delete()
        print(f"Deleted {chunk_count} transcript chunks.")
        
        # Delete interview sessions
        session_count = db.query(InterviewSession).delete()
        print(f"Deleted {session_count} interview sessions.")
        
        db.commit()
        print("Successfully cleaned all old interviews from the database.")
    except Exception as e:
        db.rollback()
        print(f"Error occurred during cleanup: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    clean_database()
