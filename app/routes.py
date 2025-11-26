from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
import re
from .config import supabase, Config
bp = Blueprint('routes', __name__)

def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None

def get_authenticated_supabase():
    """
    Vereenvoudigde helper: geeft de globale Supabase client terug zonder
    enige authenticatie of sessie-koppeling.

    We gebruiken Supabase alleen als database (via RLS/anon key of service key)
    en NIET meer voor gebruikers-authenticatie.
    """
    return supabase

def login_required(view_func):
    def wrapped(*args, **kwargs):
        # Eenvoudige check: is er een huidige gebruiker in de sessie?
        if 'email' not in session or 'user_type' not in session:
            flash("Je moet ingelogd zijn.", "error")
            return redirect(url_for('routes.login'))
        return view_func(*args, **kwargs)
    # Preserve function name for Flask debug
    wrapped.__name__ = view_func.__name__
    return wrapped


@bp.before_request
def load_current_user():
    """Load current user info into g for template access"""
    # Gebruik de gebruikersnaam als "id" voor login-detectie
    g.current_user_id = session.get('email')
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
            
            # Get only routes assigned to this driver by the company
            assigned_routes = []
            
            if driver_id:
                # Get routes assigned to this driver (by company)
                assigned_result = sb.table('Orders').select('*, Address(*), Companies(*)').eq('driver_id', driver_id).eq('status', 'accepted').order('deadline', desc=False).limit(50).execute()
                
                print(f"✅ Found {len(assigned_result.data) if assigned_result.data else 0} assigned routes for driver {driver_id}")
                
                if assigned_result.data:
                    for order in assigned_result.data:
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
                        assigned_routes.append(route_info)
            
            return render_template('home.html', user_type='driver', assigned_routes=assigned_routes, company_id=company_id, driver_id=driver_id)
        except Exception as e:
            print(f"Error loading driver home: {e}")
            import traceback
            traceback.print_exc()
            return render_template('home.html', user_type='driver', assigned_routes=[], company_id=None, driver_id=None)
    
    # For customers and others, show regular home page
    return render_template('home.html', user_type=user_type)


