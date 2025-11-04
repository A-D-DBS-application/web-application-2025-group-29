import os
from supabase import create_client, Client

class Config:
    SECRET_KEY = 'Agriflowgroup29'
    SQLALCHEMY_DATABASE_URI = (
        'postgresql://Agriflow:Agriflowgroup29@db.ikdirrysepokfryqnxre.supabase.co:5432/Agriflow'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ikdirrysepokfryqnxre.supabase.co")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "<YOUR_SUPABASE_API_KEY>")

supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)





    


