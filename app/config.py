import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from a local .env file if present
load_dotenv()


def _build_database_uri() -> str:
    # Prefer environment variable (copy from Supabase -> Settings -> Database -> Connection string)
    database_url = os.getenv("DATABASE_URL")

    if database_url:
        # If placeholder is still present, use local fallback to avoid runtime errors
        if "YOUR_DB_PASSWORD" in database_url:
            return "sqlite:///app.db"

        # Normalize old-style prefixes (e.g., Heroku style)
        if database_url.startswith("postgres://"):
            database_url = database_url.replace("postgres://", "postgresql://", 1)

        # Ensure SSL for Supabase connections unless explicitly provided
        if "supabase.co" in database_url and "sslmode=" not in database_url:
            database_url = f"{database_url}{'&' if '?' in database_url else '?'}sslmode=require"
        return database_url

    # Local development fallback
    return "sqlite:///app.db"


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'Agriflowgroup29')
    SQLALCHEMY_DATABASE_URI = _build_database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ikdirrysepokfryqnxre.supabase.co")
<<<<<<< Updated upstream
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    
    # Fallback to known key if not set (for development)
    if not SUPABASE_KEY or SUPABASE_KEY == "<YOUR_SUPABASE_API_KEY>":
        SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlrZGlycnlzZXBva2ZyeXFueHJlIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjEwMjEwNjMsImV4cCI6MjA3NjU5NzA2M30.HMmjYOCLV6t3H_ccny_layy5QyVCNTdFSSP3_ynVN2E"

    # Secure session cookie settings (best practices)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set Secure=True automatically when running behind HTTPS in production
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"


# Create Supabase client with error handling
try:
    supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY) if Config.SUPABASE_KEY else None
except Exception as e:
    print(f"ERROR: Failed to create Supabase client: {e}")
    supabase = None





    

=======
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImlrZGlycnlzZXBva2ZyeXFueHJlIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2MTAyMTA2MywiZXhwIjoyMDc2NTk3MDYzfQ.Cxa5SDrz2Soct8UI6cIjee338l2y3VYx8yQ126kBPPc")
>>>>>>> Stashed changes

supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)