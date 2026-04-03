import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:

    print("Database loaded perfectly!")
except Exception:
    import traceback

    traceback.print_exc()
