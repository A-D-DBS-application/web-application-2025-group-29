from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
import re
from urllib.parse import unquote_plus
from .config import supabase, Config
from supabase import create_client
bp = Blueprint('routes', __name__)

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def validate_password(password):
    """Validate password strength"""
    if len(password) < 6:
        return False, "Wachtwoord moet minimaal 6 tekens lang zijn."
    return True, None

def get_authenticated_supabase():
    """Get Supabase client with session token if available"""
    # Always use a fresh client instance to avoid session conflicts
    client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    # If user has an access token in session, set it for authenticated requests
    if session.get('sb_access_token') and session.get('sb_refresh_token'):
        try:
            client.auth.set_session(access_token=session.get('sb_access_token'), refresh_token=session.get('sb_refresh_token'))
            # Verify the session is working by getting the user
            try:
                user = client.auth.get_user()
                print(f"✓ Authenticated Supabase client - User: {user.user.email if user.user else 'None'}")
            except Exception as verify_error:
                print(f"⚠ Session verification failed: {verify_error}")
        except Exception as e:
            print(f"⚠ Failed to set session on Supabase client: {e}")
            # If session setting fails, continue with unauthenticated client
            pass
    else:
        print(f"⚠ No session tokens in Flask session - using unauthenticated client")
    return client

def login_required(view_func):
    def wrapped(*args, **kwargs):
        if 'sb_user_id' not in session:
            flash("Je moet ingelogd zijn.", "error")
            return redirect(url_for('routes.login'))
        return view_func(*args, **kwargs)
    # Preserve function name for Flask debug
    wrapped.__name__ = view_func.__name__
    return wrapped


@bp.before_request
def load_current_user():
    """Load current user info into g for template access"""
    g.current_user_id = session.get('sb_user_id')
    g.current_user_email = session.get('email')
    g.current_user_type = session.get('user_type', 'customer')
    
    # For customers, get display name (first_name + last_name) instead of email
    if g.current_user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        if first_name and last_name:
            g.current_user_display_name = f"{first_name} {last_name}"
        else:
            # Fallback to email if name not available
            g.current_user_display_name = g.current_user_email
    else:
        # For companies and drivers, use email
        g.current_user_display_name = g.current_user_email


