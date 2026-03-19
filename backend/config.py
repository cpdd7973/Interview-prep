"""
Configuration management for Interview Agent System.
Loads all environment variables and provides typed config objects.
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Literal


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LLM Configuration
    groq_api_key: str
    gemini_api_key: str
    primary_llm: Literal["groq", "gemini"] = "groq"
    
    # Google APIs (OAuth2 — optional if using GWS CLI instead)
    google_client_id: str = ""
    google_client_secret: str = ""
    google_refresh_token: str = ""
    admin_email: str = ""
    
    # Google Workspace CLI (gws)
    gws_cli_path: str = "gws"  # Path to gws binary, or 'gws' if on PATH
    
    # Daily.co (Now Optional/Deprecated for Jitsi Meet)
    daily_api_key: str = ""
    daily_domain: str = ""
    
    # Application URLs
    backend_url: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    
    # Database
    database_path: str = "./interview_system.db"
    scheduler_jobstore_path: str = "./scheduler_jobs.db"
    
    # Whisper
    whisper_model: Literal["tiny", "base"] = "tiny"
    whisper_device: Literal["cpu", "cuda"] = "cpu"
    
    # Interview Settings
    early_entry_minutes: int = 5
    session_timeout_minutes: int = 60
    max_interview_duration_minutes: int = 45
    
    # Email (SMTP — use Gmail App Password for simple setup)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""  # Gmail address (e.g. you@gmail.com)
    smtp_password: str = ""  # Gmail App Password from myaccount.google.com/apppasswords
    
    # Security
    secret_key: str
    allowed_origins: str = "http://localhost:5173"
    
    # Logging
    log_level: str = "INFO"
    
    model_config = {
        "env_file": str(Path(__file__).parent.parent / ".env"),
        "case_sensitive": False,
        "extra": "ignore"  # Allow extra env vars from gws auth, system, etc.
    }
    
    @property
    def database_url(self) -> str:
        """SQLAlchemy database URL."""
        return f"sqlite:///{self.database_path}"
    
    @property
    def allowed_origins_list(self) -> list[str]:
        """Parse CORS allowed origins."""
        return [origin.strip() for origin in self.allowed_origins.split(",")]


# Global settings instance
settings = Settings()

# Paths
BASE_DIR = Path(__file__).parent
PROMPTS_DIR = BASE_DIR / "prompts"
QUESTION_BANK_DIR = BASE_DIR / "question_bank"
REPORTS_DIR = BASE_DIR.parent / "reports"

# Ensure directories exist
REPORTS_DIR.mkdir(exist_ok=True)
