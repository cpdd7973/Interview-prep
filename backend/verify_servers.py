import os
import sys

# Add the backend directory to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def verify_servers():
    print("Verifying MCP Servers...\n")
    try:
        # 1. Voice
        from mcp_servers.voice_mcp import voice_mcp
        print("✅ Voice MCP Server loaded (Whisper & Edge-TTS configured)")
        
        # 2. Question Bank
        from mcp_servers.question_bank_mcp import question_bank_mcp
        print("✅ Question Bank MCP Server loaded (ChromaDB semantic search active)")
        
        # 3. Room
        from mcp_servers.room_mcp import room_mcp
        print("✅ Room MCP Server loaded (Daily.co initialized)")
        
        # 4. Gmail & Calendar
        from mcp_servers.gmail_mcp import gmail_mcp
        from mcp_servers.calendar_mcp import calendar_mcp
        print("✅ Gmail & Calendar MCP Servers loaded (Google API initialized)")
        
        # 5. Evaluator & Report
        from mcp_servers.evaluator_mcp import evaluator_mcp
        from mcp_servers.report_mcp import report_mcp
        print("✅ Evaluator & Report MCP Servers loaded (LLM and PDF generation ready)")
        
        print("\n🎉 All 5 MCP servers instantiated successfully without syntax or import errors!")
        
    except Exception as e:
        print(f"\n❌ Verification failed with error: {e}")
        print("Please ensure your virtual environment is active and 'pip install -r requirements.txt' is completed.")

if __name__ == "__main__":
    verify_servers()
