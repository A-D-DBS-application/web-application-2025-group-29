#!/usr/bin/env python3
"""
Script om een bedrijf handmatig aan te maken in Supabase.
Gebruik: python create_company.py <email> <naam>
"""

import sys
from datetime import datetime
from app.config import supabase

def create_company(email, name):
    """Maak een bedrijf aan met email en naam."""
    try:
        # Check if company already exists
        existing = supabase.table('Companies').select('id').eq('emailaddress', email).execute()
        
        if existing.data and len(existing.data) > 0:
            company_id = existing.data[0]['id']
            print(f"Bedrijf bestaat al met ID: {company_id}")
            print(f"Naam updaten naar: '{name}'...")
            
            # Update name
            update_result = supabase.table('Companies').update({
                'name': name
            }).eq('id', company_id).execute()
            
            if update_result.data:
                print(f"✓ Bedrijfsnaam geüpdatet naar: '{update_result.data[0].get('name')}'")
                return True
            else:
                print("✗ Update mislukt")
                return False
        else:
            # Create new company
            print(f"Aanmaken van bedrijf: '{name}' ({email})...")
            
            new_company = supabase.table('Companies').insert({
                'name': name,
                'emailaddress': email,
                'created_at': datetime.now().isoformat()
            }).execute()
            
            if new_company.data:
                company = new_company.data[0]
                print(f"✓ Bedrijf succesvol aangemaakt!")
                print(f"  ID: {company.get('id')}")
                print(f"  Naam: {company.get('name')}")
                print(f"  Email: {company.get('emailaddress')}")
                return True
            else:
                print("✗ Aanmaken mislukt - geen data terug")
                return False
                
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Fout: {error_msg}")
        
        if 'row-level security' in error_msg.lower() or '42501' in error_msg:
            print("")
            print("RLS (Row Level Security) blokkeert het aanmaken.")
            print("")
            print("Oplossingen:")
            print("1. Log in als bedrijf met dit email adres - dan wordt het automatisch aangemaakt")
            print("2. Pas RLS policies aan in Supabase Dashboard > Authentication > Policies")
            print("3. Maak het bedrijf handmatig aan via Supabase Dashboard > Table Editor > Companies")
        
        return False

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Gebruik: python create_company.py <email> <naam>")
        print("Voorbeeld: python create_company.py poep1@gmail.com jonko")
        sys.exit(1)
    
    email = sys.argv[1]
    name = sys.argv[2]
    create_company(email, name)

