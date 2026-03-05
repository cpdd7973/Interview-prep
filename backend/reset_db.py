import os
import sys

# Add current directory to path so config/database modules can be imported
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from database import Base, engine, init_db

def reset():
    print("Dropping all tables...")
    try:
        Base.metadata.drop_all(bind=engine)
    except Exception as e:
        print(f"Error dropping tables: {e}")
        
    print("Recreating all tables...")
    init_db()
    print("Database reset complete.")

if __name__ == "__main__":
    reset()
