@echo off
set PYTHONIOENCODING=utf-8
uvicorn main:app --reload --reload-exclude "*.log" --reload-exclude "*.db" --reload-exclude "*.mp3" --reload-exclude "*.webm" --reload-exclude "chroma_db/*"