import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    import database
    print("Database loaded perfectly!")
except Exception as e:
    import traceback
    traceback.print_exc()