@bp.route('/debug-login')
def debug_login():
    """Debug page to test login form submission"""
    return render_template('debug_login.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    # Debug logging
    print(f"Login route called - Method: {request.method}")
    
    if request.method == 'POST':
        print(f"POST request received - Form data: {dict(request.form)}")
        # Gebruikersnaam die we in de emailaddress/email_address kolommen opslaan
        username = request.form.get('username', '').strip()

        # Minimale validatie: alleen leeg veld blokkeren
        if not username:
            flash("Gebruikersnaam is verplicht.", "error")
            return render_template('login.html')

        try:
            if supabase is None:
                print("ERROR: Supabase client is None!")
                flash("Supabase is niet geconfigureerd. Neem contact op met de beheerder.", "error")
                return render_template('login.html')

            sb = get_authenticated_supabase()

            # Zoek de gebruiker in de tabellen op basis van gebruikersnaam
            client_id = None
            company_id = None
            driver_id = None
            first_name = None
            last_name = None
            user_type = None

            # 1) Klant
            result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', username).limit(1).execute()
            if result.data and len(result.data) > 0:
                row = result.data[0]
                client_id = row['id']
                first_name = row.get('Name')
                last_name = row.get('Lastname')
                user_type = 'customer'
            else:
                # 2) Bedrijf
                result = sb.table('Companies').select('id, name').eq('emailaddress', username).limit(1).execute()
                if result.data and len(result.data) > 0:
                    company_id = result.data[0]['id']
                    user_type = 'company'
                else:
                    # 3) Chauffeur
                    result = sb.table('Drivers').select('id, name').eq('email_address', username).limit(1).execute()
                    if result.data and len(result.data) > 0:
                        driver_id = result.data[0]['id']
                        user_type = 'driver'

            if not user_type:
                flash("Geen gebruiker gevonden met deze gebruikersnaam.", "error")
                return render_template('login.html')

            # Sessie vullen – geen Supabase-auth tokens meer, alleen onze eigen context
            session.clear()
            session['email'] = username
            session['user_type'] = user_type

            if client_id is not None:
                session['client_id'] = client_id
            if company_id is not None:
                session['company_id'] = company_id
            if driver_id is not None:
                session['driver_id'] = driver_id
            if first_name:
                session['first_name'] = first_name
            if last_name:
                session['last_name'] = last_name

            session.modified = True

            flash("Succesvol ingelogd zonder wachtwoord.", "success")
            # Redirect op basis van type
            if user_type == 'company':
                return redirect(url_for('routes.company_dashboard'))
            elif user_type == 'driver':
                return redirect(url_for('routes.driver_dashboard'))
            else:
                return redirect(url_for('routes.profile'))

        except Exception as e:
            import traceback
            print(f"Login error (username-only): {e}")
            print(traceback.format_exc())
            flash(f"Inloggen mislukt. Fout: {e}", "error")
            return render_template('login.html')

    return render_template('login.html')


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    # user_type kan nu direct op het formulier gekozen worden
    user_type = request.args.get('user_type') or request.form.get('user_type') or 'customer'
    if user_type not in ['company', 'customer', 'driver']:
        user_type = 'customer'

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()

        if not username:
            flash("Gebruikersnaam is verplicht.", "error")
            return render_template('signup.html', user_type=user_type)

        if not first_name:
            flash("Voornaam is verplicht.", "error")
            return render_template('signup.html', user_type=user_type)
        if not last_name:
            flash("Achternaam is verplicht.", "error")
            return render_template('signup.html', user_type=user_type)

        try:
            if supabase is None:
                flash("Supabase is niet geconfigureerd. Neem contact op met de beheerder.", "error")
                return render_template('signup.html', user_type=user_type)

            sb = get_authenticated_supabase()

            if user_type == 'customer':
                # Bestaat klant al?
                existing = sb.table('Client').select('id').eq('emailaddress', username).limit(1).execute()
                if existing.data and len(existing.data) > 0:
                    flash("Er bestaat al een klant met deze gebruikersnaam. Log in zonder wachtwoord.", "info")
                    return redirect(url_for('routes.login', user_type=user_type))

                sb.table('Client').insert({
                    "emailaddress": username,
                    "Name": first_name,
                    "Lastname": last_name,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()

            elif user_type == 'company':
                existing = sb.table('Companies').select('id').eq('emailaddress', username).limit(1).execute()
                if existing.data and len(existing.data) > 0:
                    flash("Er bestaat al een bedrijf met deze gebruikersnaam. Log in zonder wachtwoord.", "info")
                    return redirect(url_for('routes.login', user_type=user_type))

                company_result = sb.table('Companies').insert({
                    "name": username,  # gebruik gebruikersnaam als bedrijfsnaam
                    "emailaddress": username,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()

                # Optioneel: ook een Farmer-record aanmaken (maar laat registratie niet falen als tabel ontbreekt)
                if company_result.data and len(company_result.data) > 0:
                    try:
                        company_id = company_result.data[0]['id']
                        sb.table('Farmer').insert({
                            "emailadress": username,
                            "created_at": datetime.utcnow().isoformat(),
                            "company_id": company_id
                        }).execute()
                    except Exception as e:
                        # Log alleen; registratie van bedrijf mag gewoon doorgaan
                        print(f"Kon Farmer-record niet aanmaken, ga verder zonder: {e}")

            elif user_type == 'driver':
                existing = sb.table('Drivers').select('id').eq('email_address', username).limit(1).execute()
                if existing.data and len(existing.data) > 0:
                    flash("Er bestaat al een chauffeur met deze gebruikersnaam. Log in zonder wachtwoord.", "info")
                    return redirect(url_for('routes.login', user_type=user_type))

                sb.table('Drivers').insert({
                    "email_address": username,
                    "name": f"{first_name} {last_name}".strip(),
                    "created_at": datetime.utcnow().isoformat()
                }).execute()

            flash("Account aangemaakt. Je kunt nu inloggen met je gebruikersnaam (zonder wachtwoord).", "success")
            return redirect(url_for('routes.login', user_type=user_type))

        except Exception as e:
            import traceback
            print(f"Signup error (no-auth): {e}")
            print(traceback.format_exc())
            flash(f"Registratie mislukt. Fout: {e}", "error")
            return render_template('signup.html', user_type=user_type)

    return render_template('signup.html', user_type=user_type)


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
            return render_template('company_dashboard.html', orders=[], drivers=[], user_email=company_email)
        
        # Haal alle chauffeurs van dit bedrijf op
        drivers_result = sb.table('Drivers').select('id, name, email_address').eq('company_id', company_id).order('name').execute()
        drivers = drivers_result.data if drivers_result.data else []
        
        # Get only orders for this company (filtered by company_id)
        # Use * to get all fields including customer_email and client_id
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
                    'address': None,
                    'customer_name': None,
                    'customer_lastname': None,
                    'driver_id': order.get('driver_id'),
                    'status': order.get('status')
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
                
                # Get customer name from Client table
                # Try client_id first (more reliable), then fall back to customer_email
                client_id = order.get('client_id')
                customer_email = order.get('customer_email')
                
                # If order doesn't have client_id but has customer_email, try to link it
                if not client_id and customer_email:
                    try:
                        # Find client by email and get their ID
                        client_lookup = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                        if client_lookup.data and len(client_lookup.data) > 0:
                            client_id = client_lookup.data[0]['id']
                            # Update the order to link it to the client
                            try:
                                sb.table('Orders').update({'client_id': client_id}).eq('id', order_info['id']).execute()
                                print(f"Linked order {order_info['id']} to client_id {client_id}")
                            except Exception as update_error:
                                print(f"Warning: Could not update order {order_info['id']} with client_id: {update_error}")
                    except Exception as e:
                        print(f"Warning: Could not find client for email {customer_email}: {e}")
                
                # Get customer name using client_id (preferred) or customer_email (fallback)
                if client_id:
                    try:
                        client_result = sb.table('Client').select('Name, Lastname').eq('id', client_id).limit(1).execute()
                        if client_result.data and len(client_result.data) > 0:
                            order_info['customer_name'] = client_result.data[0].get('Name', '')
                            order_info['customer_lastname'] = client_result.data[0].get('Lastname', '')
                    except Exception as e:
                        print(f"Warning: Could not get customer name by client_id {client_id}: {e}")
                
                # If we still don't have the name, try customer_email
                if (not order_info['customer_name'] and not order_info['customer_lastname']) and customer_email:
                    try:
                        client_result = sb.table('Client').select('Name, Lastname').eq('emailaddress', customer_email).limit(1).execute()
                        if client_result.data and len(client_result.data) > 0:
                            order_info['customer_name'] = client_result.data[0].get('Name', '')
                            order_info['customer_lastname'] = client_result.data[0].get('Lastname', '')
                    except Exception as e:
                        print(f"Warning: Could not get customer name for {customer_email}: {e}")
                
                orders.append(order_info)
        
        return render_template('company_dashboard.html', orders=orders, drivers=drivers, user_email=session.get('email', ''))
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('company_dashboard.html', orders=[], drivers=[], user_email=session.get('email', ''))


@bp.route('/company/assign-driver/<int:order_id>', methods=['POST'])
@login_required
def company_assign_driver(order_id):
    """Wijs een chauffeur toe aan een order (door bedrijf)."""
    user_type = session.get('user_type', 'customer')
    if user_type != 'company':
        flash("Je hebt geen toegang tot deze actie.", "error")
        return redirect(url_for('routes.profile'))

    driver_id = request.form.get('driver_id')
    if not driver_id:
        flash("Selecteer een chauffeur om toe te wijzen.", "error")
        return redirect(url_for('routes.company_dashboard'))

    try:
        driver_id_int = int(driver_id)
    except (ValueError, TypeError):
        flash("Ongeldige chauffeur geselecteerd.", "error")
        return redirect(url_for('routes.company_dashboard'))

    try:
        sb = get_authenticated_supabase()
        company_email = session.get('email')

        # Bepaal company_id van ingelogde company
        company_result = sb.table('Companies').select('id').eq('emailaddress', company_email).limit(1).execute()
        if not company_result.data or len(company_result.data) == 0:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return redirect(url_for('routes.company_dashboard'))

        company_id = company_result.data[0]['id']

        # Controleer of de chauffeur bij dit bedrijf hoort
        driver_result = sb.table('Drivers').select('id').eq('id', driver_id_int).eq('company_id', company_id).limit(1).execute()
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Deze chauffeur hoort niet bij jouw bedrijf.", "error")
            return redirect(url_for('routes.company_dashboard'))

        # Update de order: koppel driver_id en markeer als 'accepted'
        update_result = sb.table('Orders').update({
            'driver_id': driver_id_int,
            'status': 'accepted'
        }).eq('id', order_id).eq('company_id', company_id).execute()

        if not update_result.data:
            flash("Bestelling niet gevonden of kon niet worden bijgewerkt.", "error")
        else:
            flash("Chauffeur succesvol aan bestelling toegewezen.", "success")

    except Exception as e:
        import traceback
        print(f"Error assigning driver: {e}")
        print(traceback.format_exc())
        flash(f"Fout bij het toewijzen van chauffeur: {e}", "error")

    return redirect(url_for('routes.company_dashboard'))


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
