"""
Local dev utility: wipes all interview/evaluation/transcript data.
Destructive. Not shipped in the Docker image (see backend/.dockerignore).
"""

import sys
import os

# backend/ (parent of this scripts/ dir) so `database` resolves
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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
    confirm = input(
        "This permanently deletes ALL interview sessions, transcripts, and "
        "evaluations. Type YES to confirm: "
    )
    if confirm != "YES":
        print("Aborted.")
        sys.exit(1)
    clean_database()
