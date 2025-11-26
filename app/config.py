import os
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables from a local .env file if present
load_dotenv()


class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'Agriflowgroup29')

    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ikdirrysepokfryqnxre.supabase.co")
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
