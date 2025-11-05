#!/usr/bin/env python3
"""
Script om bedrijfsnamen te updaten in Supabase.
Gebruik: python update_company_name.py <email> <nieuwe_naam>
"""

import sys
from app.config import supabase

def update_company_name(email, new_name):
    """Update de naam van een bedrijf op basis van email adres."""
    try:
        # Zoek het bedrijf op basis van email
        result = supabase.table('Companies').select('id, name, emailaddress').eq('emailaddress', email).execute()
        
        if not result.data or len(result.data) == 0:
            print(f"✗ Geen bedrijf gevonden met email: {email}")
            return False
        
        company = result.data[0]
        old_name = company.get('name')
        company_id = company.get('id')
        
        print(f"Bedrijf gevonden:")
        print(f"  ID: {company_id}")
        print(f"  Huidige naam: '{old_name}'")
        print(f"  Email: {email}")
        print(f"")
        print(f"Updaten naar: '{new_name}'...")
        
        # Update de naam
        update_result = supabase.table('Companies').update({
            'name': new_name
        }).eq('id', company_id).execute()
        
        if update_result.data:
            print(f"✓ Bedrijfsnaam succesvol geüpdatet!")
            print(f"  Oude naam: '{old_name}'")
            print(f"  Nieuwe naam: '{update_result.data[0].get('name')}'")
            return True
        else:
            print(f"✗ Update mislukt - geen data terug")
            return False
            
    except Exception as e:
        error_msg = str(e)
        print(f"✗ Fout bij updaten: {error_msg}")
        
        if 'row-level security' in error_msg.lower() or '42501' in error_msg:
            print("")
            print("RLS (Row Level Security) blokkeert de update.")
            print("Je moet ingelogd zijn als het bedrijf om de naam te kunnen updaten.")
            print("Of maak de update via Supabase Dashboard > Table Editor > Companies")
        
        return False

def list_all_companies():
    """Toon alle bedrijven in de database."""
    try:
        result = supabase.table('Companies').select('id, name, emailaddress').order('name').execute()
        
        if not result.data:
            print("Geen bedrijven gevonden in de database.")
            return
        
        print("Alle bedrijven in de database:")
        print("=" * 70)
        for company in result.data:
            print(f"ID: {company.get('id'):<3} | Naam: {company.get('name'):<30} | Email: {company.get('emailaddress')}")
        print("=" * 70)
        print(f"Totaal: {len(result.data)} bedrijven")
        
    except Exception as e:
        print(f"Fout bij ophalen bedrijven: {e}")

if __name__ == "__main__":
    if len(sys.argv) == 1:
        # Geen argumenten - toon alle bedrijven
        list_all_companies()
        print("")
        print("Gebruik: python update_company_name.py <email> <nieuwe_naam>")
        print("Voorbeeld: python update_company_name.py poep1@gmail.com jonko")
    elif len(sys.argv) == 3:
        email = sys.argv[1]
        new_name = sys.argv[2]
        update_company_name(email, new_name)
    else:
        print("Gebruik: python update_company_name.py <email> <nieuwe_naam>")
        print("Of: python update_company_name.py (om alle bedrijven te zien)")
        sys.exit(1)

