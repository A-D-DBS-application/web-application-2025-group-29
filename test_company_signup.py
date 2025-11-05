#!/usr/bin/env python3
"""
Test script om te zien waarom bedrijf aanmaken faalt tijdens signup
"""
import sys
from app.config import supabase, Config
from supabase import create_client
from datetime import datetime

def test_company_creation(email, password, company_name):
    """Test het volledige signup proces voor een bedrijf"""
    print(f"=" * 60)
    print(f"Test: Bedrijf aanmaken tijdens signup")
    print(f"Email: {email}")
    print(f"Bedrijfsnaam: {company_name}")
    print(f"=" * 60)
    
    try:
        # Step 1: Sign up
        print("\n1. Signup...")
        signup_result = supabase.auth.sign_up({
            "email": email,
            "password": password
        })
        
        if not signup_result.user:
            print("✗ Signup failed - no user returned")
            return False
        
        print(f"✓ Signup successful - User ID: {signup_result.user.id}")
        print(f"  Session available: {bool(signup_result.session)}")
        
        # Step 2: Sign in to get session
        print("\n2. Sign in to get session...")
        signin_result = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        if not signin_result.session:
            print("✗ Sign in failed - no session")
            return False
        
        print(f"✓ Sign in successful")
        print(f"  Access token: {signin_result.session.access_token[:20]}...")
        
        # Step 3: Create authenticated client
        print("\n3. Creating authenticated Supabase client...")
        authenticated_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
        authenticated_client.auth.set_session(
            access_token=signin_result.session.access_token,
            refresh_token=signin_result.session.refresh_token
        )
        
        # Get current user to verify
        current_user = authenticated_client.auth.get_user()
        print(f"✓ Authenticated as: {current_user.user.email}")
        
        # Step 4: Check if company exists
        print("\n4. Checking if company exists...")
        existing = authenticated_client.table('Companies').select('id').eq('emailaddress', email).limit(1).execute()
        if existing.data:
            print(f"  Company already exists with ID: {existing.data[0]['id']}")
            return True
        
        # Step 5: Create company
        print(f"\n5. Creating company '{company_name}'...")
        company_result = authenticated_client.table('Companies').insert({
            "name": company_name,
            "emailaddress": email,
            "created_at": datetime.now().isoformat()
        }).execute()
        
        if company_result.data:
            print(f"✓ Company created successfully!")
            print(f"  ID: {company_result.data[0]['id']}")
            print(f"  Name: {company_result.data[0]['name']}")
            print(f"  Email: {company_result.data[0]['emailaddress']}")
            return True
        else:
            print("✗ Company creation returned no data")
            return False
            
    except Exception as e:
        error_msg = str(e)
        print(f"\n✗ Error: {error_msg}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Gebruik: python test_company_signup.py <email> <password> <company_name>")
        print("Voorbeeld: python test_company_signup.py test@example.com password123 TestCompany")
        sys.exit(1)
    
    email = sys.argv[1]
    password = sys.argv[2]
    company_name = sys.argv[3]
    
    success = test_company_creation(email, password, company_name)
    sys.exit(0 if success else 1)