@bp.route('/')
def home():
    user_type = session.get('user_type', 'customer')
    user_email = session.get('email')
    
    # For companies, show company-specific home page with stats
    if user_type == 'company' and user_email:
        try:
            sb = get_authenticated_supabase()
            # Get company ID
            company_result = sb.table('Companies').select('id, name').eq('emailaddress', user_email).limit(1).execute()
            company_id = None
            company_name = None
            
            if company_result.data and len(company_result.data) > 0:
                company_id = company_result.data[0]['id']
                company_name = company_result.data[0].get('name', 'Bedrijf')
            
            # Get statistics for company
            stats = {
                'total_orders': 0,
                'pending_orders': 0,
                'recent_orders': []
            }
            
            if company_id:
                # Get total orders for this company
                orders_result = sb.table('Orders').select('id, deadline, created_at').eq('company_id', company_id).execute()
                if orders_result.data:
                    stats['total_orders'] = len(orders_result.data)
                    # Count orders without deadline or with future deadline as pending
                    today = datetime.now().date().isoformat()
                    stats['pending_orders'] = sum(1 for o in orders_result.data if not o.get('deadline') or o.get('deadline') >= today)
                    # Get 5 most recent orders
                    stats['recent_orders'] = sorted(orders_result.data, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
            
            return render_template('home.html', user_type='company', company_name=company_name, stats=stats)
        except Exception as e:
            print(f"Error loading company home: {e}")
            # Fall back to regular home if error
            return render_template('home.html', user_type='company', company_name=None, stats={'total_orders': 0, 'pending_orders': 0, 'recent_orders': []})
    
    # For drivers, show driver-specific home page with available routes
    if user_type == 'driver' and user_email:
        try:
            sb = get_authenticated_supabase()
            # Get driver's company_id
            driver_result = sb.table('Drivers').select('id, company_id').eq('email_address', user_email).limit(1).execute()
            driver_id = None
            company_id = None
            
            if driver_result.data and len(driver_result.data) > 0:
                driver_id = driver_result.data[0]['id']
                company_id = driver_result.data[0].get('company_id')
            
            # If no company assigned, redirect to select company
            if not company_id:
                return redirect(url_for('routes.driver_select_company'))
            
            # Get available routes (pending orders for this company)
            available_routes = []
            accepted_routes = []
            
            if company_id:
                print(f"🔍 Looking for routes for company_id: {company_id}")
                
                # Get pending routes (available to accept)
                pending_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('company_id', company_id).eq('status', 'pending').order('deadline', desc=False).limit(50).execute()
                
                print(f"📊 Found {len(pending_result.data) if pending_result.data else 0} pending routes for company {company_id}")
                
                if pending_result.data:
                    for order in pending_result.data:
                        route_info = {
                            'id': order.get('id'),
                            'deadline': order.get('deadline'),
                            'task_type': order.get('task_type'),
                            'product_type': order.get('product_type'),
                            'created_at': order.get('created_at'),
                            'status': 'pending',
                            'address': None,
                            'company': None
                        }
                        if order.get('Address'):
                            addr = order['Address']
                            route_info['address'] = {
                                'street_name': addr.get('street_name'),
                                'house_number': addr.get('house_number'),
                                'city': addr.get('city'),
                                'phone_number': addr.get('phone_number')
                            }
                        if order.get('Companies'):
                            company = order['Companies']
                            route_info['company'] = {
                                'name': company.get('name')
                            }
                        available_routes.append(route_info)
                
                # Get accepted routes by this driver (with navigation button)
                if driver_id:
                    accepted_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('driver_id', driver_id).eq('status', 'accepted').order('deadline', desc=False).limit(50).execute()
                    
                    print(f"✅ Found {len(accepted_result.data) if accepted_result.data else 0} accepted routes for driver {driver_id}")
                    
                    if accepted_result.data:
                        for order in accepted_result.data:
                            route_info = {
                                'id': order.get('id'),
                                'deadline': order.get('deadline'),
                                'task_type': order.get('task_type'),
                                'product_type': order.get('product_type'),
                                'created_at': order.get('created_at'),
                                'status': 'accepted',
                                'address': None,
                                'company': None
                            }
                            if order.get('Address'):
                                addr = order['Address']
                                route_info['address'] = {
                                    'street_name': addr.get('street_name'),
                                    'house_number': addr.get('house_number'),
                                    'city': addr.get('city'),
                                    'phone_number': addr.get('phone_number')
                                }
                            if order.get('Companies'):
                                company = order['Companies']
                                route_info['company'] = {
                                    'name': company.get('name')
                                }
                            accepted_routes.append(route_info)
            
            return render_template('home.html', user_type='driver', available_routes=available_routes, accepted_routes=accepted_routes, company_id=company_id, driver_id=driver_id)
        except Exception as e:
            print(f"Error loading driver home: {e}")
            import traceback
            traceback.print_exc()
            return render_template('home.html', user_type='driver', available_routes=[], accepted_routes=[], company_id=None, driver_id=None)
    
    # For customers and others, show regular home page
    return render_template('home.html', user_type=user_type)


@bp.route('/debug-login')
def debug_login():
    """Debug page to test login form submission"""
    return render_template('debug_login.html')


@bp.route('/select-role')
def select_role():
    return render_template('select_role.html')


@bp.route('/choose-auth', methods=['GET', 'POST'])
def choose_auth():
    if request.method == 'POST':
        user_type = request.form.get('user_type', 'customer')
        if user_type not in ['company', 'customer', 'driver']:
            user_type = 'customer'
        # Store in session temporarily
        session['selected_user_type'] = user_type
        return render_template('choose_auth.html', user_type=user_type)
    
    # GET request - check if user_type is in session or query param
    user_type = request.args.get('user_type') or session.get('selected_user_type', 'customer')
    if user_type not in ['company', 'customer', 'driver']:
        return redirect(url_for('routes.select_role'))
    
    session['selected_user_type'] = user_type
    return render_template('choose_auth.html', user_type=user_type)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Get user_type from query parameter, form, or session
    user_type = request.args.get('user_type') or request.form.get('user_type') or session.get('selected_user_type', 'customer')
    if user_type not in ['company', 'customer', 'driver']:
        user_type = 'customer'
    
    # Debug logging
    print(f"Login route called - Method: {request.method}, User type: {user_type}")
    
    if request.method == 'POST':
        print(f"POST request received - Form data: {dict(request.form)}")
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validation
        if not email:
            flash("E-mailadres is verplicht.", "error")
            return render_template('login.html', user_type=user_type)
        
        if not password:
            flash("Wachtwoord is verplicht.", "error")
            return render_template('login.html', user_type=user_type)
        
        if not validate_email(email):
            flash("Voer een geldig e-mailadres in (bijv. naam@voorbeeld.com).", "error")
            return render_template('login.html', user_type=user_type)

        try:
            print(f"Attempting login for email: {email}")
            if supabase is None:
                print("ERROR: Supabase client is None!")
                flash("Supabase is niet geconfigureerd. Neem contact op met de beheerder.", "error")
                return render_template('login.html', user_type=user_type)
            
            print("Calling supabase.auth.sign_in_with_password...")
            try:
                result = supabase.auth.sign_in_with_password({"email": email, "password": password})
            except Exception as login_error:
                # Check if error is about email verification
                error_str = str(login_error).lower()
                if "email not confirmed" in error_str or "email_confirmed_at" in error_str or "email verification" in error_str:
                    # Email verification error - try to work around it
                    print(f"Email verification error detected, attempting workaround...")
                    # Try to sign in with a different approach that might bypass verification
                    # Or show a helpful message
                    flash("Email verificatie is nog vereist in Supabase. Schakel 'Confirm email' uit in Supabase Dashboard > Auth > Providers > Email, of bevestig je email via de link in je inbox.", "error")
                    return render_template('login.html', user_type=user_type)
                else:
                    # Re-raise other errors
                    raise
            
            print(f"Supabase response received, user: {result.user}")
            user = result.user
            
            if user is None:
                flash("Ongeldige inloggegevens. Controleer je e-mail en wachtwoord.", "error")
                return render_template('login.html', user_type=user_type)
            
            # Check if email is confirmed (disabled for development - can be re-enabled in production)
            # For development, we skip email verification check
            # if not user.email_confirmed_at:
            #     flash("Je e-mailadres is nog niet bevestigd. Controleer je inbox en klik op de verificatielink.", "error")
            #     return render_template('login.html', user_type=user_type)

            # Persist minimal user info and session tokens for future API calls/refresh
            # Explicitly mark session as modified for Safari compatibility
            session['sb_user_id'] = user.id
            session['email'] = email
            session['user_type'] = user_type
            
            if getattr(result, 'session', None):
                session['sb_access_token'] = result.session.access_token
                session['sb_refresh_token'] = result.session.refresh_token
            
            # Force session to be saved (important for Safari)
            session.modified = True

            # If customer, ensure they exist in Client table and get name
            if user_type == 'customer':
                try:
                    sb = get_authenticated_supabase()
                    # Check if client exists and get name
                    client_result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', email).limit(1).execute()
                    
                    client_id = None
                    if client_result.data and len(client_result.data) > 0:
                        client_id = client_result.data[0]['id']
                        first_name = client_result.data[0].get('Name', '')
                        last_name = client_result.data[0].get('Lastname', '')
                        session['first_name'] = first_name
                        session['last_name'] = last_name
                        print(f"✓ Client found with ID {client_id}, Name: {first_name} {last_name}")
                    else:
                        # Create Client record if it doesn't exist (without name, will be updated later)
                        new_client = sb.table('Client').insert({
                            "emailaddress": email,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        if new_client.data:
                            client_id = new_client.data[0]['id']
                            print(f"✓ Client created during login with ID {client_id} (name not set yet)")
                    
                    # Store client_id in session for later use
                    if client_id:
                        session['client_id'] = client_id
                except Exception as e:
                    # Log but don't fail login
                    print(f"Warning: Could not create/check client record: {e}")

            # If company, ensure they exist in Companies and Farmer tables
            if user_type == 'company':
                try:
                    sb = get_authenticated_supabase()
                    # Check if company exists
                    company_result = sb.table('Companies').select('id').eq('emailaddress', email).limit(1).execute()
                    
                    company_id = None
                    if company_result.data and len(company_result.data) > 0:
                        company_id = company_result.data[0]['id']
                    else:
                        # Create Company record if it doesn't exist
                        # Try to get company name from user metadata if available
                        company_name = email.split('@')[0].capitalize()  # Default to email prefix
                        if hasattr(user, 'user_metadata') and user.user_metadata:
                            if 'company_name' in user.user_metadata:
                                company_name = user.user_metadata['company_name']
                        
                        new_company = sb.table('Companies').insert({
                            "name": company_name,
                            "emailaddress": email,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        if new_company.data:
                            company_id = new_company.data[0]['id']
                            print(f"✓ Company '{company_name}' created during login with ID {company_id}")
                    
                    # Check if farmer exists
                    farmer_result = sb.table('Farmer').select('id').eq('emailadress', email).limit(1).execute()
                    if not farmer_result.data or len(farmer_result.data) == 0:
                        # Create farmer record linked to company
                        farmer_data = {
                            "emailadress": email,
                            "created_at": datetime.utcnow().isoformat()
                        }
                        if company_id:
                            farmer_data["company_id"] = company_id
                        sb.table('Farmer').insert(farmer_data).execute()
                except Exception as e:
                    # Log but don't fail login
                    print(f"Warning: Could not create/check company record: {e}")
            
            flash("Succesvol ingelogd! Welkom terug.", "success")
            # Redirect based on user type
            if user_type == 'company':
                return redirect(url_for('routes.company_dashboard'))
            elif user_type == 'driver':
                return redirect(url_for('routes.driver_dashboard'))
            else:
                return redirect(url_for('routes.profile'))
            
        except Exception as e:
            # Better error extraction from Supabase Python client
            error_msg = ""
            error_dict = {}
            
            # Try to extract error from Supabase exception
            if hasattr(e, 'message'):
                error_msg = str(e.message)
            elif hasattr(e, 'args') and len(e.args) > 0:
                error_msg = str(e.args[0])
            else:
                error_msg = str(e)
            
            # Check for Supabase API error response
            if hasattr(e, 'response'):
                try:
                    if hasattr(e.response, 'json'):
                        error_dict = e.response.json()
                        if 'message' in error_dict:
                            error_msg = error_dict['message']
                        elif 'error' in error_dict:
                            if isinstance(error_dict['error'], dict):
                                if 'message' in error_dict['error']:
                                    error_msg = error_dict['error']['message']
                            else:
                                error_msg = str(error_dict['error'])
                except:
                    pass
            
            # Log full error for debugging
            import traceback
            print(f"Login error: {type(e).__name__}: {error_msg}")
            print(f"Full exception: {e}")
            print(f"Traceback: {traceback.format_exc()}")
            
            error_lower = error_msg.lower()
            # Provide more specific error messages
            if "invalid login credentials" in error_lower or ("invalid" in error_lower and "credentials" in error_lower):
                flash("Ongeldige inloggegevens. Controleer je e-mailadres en wachtwoord.", "error")
            elif "email logins are disabled" in error_lower or "email provider disabled" in error_lower:
                flash("Email authenticatie is uitgeschakeld in Supabase. Ga naar Dashboard > Auth > Providers > Email en schakel de Email provider AAN (maar laat 'Confirm email' UIT staan).", "error")
            elif "email not confirmed" in error_lower or "email_confirmed_at" in error_lower or "email verification" in error_lower:
                # Email verification is still required by Supabase
                # User needs to either disable it in dashboard or confirm email
                flash("Email verificatie is nog vereist in Supabase. Ga naar Supabase Dashboard > Auth > Providers > Email en schakel 'Confirm email' UIT, of bevestig je email via de link in je inbox.", "error")
            elif "too many requests" in error_lower or "rate limit" in error_lower:
                flash("Te veel pogingen. Wacht even en probeer het later opnieuw.", "error")
            else:
                # Show user-friendly message but log full details
                flash(f"Inloggen mislukt. Error: {error_msg[:100]}. Probeer het later opnieuw of neem contact op als het probleem aanhoudt.", "error")
            return render_template('login.html', user_type=user_type)

    return render_template('login.html', user_type=user_type)


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    # Get user_type from query parameter, form, or session
    user_type = request.args.get('user_type') or request.form.get('user_type') or session.get('selected_user_type', 'customer')
    if user_type not in ['company', 'customer', 'driver']:
        user_type = 'customer'
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        
        # Validation
        if not email:
            flash("E-mailadres is verplicht.", "error")
            return render_template('signup.html', user_type=user_type)
        
        if not password:
            flash("Wachtwoord is verplicht.", "error")
            return render_template('signup.html', user_type=user_type)
        
        if not validate_email(email):
            flash("Voer een geldig e-mailadres in (bijv. naam@voorbeeld.com).", "error")
            return render_template('signup.html', user_type=user_type)
        
        is_valid, password_error = validate_password(password)
        if not is_valid:
            flash(password_error, "error")
            return render_template('signup.html', user_type=user_type)

        try:
            if supabase is None:
                flash("Supabase is niet geconfigureerd. Neem contact op met de beheerder.", "error")
                return render_template('signup.html', user_type=user_type)
            
            # Specify redirect URL for email verification (use port 5000 where Flask runs)
            redirect_url = request.url_root.rstrip('/')  # Get current base URL (e.g., http://localhost:5000)
            result = supabase.auth.sign_up({
                "email": email, 
                "password": password,
                "options": {
                    "email_redirect_to": f"{redirect_url}/login"
                }
            })
            
            if result.user is None:
                flash("Registratie mislukt. Het account kon niet worden aangemaakt. Probeer het opnieuw.", "error")
                return render_template('signup.html', user_type=user_type)

            # If customer, create Client record in Supabase
            if user_type == 'customer':
                # Get first name and last name from form (required for customers)
                first_name = request.form.get('first_name', '').strip()
                last_name = request.form.get('last_name', '').strip()
                
                if not first_name:
                    flash("Voornaam is verplicht voor klant accounts.", "error")
                    return render_template('signup.html', user_type=user_type)
                if not last_name:
                    flash("Achternaam is verplicht voor klant accounts.", "error")
                    return render_template('signup.html', user_type=user_type)
                
                try:
                    # Sign in immediately after signup to get proper session tokens
                    print(f"Signing in after signup to get session for client creation...")
                    signin_result = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    
                    if not signin_result.session:
                        print(f"✗ Failed to get session after signup")
                        flash("Account aangemaakt, maar kon niet inloggen. Probeer opnieuw in te loggen.", "warning")
                        return redirect(url_for('routes.login', user_type=user_type))
                    
                    # Store session tokens
                    session['sb_access_token'] = signin_result.session.access_token
                    session['sb_refresh_token'] = signin_result.session.refresh_token
                    session['sb_user_id'] = signin_result.user.id
                    session['email'] = email
                    session['user_type'] = user_type
                    session.modified = True
                    print(f"✓ Session obtained for client creation - Access token: {signin_result.session.access_token[:20]}...")
                    
                    # Create a fresh authenticated client with the session (don't use get_authenticated_supabase here)
                    sb = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                    sb.auth.set_session(
                        access_token=signin_result.session.access_token,
                        refresh_token=signin_result.session.refresh_token
                    )
                    
                    # Verify authentication before proceeding
                    try:
                        auth_user = sb.auth.get_user()
                        print(f"✓ Verified authenticated user: {auth_user.user.email if auth_user.user else 'None'}")
                        if not auth_user.user or auth_user.user.email != email:
                            print(f"✗ Authentication mismatch: expected {email}, got {auth_user.user.email if auth_user.user else 'None'}")
                            flash("Account aangemaakt, maar authenticatie mislukt. Log opnieuw in.", "warning")
                            return redirect(url_for('routes.login', user_type=user_type))
                    except Exception as auth_error:
                        print(f"✗ Authentication verification failed: {auth_error}")
                        import traceback
                        traceback.print_exc()
                        flash("Account aangemaakt, maar authenticatie mislukt. Log opnieuw in.", "warning")
                        return redirect(url_for('routes.login', user_type=user_type))
                    
                    # Check if client already exists
                    existing_client = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', email).limit(1).execute()
                    
                    if existing_client.data and len(existing_client.data) > 0:
                        client_id = existing_client.data[0]['id']
                        session['client_id'] = client_id
                        # Update name if different
                        if existing_client.data[0].get('Name') != first_name or existing_client.data[0].get('Lastname') != last_name:
                            sb.table('Client').update({
                                "Name": first_name,
                                "Lastname": last_name
                            }).eq('id', client_id).execute()
                        session['first_name'] = first_name
                        session['last_name'] = last_name
                        print(f"✓ Client already exists with ID {client_id}, name updated")
                    else:
                        # Create Client record with name and lastname
                        print(f"Creating Client record for {email} with Name: {first_name}, Lastname: {last_name}")
                        try:
                            client_result = sb.table('Client').insert({
                                "emailaddress": email,
                                "Name": first_name,
                                "Lastname": last_name,
                                "created_at": datetime.utcnow().isoformat()
                            }).execute()
                            
                            print(f"Client insert result: {client_result}")
                            
                            if client_result.data and len(client_result.data) > 0:
                                client_id = client_result.data[0]['id']
                                session['client_id'] = client_id
                                session['first_name'] = first_name
                                session['last_name'] = last_name
                                print(f"✓ Client successfully created with ID {client_id}, Name: {first_name} {last_name}")
                            else:
                                print(f"✗ Client creation returned no data: {client_result}")
                                flash("Account aangemaakt, maar klantgegevens konden niet worden opgeslagen. Log opnieuw in om dit te corrigeren.", "warning")
                        except Exception as insert_error:
                            print(f"✗ Error during Client insert: {insert_error}")
                            import traceback
                            traceback.print_exc()
                            flash("Account aangemaakt, maar klantgegevens konden niet worden opgeslagen. Log opnieuw in om dit te corrigeren.", "warning")
                except Exception as e:
                    print(f"Warning: Could not create client record: {e}")
                    import traceback
                    traceback.print_exc()
                    flash("Account aangemaakt, maar klantgegevens konden niet worden opgeslagen. Log opnieuw in om dit te corrigeren.", "warning")

            # If company, create Company record and Farmer record in Supabase
            # We need to sign in first to get proper authentication for RLS
            if user_type == 'company':
                # Get company name from form (required for company signup)
                company_name = request.form.get('company_name', '').strip()
                if not company_name:
                    flash("Bedrijfsnaam is verplicht voor bedrijf accounts.", "error")
                    return render_template('signup.html', user_type=user_type)
                
                company_id = None
                try:
                    # Sign in immediately after signup to get proper session tokens
                    # This is necessary because signup doesn't always return a session
                    print(f"Signing in after signup to get session for company creation...")
                    signin_result = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    
                    if signin_result.session:
                        # Store session tokens
                        session['sb_access_token'] = signin_result.session.access_token
                        session['sb_refresh_token'] = signin_result.session.refresh_token
                        session['sb_user_id'] = signin_result.user.id
                        session['email'] = email
                        session['user_type'] = user_type
                        session.modified = True
                        print(f"✓ Session obtained for company creation")
                        
                        # Now use authenticated client to create company
                        sb = get_authenticated_supabase()
                        
                        # Verify authentication by checking current user
                        try:
                            current_user_check = sb.auth.get_user()
                            print(f"✓ Verified authentication - Current user: {current_user_check.user.email if current_user_check.user else 'None'}")
                            if current_user_check.user and current_user_check.user.email != email:
                                print(f"⚠ Warning: Authenticated as {current_user_check.user.email}, but signing up as {email}")
                        except Exception as verify_error:
                            print(f"⚠ Could not verify authentication: {verify_error}")
                        
                        # Check if company already exists
                        print(f"Checking if company exists for {email}...")
                        existing_company = sb.table('Companies').select('id').eq('emailaddress', email).limit(1).execute()
                        
                        if existing_company.data and len(existing_company.data) > 0:
                            company_id = existing_company.data[0]['id']
                            # Update company name if it exists but name is different
                            sb.table('Companies').update({
                                "name": company_name
                            }).eq('id', company_id).execute()
                            print(f"✓ Company exists, name updated to '{company_name}'")
                        else:
                            # Create Company record with provided company name
                            print(f"Creating company '{company_name}' for {email}...")
                            print(f"  Using authenticated client with email: {email}")
                            
                            try:
                                company_result = sb.table('Companies').insert({
                                    "name": company_name,
                                    "emailaddress": email,
                                    "created_at": datetime.utcnow().isoformat()
                                }).execute()
                                
                                if company_result.data and len(company_result.data) > 0:
                                    company_id = company_result.data[0]['id']
                                    print(f"✓ Company '{company_name}' successfully created with ID {company_id}")
                                else:
                                    print(f"✗ Company creation returned no data")
                                    print(f"  Response: {company_result}")
                            except Exception as insert_error:
                                print(f"✗ Error during company insert: {insert_error}")
                                import traceback
                                traceback.print_exc()
                                raise  # Re-raise to be caught by outer exception handler
                        
                        # Create farmer record linked to company
                        if company_id:
                            farmer_data = {
                                "emailadress": email,
                                "created_at": datetime.utcnow().isoformat(),
                                "company_id": company_id
                            }
                            sb.table('Farmer').insert(farmer_data).execute()
                            print(f"✓ Farmer record created and linked to company {company_id}")
                            
                            flash(f"Account en bedrijf '{company_name}' succesvol aangemaakt!", "success")
                        else:
                            flash(f"Account aangemaakt, maar bedrijf '{company_name}' kon niet worden aangemaakt. Log in om het bedrijf aan te maken.", "warning")
                    else:
                        print(f"⚠ No session returned from signin after signup")
                        flash(f"Account aangemaakt. Log in om het bedrijf '{company_name}' aan te maken.", "warning")
                        
                except Exception as e:
                    error_msg = str(e)
                    print(f"✗ Error creating company during signup: {error_msg}")
                    import traceback
                    traceback.print_exc()
                    flash(f"Account aangemaakt. Log in om het bedrijf '{company_name}' aan te maken.", "warning")
            else:
                # Not a company user - show success message
                # Store session tokens if available from signup
                if getattr(result, 'session', None):
                    session['sb_access_token'] = result.session.access_token
                    session['sb_refresh_token'] = result.session.refresh_token
                    session['sb_user_id'] = result.user.id
                    session['email'] = email
                    session['user_type'] = user_type
                    session.modified = True
                flash(f"Account aangemaakt voor {email}! Controleer je inbox en klik op de verificatielink om je e-mailadres te bevestigen.", "success")
            
            return redirect(url_for('routes.login', user_type=user_type))
            
        except Exception as e:
            # Extract error message from Supabase exception
            error_msg = ""
            error_dict = {}
            
            # Try to get error from Supabase exception structure
            if hasattr(e, 'message'):
                error_msg = str(e.message)
            elif hasattr(e, 'args') and len(e.args) > 0:
                error_msg = str(e.args[0])
            else:
                error_msg = str(e)
            
            # Check if it's a Supabase API error response (common structure)
            if hasattr(e, 'response'):
                try:
                    if hasattr(e.response, 'json'):
                        error_dict = e.response.json()
                        if 'message' in error_dict:
                            error_msg = error_dict['message']
                        elif 'error' in error_dict:
                            if isinstance(error_dict['error'], dict):
                                if 'message' in error_dict['error']:
                                    error_msg = error_dict['error']['message']
                            else:
                                error_msg = str(error_dict['error'])
                    elif hasattr(e.response, 'text'):
                        # Sometimes it's plain text
                        error_msg = e.response.text
                except Exception as parse_error:
                    print(f"Error parsing response: {parse_error}")
            
            # Also check if error is a dict-like object
            if isinstance(e, dict):
                if 'message' in e:
                    error_msg = e['message']
                elif 'error' in e:
                    error_msg = str(e['error'])
            
            # Log full error for debugging
            print(f"Signup error: {type(e).__name__}: {error_msg}")
            print(f"Full exception: {e}")
            if error_dict:
                print(f"Error dict: {error_dict}")
            
            # Provide more specific error messages
            error_lower = error_msg.lower()
            if "user already registered" in error_lower or "already exists" in error_lower or "duplicate" in error_lower:
                flash(f"Dit e-mailadres ({email}) is al geregistreerd. Gebruik een ander e-mailadres of log in met je bestaande account.", "error")
            elif "invalid email" in error_lower or ("email" in error_lower and "invalid" in error_lower):
                # Check if it's actually a valid email format according to our validation
                if validate_email(email):
                    # Our validation passed, but Supabase rejected it - could be domain validation or config issue
                    flash(f"Het e-mailadres '{email}' heeft een geldig formaat, maar wordt door Supabase afgewezen. Dit kan komen door: (1) strikte domeinvalidatie in Supabase, (2) het e-mailadres bestaat niet, of (3) een configuratieprobleem. Probeer een ander e-mailadres of controleer de Supabase-instellingen.", "error")
                else:
                    flash("Ongeldig e-mailadres. Controleer de spelling en probeer het opnieuw.", "error")
            elif "password" in error_lower and ("weak" in error_lower or "strength" in error_lower):
                flash("Wachtwoord is te zwak. Gebruik minimaal 6 tekens en combineer letters en cijfers.", "error")
            elif "too many requests" in error_lower or "rate limit" in error_lower:
                flash("Te veel pogingen. Wacht even en probeer het later opnieuw.", "error")
            else:
                # Show the actual error message but in a user-friendly way
                flash(f"Registratie mislukt: {error_msg}. Probeer het later opnieuw of neem contact op als het probleem aanhoudt.", "error")
            return render_template('signup.html', user_type=user_type)

    return render_template('signup.html', user_type=user_type)


@bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    # Check for error in URL (Supabase redirects with hash fragments that get converted)
    error_code = request.args.get('error_code') or request.args.get('error')
    error_description = request.args.get('error_description')
    
    if error_code:
        # Decode URL-encoded error description
        if error_description:
            error_description = unquote_plus(error_description)
        
        if error_code == 'otp_expired' or 'expired' in str(error_code).lower():
            if error_description:
                flash(f"De reset link is verlopen: {error_description}. Vraag een nieuwe reset link aan.", "error")
            else:
                flash("De reset link is verlopen. Vraag een nieuwe reset link aan.", "error")
        elif error_code == 'access_denied':
            if error_description:
                flash(f"Toegang geweigerd: {error_description}. De reset link is mogelijk ongeldig of reeds gebruikt.", "error")
            else:
                flash("Toegang geweigerd. De reset link is mogelijk ongeldig of reeds gebruikt.", "error")
        elif error_description:
            flash(f"Fout: {error_description}. Vraag een nieuwe reset link aan.", "error")
        else:
            flash(f"Er is een fout opgetreden ({error_code}). Vraag een nieuwe reset link aan.", "error")
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        
        if not email:
            flash("E-mailadres is verplicht.", "error")
            return render_template('forgot_password.html')
        
        if not validate_email(email):
            flash("Voer een geldig e-mailadres in (bijv. naam@voorbeeld.com).", "error")
            return render_template('forgot_password.html')
        
        try:
            # Get redirect URL for password reset
            redirect_url = request.url_root.rstrip('/')
            result = supabase.auth.reset_password_for_email(
                email,
                {
                    "redirect_to": f"{redirect_url}/reset-password"
                }
            )
            
            # Supabase doesn't throw an error if email doesn't exist (security)
            flash(f"Als het e-mailadres '{email}' bestaat, hebben we een wachtwoord reset link gestuurd. Controleer je inbox (en spam folder).", "success")
            return redirect(url_for('routes.login'))
            
        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            if "too many requests" in error_lower or "rate limit" in error_lower:
                flash("Te veel pogingen. Wacht even en probeer het later opnieuw.", "error")
            else:
                flash(f"Fout bij het versturen van reset link: {error_msg}. Probeer het later opnieuw.", "error")
            return render_template('forgot_password.html')
    
    return render_template('forgot_password.html')


@bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    # Debug logging
    print(f"Reset password route called - Method: {request.method}")
    print(f"Query args: {dict(request.args)}")
    
    # Check for errors in URL (from Supabase redirects)
    error_code = request.args.get('error_code') or request.args.get('error')
    error_description = request.args.get('error_description')
    
    if error_code:
        # Decode URL-encoded error description
        if error_description:
            error_description = unquote_plus(error_description)
        
        # Redirect to forgot-password with error message
        if error_code == 'otp_expired' or 'expired' in str(error_code).lower():
            flash("De reset link is verlopen. Vraag een nieuwe reset link aan.", "error")
        elif error_code == 'access_denied':
            flash("Toegang geweigerd. De reset link is mogelijk ongeldig of reeds gebruikt.", "error")
        elif error_description:
            flash(f"Fout: {error_description.replace('+', ' ')}", "error")
        else:
            flash(f"Er is een fout opgetreden: {error_code}. Vraag een nieuwe reset link aan.", "error")
        return redirect(url_for('routes.forgot_password'))
    
    # Get token from query parameters (Supabase sends this in the email link)
    # Supabase can send either token_hash or access_token
    token_hash = request.args.get('token_hash')
    access_token = request.args.get('access_token')
    type_param = request.args.get('type', 'recovery')
    
    # If no token found, show error but still render template (JS will handle hash conversion)
    if not token_hash and not access_token:
        print("WARNING: No token_hash or access_token found in query parameters")
        # Don't redirect immediately - let JS convert hash fragments first
        return render_template('reset_password.html', token_hash=None, type=None)
    
    if type_param != 'recovery':
        flash("Ongeldige reset link type. Vraag een nieuwe reset link aan.", "error")
        return redirect(url_for('routes.forgot_password'))
    
    if request.method == 'POST':
        # Get tokens from form if not in URL (they might be in hidden form fields)
        form_token_hash = request.form.get('token_hash') or token_hash
        form_access_token = request.form.get('access_token') or access_token
        form_type = request.form.get('type') or type_param
        
        password = request.form.get('password', '')
        password_confirm = request.form.get('password_confirm', '')
        
        print(f"POST request - token_hash: {bool(form_token_hash)}, access_token: {bool(form_access_token)}, type: {form_type}")
        
        if not password:
            flash("Wachtwoord is verplicht.", "error")
            return render_template('reset_password.html', token_hash=form_token_hash or form_access_token, type=form_type)
        
        if password != password_confirm:
            flash("Wachtwoorden komen niet overeen.", "error")
            return render_template('reset_password.html', token_hash=form_token_hash or form_access_token, type=form_type)
        
        is_valid, password_error = validate_password(password)
        if not is_valid:
            flash(password_error, "error")
            return render_template('reset_password.html', token_hash=form_token_hash or form_access_token, type=form_type)
        
        # Use form values
        token_hash = form_token_hash
        access_token = form_access_token
        type_param = form_type
        
        try:
            print(f"Attempting password reset with token_hash: {bool(token_hash)}, access_token: {bool(access_token)}")
            
            # If we have access_token, use exchange_code_for_session or update_user directly
            if access_token:
                print("Using access_token method for password reset")
                # Create a client with the access token
                sb_client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
                # Set the session with the access token
                try:
                    # Try to exchange the access token for a session
                    # Or use update_user with the access token
                    # Supabase Python client might need different approach
                    # For now, try verify_otp with token_hash if available
                    if token_hash:
                        result = sb_client.auth.verify_otp({
                            "token_hash": token_hash,
                            "type": type_param
                        })
                    else:
                        # If only access_token, we need to set it as session
                        # This is tricky - Supabase might have sent it differently
                        # Try using exchange_code_for_session or update_user
                        flash("Reset link format niet ondersteund. Probeer de link opnieuw of vraag een nieuwe aan.", "error")
                        return render_template('reset_password.html', token_hash=token_hash, type=type_param)
                except Exception as e:
                    print(f"Error with access_token method: {e}")
                    # Fall back to token_hash method
                    if not token_hash:
                        raise
            
            # Use token_hash method (standard Supabase password reset)
            if token_hash:
                print("Using token_hash method for password reset")
                result = supabase.auth.verify_otp({
                    "token_hash": token_hash,
                    "type": type_param
                })
            else:
                raise Exception("No token_hash or access_token provided")
            
            if result and result.user and result.session:
                print(f"OTP verified successfully for user: {result.user.email}")
                # Store session temporarily to update password
                session['sb_user_id'] = result.user.id
                session['email'] = result.user.email
                session['sb_access_token'] = result.session.access_token
                session['sb_refresh_token'] = result.session.refresh_token
                
                # Update the password while authenticated
                print(f"Updating password for user: {result.user.email}")
                # Use the authenticated client for password update
                authenticated_sb = get_authenticated_supabase()
                update_result = authenticated_sb.auth.update_user({
                    "password": password
                })
                
                if update_result.user:
                    print(f"Password updated successfully for user: {update_result.user.email}")
                    # Clear session after password update (user needs to login again)
                    session.clear()
                    flash("Wachtwoord succesvol gewijzigd! Je kunt nu inloggen met je nieuwe wachtwoord.", "success")
                    return redirect(url_for('routes.login'))
                else:
                    print("Password update failed - no user in result")
                    session.clear()
                    flash("Wachtwoord kon niet worden gewijzigd. Probeer het opnieuw.", "error")
            else:
                print("OTP verification failed - no user or session")
                flash("Reset link is ongeldig of verlopen. Vraag een nieuwe reset link aan.", "error")
                return redirect(url_for('routes.forgot_password'))
                
        except Exception as e:
            error_msg = str(e)
            error_lower = error_msg.lower()
            
            if "expired" in error_lower or "invalid" in error_lower:
                flash("Reset link is ongeldig of verlopen. Vraag een nieuwe reset link aan.", "error")
                return redirect(url_for('routes.forgot_password'))
            else:
                flash(f"Fout bij het resetten van wachtwoord: {error_msg}. Probeer het later opnieuw.", "error")
            return render_template('reset_password.html', token_hash=token_hash or access_token, type=type_param)
    
    # Render template with token info (use token_hash if available, otherwise access_token)
    return render_template('reset_password.html', token_hash=token_hash or access_token, type=type_param)


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_type = session.get('user_type', 'customer')
    # Redirect company and driver to their dashboards
    if user_type == 'company':
        return redirect(url_for('routes.company_dashboard'))
    elif user_type == 'driver':
        return redirect(url_for('routes.driver_dashboard'))
    
    # For customers, get name from session or Client table
    user_ctx = {
        "emailaddress": session.get('email', ''),
        "user_type": user_type
    }
    
    # For customers, add name information
    if user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        if first_name or last_name:
            user_ctx['first_name'] = first_name
            user_ctx['last_name'] = last_name
            user_ctx['display_name'] = f"{first_name} {last_name}".strip()
        else:
            # Try to get name from Client table if not in session
            try:
                sb = get_authenticated_supabase()
                client_id = session.get('client_id')
                if client_id:
                    client_result = sb.table('Client').select('Name, Lastname').eq('id', client_id).limit(1).execute()
                    if client_result.data and len(client_result.data) > 0:
                        first_name = client_result.data[0].get('Name', '')
                        last_name = client_result.data[0].get('Lastname', '')
                        if first_name or last_name:
                            user_ctx['first_name'] = first_name
                            user_ctx['last_name'] = last_name
                            user_ctx['display_name'] = f"{first_name} {last_name}".strip()
                            session['first_name'] = first_name
                            session['last_name'] = last_name
            except Exception as e:
                print(f"Warning: Could not get client name: {e}")
    
    return render_template('profile.html', user=user_ctx)


@bp.route('/customer/orders')
@login_required
def customer_orders():
    """Show customer's own orders only"""
    user_type = session.get('user_type', 'customer')
    if user_type != 'customer':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        customer_email = session.get('email')
        
        # Get only orders placed by this customer (filtered by customer_email)
        orders_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('customer_email', customer_email).order('created_at', desc=True).limit(100).execute()
        
        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = {
                    'id': order.get('id'),
                    'deadline': order.get('deadline'),
                    'task_type': order.get('task_type'),
                    'product_type': order.get('product_type'),
                    'created_at': order.get('created_at'),
                    'address': None,
                    'company': None
                }
                # Get address if available
                if order.get('Address'):
                    addr = order['Address']
                    order_info['address'] = {
                        'street_name': addr.get('street_name'),
                        'house_number': addr.get('house_number'),
                        'city': addr.get('city'),
                        'phone_number': addr.get('phone_number')
                    }
                # Get company name if available
                if order.get('Companies'):
                    company = order['Companies']
                    order_info['company'] = {
                        'name': company.get('name'),
                        'id': company.get('id')
                    }
                orders.append(order_info)
        
        return render_template('customer_orders.html', orders=orders, user_email=customer_email)
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('customer_orders.html', orders=[], user_email=session.get('email', ''))


@bp.route('/customer/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_order(order_id):
    """Edit an existing order - only the owner can edit"""
    user_type = session.get('user_type', 'customer')
    if user_type != 'customer':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    sb = get_authenticated_supabase()
    customer_email = session.get('email')
    
    try:
        # Get the order and verify it belongs to the current customer
        order_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('id', order_id).eq('customer_email', customer_email).limit(1).execute()
        
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order_data = order_result.data[0]
        
        # Get all companies for the dropdown
        companies = []
        try:
            companies_result = sb.table('Companies').select('id, name, emailaddress').order('name').execute()
            if companies_result.data:
                companies = [
                    {'id': c['id'], 'name': c['name']} 
                    for c in companies_result.data
                ]
        except Exception as e:
            print(f"Error fetching companies: {e}")
            flash("Kon bedrijven niet ophalen. Probeer het later opnieuw.", "error")
        
        # Prepare order info for template
        order_info = {
            'id': order_data.get('id'),
            'deadline': order_data.get('deadline'),
            'task_type': order_data.get('task_type'),
            'product_type': order_data.get('product_type'),
            'created_at': order_data.get('created_at'),
            'address': None,
            'company': None,
            'address_id': order_data.get('address_id')
        }
        
        # Get address if available
        if order_data.get('Address'):
            addr = order_data['Address']
            order_info['address'] = {
                'street_name': addr.get('street_name'),
                'house_number': addr.get('house_number'),
                'city': addr.get('city'),
                'phone_number': addr.get('phone_number'),
                'id': addr.get('id')
            }
        
        # Get company name if available
        if order_data.get('Companies'):
            company = order_data['Companies']
            order_info['company'] = {
                'name': company.get('name'),
                'id': company.get('id')
            }
        
        if request.method == 'POST':
            try:
                # Get farmer_id from Supabase Farmer table (if exists)
                farmer_id = None
                if session.get('email'):
                    try:
                        farmer_result = sb.table('Farmer').select('id').eq('emailadress', session['email']).limit(1).execute()
                        if farmer_result.data and len(farmer_result.data) > 0:
                            farmer_id = farmer_result.data[0]['id']
                    except Exception:
                        pass  # Farmer may not exist yet, that's okay
                
                # Coerce house_number to integer if possible
                house_number_raw = request.form.get("house_number")
                try:
                    house_number_val = int(house_number_raw) if house_number_raw is not None else None
                except ValueError:
                    house_number_val = None
                
                # Update address via Supabase REST API
                address_update_data = {
                    "farmer_id": farmer_id,
                    "street_name": request.form.get("street_name"),
                    "house_number": house_number_val,
                    "city": request.form.get("city"),
                    "phone_number": request.form.get("phone_number")
                }
                
                # Update the existing address
                if order_info['address_id']:
                    address_update_result = sb.table('Address').update(address_update_data).eq('id', order_info['address_id']).execute()
                else:
                    # If no address_id, create a new address (shouldn't happen, but handle it)
                    address_result = sb.table('Address').insert(address_update_data).execute()
                    if address_result.data and len(address_result.data) > 0:
                        order_info['address_id'] = address_result.data[0]['id']
                
                # Get company_id from form (required field)
                company_id = request.form.get("company_id")
                if not company_id:
                    flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                    return render_template('edit_order.html', order=order_info, companies=companies)
                
                try:
                    company_id = int(company_id)
                except (ValueError, TypeError):
                    flash("Ongeldig bedrijf geselecteerd.", "error")
                    return render_template('edit_order.html', order=order_info, companies=companies)
                
                # Update order via Supabase REST API
                order_update_data = {
                    "deadline": request.form.get("deadline"),
                    "task_type": request.form.get("task_type"),
                    "product_type": request.form.get("product_type"),
                    "company_id": company_id
                }
                
                # Ensure address_id is set if we created a new address
                if order_info['address_id']:
                    order_update_data["address_id"] = order_info['address_id']
                
                order_update_result = sb.table('Orders').update(order_update_data).eq('id', order_id).eq('customer_email', customer_email).execute()
                
                if order_update_result.data:
                    flash("Bestelling bijgewerkt!", "success")
                    return redirect(url_for('routes.customer_orders'))
                else:
                    flash("Bestelling kon niet worden bijgewerkt.", "error")
            except Exception as e:
                flash(f"Fout bij het bijwerken van bestelling: {str(e)}", "error")
                import traceback
                traceback.print_exc()
                return render_template('edit_order.html', order=order_info, companies=companies)
        
        # GET request - show edit form
        return render_template('edit_order.html', order=order_info, companies=companies)
    
    except Exception as e:
        flash(f"Fout bij het ophalen van bestelling: {str(e)}", "error")
        import traceback
        traceback.print_exc()
        return redirect(url_for('routes.customer_orders'))


@bp.route('/company/dashboard')
@login_required
def company_dashboard():
    user_type = session.get('user_type', 'customer')
    if user_type != 'company':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        # Get company_id for the logged-in company
        company_email = session.get('email')
        company_id = None
        
        # Find the company ID for this company
        company_result = sb.table('Companies').select('id').eq('emailaddress', company_email).limit(1).execute()
        if company_result.data and len(company_result.data) > 0:
            company_id = company_result.data[0]['id']
        
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return render_template('company_dashboard.html', orders=[], user_email=company_email)
        
        # Get only orders for this company (filtered by company_id)
        orders_result = sb.table('Orders').select('*, Address(*)').eq('company_id', company_id).order('created_at', desc=True).limit(100).execute()
        
        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = {
                    'id': order.get('id'),
                    'deadline': order.get('deadline'),
                    'task_type': order.get('task_type'),
                    'product_type': order.get('product_type'),
                    'created_at': order.get('created_at'),
                    'address': None
                }
                # Get address if available
                if order.get('Address'):
                    addr = order['Address']
                    order_info['address'] = {
                        'street_name': addr.get('street_name'),
                        'house_number': addr.get('house_number'),
                        'city': addr.get('city'),
                        'phone_number': addr.get('phone_number')
                    }
                orders.append(order_info)
        
        return render_template('company_dashboard.html', orders=orders, user_email=session.get('email', ''))
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('company_dashboard.html', orders=[], user_email=session.get('email', ''))


@bp.route('/driver/select-company', methods=['GET', 'POST'])
@login_required
def driver_select_company():
    """Allow driver to select their company (one-time setup)"""
    user_type = session.get('user_type', 'customer')
    if user_type != 'driver':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    user_email = session.get('email')
    
    if request.method == 'POST':
        company_id = request.form.get('company_id')
        if not company_id:
            flash("Selecteer een bedrijf.", "error")
            return redirect(url_for('routes.driver_select_company'))
        
        try:
            sb = get_authenticated_supabase()
            # Get or create driver record
            driver_result = sb.table('Drivers').select('id').eq('email_address', user_email).limit(1).execute()
            
            if driver_result.data and len(driver_result.data) > 0:
                driver_id = driver_result.data[0]['id']
                # Update driver with company_id
                sb.table('Drivers').update({'company_id': int(company_id)}).eq('id', driver_id).execute()
            else:
                # Create new driver record
                sb.table('Drivers').insert({
                    'email_address': user_email,
                    'company_id': int(company_id),
                    'name': user_email.split('@')[0]  # Use email prefix as name
                }).execute()
            
            flash("Bedrijf succesvol geselecteerd!", "success")
            return redirect(url_for('routes.home'))
        except Exception as e:
            flash(f"Fout bij het selecteren van bedrijf: {str(e)}", "error")
            import traceback
            traceback.print_exc()
    
    # GET: Show company selection form
    try:
        sb = get_authenticated_supabase()
        # Get all companies
        companies_result = sb.table('Companies').select('id, name').order('name').execute()
        companies = companies_result.data if companies_result.data else []
        
        # Check if driver already has a company
        driver_result = sb.table('Drivers').select('company_id').eq('email_address', user_email).limit(1).execute()
        if driver_result.data and len(driver_result.data) > 0 and driver_result.data[0].get('company_id'):
            # Already has company, redirect to home
            return redirect(url_for('routes.home'))
        
        return render_template('driver_select_company.html', companies=companies)
    except Exception as e:
        flash(f"Fout bij het ophalen van bedrijven: {str(e)}", "error")
        return render_template('driver_select_company.html', companies=[])


@bp.route('/driver/accept-route/<int:order_id>', methods=['POST'])
@login_required
def driver_accept_route(order_id):
    """Accept a route (order)"""
    user_type = session.get('user_type', 'customer')
    if user_type != 'driver':
        flash("Je hebt geen toegang tot deze actie.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        user_email = session.get('email')
        
        # Get driver ID
        driver_result = sb.table('Drivers').select('id').eq('email_address', user_email).limit(1).execute()
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Chauffeur niet gevonden.", "error")
            return redirect(url_for('routes.home'))
        
        driver_id = driver_result.data[0]['id']
        
        # Update order status and assign to driver
        sb.table('Orders').update({
            'status': 'accepted',
            'driver_id': driver_id
        }).eq('id', order_id).execute()
        
        flash("Route geaccepteerd!", "success")
    except Exception as e:
        flash(f"Fout bij het accepteren van route: {str(e)}", "error")
        import traceback
        traceback.print_exc()
    
    return redirect(url_for('routes.home'))


@bp.route('/driver/reject-route/<int:order_id>', methods=['POST'])
@login_required
def driver_reject_route(order_id):
    """Reject a route (order)"""
    user_type = session.get('user_type', 'customer')
    if user_type != 'driver':
        flash("Je hebt geen toegang tot deze actie.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        
        # Update order status to rejected
        sb.table('Orders').update({
            'status': 'rejected'
        }).eq('id', order_id).execute()
        
        flash("Route afgewezen.", "info")
    except Exception as e:
        flash(f"Fout bij het afwijzen van route: {str(e)}", "error")
    
    return redirect(url_for('routes.home'))


@bp.route('/driver/dashboard')
@login_required
def driver_dashboard():
    user_type = session.get('user_type', 'customer')
    if user_type != 'driver':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        user_email = session.get('email')
        
        # Get driver's company_id
        driver_result = sb.table('Drivers').select('id, company_id').eq('email_address', user_email).limit(1).execute()
        driver_id = None
        company_id = None
        
        if driver_result.data and len(driver_result.data) > 0:
            driver_id = driver_result.data[0]['id']
            company_id = driver_result.data[0].get('company_id')
        
        if not company_id:
            return redirect(url_for('routes.driver_select_company'))
        
        # Get accepted routes for this driver (sorted by deadline)
        orders_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('driver_id', driver_id).eq('status', 'accepted').order('deadline', desc=False).limit(100).execute()
        
        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = {
                    'id': order.get('id'),
                    'deadline': order.get('deadline'),
                    'task_type': order.get('task_type'),
                    'product_type': order.get('product_type'),
                    'created_at': order.get('created_at'),
                    'address': None,
                    'company': None
                }
                # Get address if available
                if order.get('Address'):
                    addr = order['Address']
                    order_info['address'] = {
                        'street_name': addr.get('street_name'),
                        'house_number': addr.get('house_number'),
                        'city': addr.get('city'),
                        'phone_number': addr.get('phone_number')
                    }
                # Get company name if available
                if order.get('Companies'):
                    company = order['Companies']
                    order_info['company'] = {
                        'name': company.get('name')
                    }
                orders.append(order_info)
        
        return render_template('driver_dashboard.html', orders=orders, user_email=user_email)
    except Exception as e:
        flash(f"Fout bij het ophalen van ritten: {str(e)}", "error")
        import traceback
        traceback.print_exc()
        return render_template('driver_dashboard.html', orders=[], user_email=session.get('email', ''))

@bp.route('/logout')
def logout():
    session.clear()
    flash("Uitgelogd.", "success")
    return redirect(url_for('routes.home'))


@bp.route('/order', methods=['GET', 'POST'])
@login_required
def order():
    # Only customers can place orders, companies cannot
    user_type = session.get('user_type', 'customer')
    if user_type == 'company':
        flash("Bedrijven kunnen geen bestellingen plaatsen. Gebruik het dashboard om bestellingen te bekijken.", "error")
        return redirect(url_for('routes.company_dashboard'))
    
    # Get authenticated Supabase client
    sb = get_authenticated_supabase()
    
    # Get all companies (show all companies, not just those with email addresses)
    companies = []
    try:
        # Get all companies - show all companies regardless of emailaddress
        companies_result = sb.table('Companies').select('id, name, emailaddress').order('name').execute()
        if companies_result.data:
            # Show all companies (simplified - no filtering by emailaddress)
            companies = [
                {'id': c['id'], 'name': c['name']} 
                for c in companies_result.data
            ]
            print(f"Found {len(companies)} companies total")
    except Exception as e:
        print(f"Error fetching companies: {e}")
        import traceback
        traceback.print_exc()
        flash("Kon bedrijven niet ophalen. Probeer het later opnieuw.", "error")
    
    if request.method == 'POST':
        try:
            # Get farmer_id from Supabase Farmer table (if exists) - works over HTTPS
            farmer_id = None
            if session.get('email'):
                try:
                    farmer_result = sb.table('Farmer').select('id').eq('emailadress', session['email']).limit(1).execute()
                    if farmer_result.data and len(farmer_result.data) > 0:
                        farmer_id = farmer_result.data[0]['id']
                except Exception:
                    pass  # Farmer may not exist yet, that's okay

            # Coerce house_number to integer if possible
            house_number_raw = request.form.get("house_number")
            try:
                house_number_val = int(house_number_raw) if house_number_raw is not None else None
            except ValueError:
                house_number_val = None

            # Create address via Supabase REST API (works over HTTPS, no direct DB needed)
            address_data = {
                "farmer_id": farmer_id,
                "street_name": request.form.get("street_name"),
                "house_number": house_number_val,
                "city": request.form.get("city"),
                "phone_number": request.form.get("phone_number")
            }
            address_result = sb.table('Address').insert(address_data).execute()
            
            if not address_result.data or len(address_result.data) == 0:
                flash("Adres kon niet worden aangemaakt.", "error")
                return render_template('order.html', companies=companies)

            address_id = address_result.data[0]['id']

            # Get company_id from form (required field)
            company_id = request.form.get("company_id")
            if not company_id:
                flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                return render_template('order.html', companies=companies)
            
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                flash("Ongeldig bedrijf geselecteerd.", "error")
                return render_template('order.html', companies=companies)
            
            # Get weight from form and convert to float
            weight = None
            weight_str = request.form.get("weight", "").strip()
            if weight_str:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                    return render_template('order.html', companies=companies)
            
            if weight is None or weight <= 0:
                flash("Gewicht is verplicht en moet groter zijn dan 0.", "error")
                return render_template('order.html', companies=companies)
            
            # Get or create client_id for the customer
            client_id = session.get('client_id')
            if not client_id:
                # Try to get client_id from Client table
                try:
                    customer_email = session.get('email')
                    client_result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', customer_email).limit(1).execute()
                    if client_result.data and len(client_result.data) > 0:
                        client_id = client_result.data[0]['id']
                        session['client_id'] = client_id
                        # Update session with name if available
                        first_name = client_result.data[0].get('Name', '')
                        last_name = client_result.data[0].get('Lastname', '')
                        if first_name:
                            session['first_name'] = first_name
                        if last_name:
                            session['last_name'] = last_name
                    else:
                        # Create Client record if it doesn't exist (without name, will be set during signup)
                        new_client = sb.table('Client').insert({
                            "emailaddress": customer_email,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        if new_client.data:
                            client_id = new_client.data[0]['id']
                            session['client_id'] = client_id
                except Exception as e:
                    print(f"Warning: Could not get/create client_id: {e}")
            
            # Create order via Supabase REST API
            # Link to Client table via client_id
            # Also keep customer_email for backward compatibility and filtering
            order_data = {
                "deadline": request.form.get("deadline"),
                "task_type": request.form.get("task_type"),
                "product_type": request.form.get("product_type"),
                "address_id": address_id,
                "company_id": company_id,
                "customer_email": session.get('email'),  # Keep for backward compatibility
                "client_id": client_id,  # Link to Client table
                "status": "pending",  # Explicitly set status to pending for driver visibility
                "Weight": weight  # Store weight in kilograms
            }
            
            order_result = sb.table('Orders').insert(order_data).execute()

            if order_result.data:
                flash("Bestelling geplaatst!", "success")
                return redirect(url_for('routes.home'))
            else:
                flash("Bestelling kon niet worden geplaatst.", "error")
        except Exception as e:
            flash(f"Fout bij het plaatsen van bestelling: {str(e)}", "error")
            return render_template('order.html', companies=companies)

    return render_template('order.html', companies=companies)
