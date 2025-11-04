from .config import supabase

def get_user_by_email(email):
    result = supabase.table("Farmer").select("*").eq("emailaddress", email).execute()
    if len(result.data) > 0:
        return result.data[0]
    return None

def insert_order(data):
    return supabase.table("Orders").insert(data).execute()

def insert_farmer(data):
    return supabase.table("Farmer").insert(data).execute()
