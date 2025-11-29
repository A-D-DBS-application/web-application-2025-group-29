from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
from .config import supabase
from .algorithms import suggest_best_driver, sort_orders_by_priority, calculate_driver_workload_hours, calculate_order_time_hours
bp = Blueprint('routes', __name__)

def get_authenticated_supabase():
    return supabase

def login_required(view_func):
    def wrapped(*args, **kwargs):
        if 'email' not in session or 'user_type' not in session:
            flash("Je moet ingelogd zijn.", "error")
            return redirect(url_for('routes.login'))
        return view_func(*args, **kwargs)
    wrapped.__name__ = view_func.__name__
    return wrapped


@bp.before_request
def load_current_user():
    g.current_user_id = session.get('email')
    g.current_user_email = session.get('email')
    g.current_user_type = session.get('user_type', 'customer')
    
    if g.current_user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        if first_name and last_name:
            g.current_user_display_name = f"{first_name} {last_name}"
        else:
            g.current_user_display_name = g.current_user_email
    else:
        g.current_user_display_name = g.current_user_email


@bp.route('/')
def home():
    user_type = session.get('user_type', 'customer')
    user_email = session.get('email')
    
    # For companies, show company-specific home page with stats
    if user_type == 'company' and user_email:
        try:
            sb = get_authenticated_supabase()
            company_result = sb.table('Companies').select('id, name').eq('emailaddress', user_email).limit(1).execute()
            company_id = None
            company_name = None
            
            if company_result.data and len(company_result.data) > 0:
                company_id = company_result.data[0]['id']
                company_name = company_result.data[0].get('name', 'Bedrijf')
            
            stats = {
                'total_orders': 0,
                'pending_orders': 0,
                'completed_orders': 0,
                'recent_orders': []
            }
            
            if company_id:
                orders_result = sb.table('Orders').select('id, deadline, created_at, status').eq('company_id', company_id).execute()
                if orders_result.data:
                    stats['total_orders'] = len(orders_result.data)
                    stats['completed_orders'] = sum(1 for o in orders_result.data if o.get('status') == 'completed')
                    # Count orders that are not completed as pending
                    stats['pending_orders'] = stats['total_orders'] - stats['completed_orders']
                    stats['recent_orders'] = sorted(orders_result.data, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
            
            return render_template('home.html', user_type='company', company_name=company_name, stats=stats)
        except Exception as e:
            flash(f"Error loading company home: {e}", "error")
            return render_template('home.html', user_type='company', company_name=None, stats={'total_orders': 0, 'pending_orders': 0, 'completed_orders': 0, 'recent_orders': []})
    
    # For drivers, show driver-specific home page with available routes
    if user_type == 'driver' and user_email:
        try:
            sb = get_authenticated_supabase()
            driver_result = sb.table('Drivers').select('id, company_id').eq('email_address', user_email).limit(1).execute()
            driver_id = None
            company_id = None
            
            if driver_result.data and len(driver_result.data) > 0:
                driver_id = driver_result.data[0]['id']
                company_id = driver_result.data[0].get('company_id')
            
            if not company_id:
                return redirect(url_for('routes.driver_select_company'))
            
            assigned_routes = []
            
            if driver_id:
                assigned_result = sb.table('Orders').select('*, Address!orders_address_id_fkey(*), Companies(*)').eq('driver_id', driver_id).in_('status', ['accepted', 'completed']).order('deadline', desc=False).limit(50).execute()
                
                if assigned_result.data:
                    for order in assigned_result.data:
                        route_info = {
                            'id': order.get('id'),
                            'deadline': order.get('deadline'),
                            'task_type': order.get('task_type'),
                            'product_type': order.get('product_type'),
                            'created_at': order.get('created_at'),
                            'status': order.get('status'),
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
            
            # Splits routes in actieve en voltooide
            active_routes = [r for r in assigned_routes if r.get('status') != 'completed']
            completed_routes = [r for r in assigned_routes if r.get('status') == 'completed']
            
            return render_template('home.html', user_type='driver', active_routes=active_routes, completed_routes=completed_routes, company_id=company_id, driver_id=driver_id)
        except Exception as e:
            flash(f"Error loading driver home: {e}", "error")
            return render_template('home.html', user_type='driver', active_routes=[], completed_routes=[], company_id=None, driver_id=None)
    
    # For customers and others, show regular home page
    return render_template('home.html', user_type=user_type)


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()

        if not username:
            flash("Gebruikersnaam is verplicht.", "error")
            return render_template('login.html')

        try:
            if supabase is None:
                flash("Supabase is niet geconfigureerd. Neem contact op met de beheerder.", "error")
                return render_template('login.html')

            sb = get_authenticated_supabase()

            client_id = None
            company_id = None
            driver_id = None
            first_name = None
            last_name = None
            user_type = None

            result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', username).limit(1).execute()
            if result.data and len(result.data) > 0:
                row = result.data[0]
                client_id = row['id']
                first_name = row.get('Name')
                last_name = row.get('Lastname')
                user_type = 'customer'
            else:
                result = sb.table('Companies').select('id, name').eq('emailaddress', username).limit(1).execute()
                if result.data and len(result.data) > 0:
                    company_id = result.data[0]['id']
                    user_type = 'company'
                else:
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

            flash("Succesvol ingelogd.", "success")
            return redirect(url_for('routes.home'))
            
        except Exception as e:
            flash(f"Inloggen mislukt. Fout: {e}", "error")
            return render_template('login.html')

    return render_template('login.html')


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
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
                    "name": username,
                    "emailaddress": username,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()
                
                if company_result.data and len(company_result.data) > 0:
                    pass

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
            flash(f"Registratie mislukt. Fout: {e}", "error")
            return render_template('signup.html', user_type=user_type)

    return render_template('signup.html', user_type=user_type)


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user_type = session.get('user_type', 'customer')
    
    user_ctx = {
        "emailaddress": session.get('email', ''),
        "user_type": user_type
    }
    
    addresses = []
    
    if user_type == 'driver':
        try:
            sb = get_authenticated_supabase()
            driver_email = session.get('email')
            if driver_email:
                driver_result = sb.table('Drivers').select('id, name, company_id').eq('email_address', driver_email).limit(1).execute()
                if driver_result.data and len(driver_result.data) > 0:
                    driver_data = driver_result.data[0]
                    driver_name = driver_data.get('name', '')
                    if driver_name:
                        user_ctx['display_name'] = driver_name
                    company_id = driver_data.get('company_id')
                    if company_id:
                        company_result = sb.table('Companies').select('name').eq('id', company_id).limit(1).execute()
                        if company_result.data and len(company_result.data) > 0:
                            user_ctx['company_name'] = company_result.data[0].get('name', '')
        except Exception:
            pass
    
    if user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        if first_name or last_name:
            user_ctx['first_name'] = first_name
            user_ctx['last_name'] = last_name
            user_ctx['display_name'] = f"{first_name} {last_name}".strip()
        else:
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
            except Exception:
                pass
        
        try:
            sb = get_authenticated_supabase()
            client_id = session.get('client_id')
            if not client_id:
                customer_email = session.get('email')
                if customer_email:
                    client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                    if client_result.data and len(client_result.data) > 0:
                        client_id = client_result.data[0]['id']
                        session['client_id'] = client_id
            
            if client_id:
                addresses_result = sb.table('Address').select('*').eq('client_id', client_id).order('created_at', desc=False).execute()
                if addresses_result.data:
                    addresses = addresses_result.data
        except Exception as e:
            flash(f"Kon adressen niet ophalen: {e}", "error")
    
    return render_template('profile.html', user=user_ctx, addresses=addresses)


@bp.route('/profile/add-address', methods=['POST'])
@login_required
def add_address():
    user_type = session.get('user_type', 'customer')
    if user_type != 'customer':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        client_id = session.get('client_id')
        if not client_id:
            # Try to get client_id from email
            customer_email = session.get('email')
            if customer_email:
                client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                if client_result.data and len(client_result.data) > 0:
                    client_id = client_result.data[0]['id']
                    session['client_id'] = client_id
        
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for('routes.profile'))
        
        house_number_raw = request.form.get("house_number")
        try:
            house_number_val = int(house_number_raw) if house_number_raw is not None else None
        except ValueError:
            house_number_val = None
        
        address_data = {
            "client_id": client_id,
            "street_name": request.form.get("street_name"),
            "house_number": house_number_val,
            "city": request.form.get("city"),
            "phone_number": request.form.get("phone_number")
        }
        
        address_result = sb.table('Address').insert(address_data).execute()
        
        if address_result.data:
            flash("Adres succesvol toegevoegd!", "success")
        else:
            flash("Adres kon niet worden toegevoegd.", "error")
    except Exception as e:
        flash(f"Fout bij het toevoegen van adres: {str(e)}", "error")
    
    return redirect(url_for('routes.profile'))


@bp.route('/profile/delete-address/<int:address_id>', methods=['POST'])
@login_required
def delete_address(address_id):
    user_type = session.get('user_type', 'customer')
    if user_type != 'customer':
        flash("Je hebt geen toegang tot deze pagina.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        client_id = session.get('client_id')
        if not client_id:
            # Try to get client_id from email
            customer_email = session.get('email')
            if customer_email:
                client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                if client_result.data and len(client_result.data) > 0:
                    client_id = client_result.data[0]['id']
                    session['client_id'] = client_id
        
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for('routes.profile'))
        
        # Verify that the address belongs to this client
        address_result = sb.table('Address').select('client_id').eq('id', address_id).eq('client_id', client_id).limit(1).execute()
        if not address_result.data or len(address_result.data) == 0:
            flash("Adres niet gevonden of je hebt geen toegang tot dit adres.", "error")
            return redirect(url_for('routes.profile'))
        
        # Check if address is used in any orders
        orders_result = sb.table('Orders').select('id').eq('address_id', address_id).limit(1).execute()
        if orders_result.data and len(orders_result.data) > 0:
            flash("Dit adres kan niet worden verwijderd omdat het gebruikt wordt in een bestelling.", "error")
            return redirect(url_for('routes.profile'))
        
        # Delete address
        delete_result = sb.table('Address').delete().eq('id', address_id).eq('client_id', client_id).execute()
        
        if delete_result.data:
            flash("Adres succesvol verwijderd!", "success")
        else:
            flash("Adres kon niet worden verwijderd.", "error")
    except Exception as e:
        flash(f"Fout bij het verwijderen van adres: {str(e)}", "error")
    
    return redirect(url_for('routes.profile'))


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
        
        orders_result = sb.table('Orders').select('*, Address!orders_address_id_fkey(*), Companies(*)').eq('customer_email', customer_email).order('created_at', desc=True).limit(100).execute()
        
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
                    'company': None,
                    'driver_id': order.get('driver_id'),
                    'driver_name': None,
                    'status': order.get('status')
                }
                if order.get('Address'):
                    addr = order['Address']
                    order_info['address'] = {
                        'street_name': addr.get('street_name'),
                        'house_number': addr.get('house_number'),
                        'city': addr.get('city'),
                        'phone_number': addr.get('phone_number')
                    }
                if order.get('Companies'):
                    company = order['Companies']
                    order_info['company'] = {
                        'name': company.get('name'),
                        'id': company.get('id')
                    }
                driver_id = order.get('driver_id')
                if driver_id:
                    try:
                        driver_result = sb.table('Drivers').select('name').eq('id', driver_id).limit(1).execute()
                        if driver_result.data and len(driver_result.data) > 0:
                            order_info['driver_name'] = driver_result.data[0].get('name', 'Onbekend')
                    except Exception:
                        pass
                orders.append(order_info)
        
        # Splits orders in actieve en voltooide
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('customer_orders.html', active_orders=active_orders, completed_orders=completed_orders, user_email=customer_email)
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('customer_orders.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))


@bp.route('/customer/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    """Annuleer een bestelling (alleen als deze nog niet is toegewezen aan een chauffeur)."""
    user_type = session.get('user_type', 'customer')
    if user_type != 'customer':
        flash("Je hebt geen toegang tot deze actie.", "error")
        return redirect(url_for('routes.profile'))
    
    try:
        sb = get_authenticated_supabase()
        customer_email = session.get('email')
        
        # Controleer of de bestelling bestaat en bij deze klant hoort
        order_result = sb.table('Orders').select('id, driver_id, customer_email, status').eq('id', order_id).eq('customer_email', customer_email).limit(1).execute()
        
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order = order_result.data[0]
        
        # Controleer of de bestelling al is toegewezen aan een chauffeur
        if order.get('driver_id'):
            flash("Deze bestelling kan niet worden geannuleerd omdat deze al is toegewezen aan een chauffeur.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        # Controleer of de bestelling al is voltooid
        if order.get('status') == 'completed':
            flash("Deze bestelling kan niet worden geannuleerd omdat deze al is voltooid.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        # Verwijder de bestelling
        delete_result = sb.table('Orders').delete().eq('id', order_id).eq('customer_email', customer_email).execute()
        
        if delete_result.data:
            flash("Bestelling succesvol geannuleerd.", "success")
        else:
            flash("Bestelling kon niet worden geannuleerd.", "error")
    
    except Exception as e:
        flash(f"Fout bij het annuleren van bestelling: {str(e)}", "error")
    
    return redirect(url_for('routes.customer_orders'))


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
        order_result = sb.table('Orders').select('*, Address!orders_address_id_fkey(*), Companies(*)').eq('id', order_id).eq('customer_email', customer_email).limit(1).execute()
        
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order_data = order_result.data[0]
        
        address_id = order_data.get('address_id')
        if address_id:
            try:
                client_id = session.get('client_id')
                if not client_id:
                    client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                    if client_result.data and len(client_result.data) > 0:
                        client_id = client_result.data[0]['id']
                        session['client_id'] = client_id
                
                if client_id:
                    address_check = sb.table('Address').select('client_id').eq('id', address_id).eq('client_id', client_id).limit(1).execute()
                    if not address_check.data or len(address_check.data) == 0:
                        flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
                        return redirect(url_for('routes.customer_orders'))
            except Exception:
                pass
        
        driver_id = order_data.get('driver_id')
        if driver_id:
            driver_name = "een chauffeur"
            try:
                driver_result = sb.table('Drivers').select('name').eq('id', driver_id).limit(1).execute()
                if driver_result.data and len(driver_result.data) > 0:
                    driver_name = driver_result.data[0].get('name', 'een chauffeur')
            except Exception:
                pass
            flash(f"Deze bestelling kan niet meer bewerkt worden omdat deze is toegewezen aan {driver_name}.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        companies = []
        try:
            companies_result = sb.table('Companies').select('id, name, emailaddress').order('name').execute()
            if companies_result.data:
                companies = [
                    {'id': c['id'], 'name': c['name']} 
                    for c in companies_result.data
                ]
        except Exception as e:
            flash(f"Kon bedrijven niet ophalen: {e}", "error")
        
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
        
        if order_data.get('Address'):
            addr = order_data['Address']
            order_info['address'] = {
                'street_name': addr.get('street_name'),
                'house_number': addr.get('house_number'),
                'city': addr.get('city'),
                'phone_number': addr.get('phone_number'),
                'id': addr.get('id')
            }
        
        if order_data.get('Companies'):
            company = order_data['Companies']
            order_info['company'] = {
                'name': company.get('name'),
                'id': company.get('id')
            }
        
        if request.method == 'POST':
            try:
                client_id = session.get('client_id')
                if not client_id:
                    customer_email = session.get('email')
                    if customer_email:
                        client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                        if client_result.data and len(client_result.data) > 0:
                            client_id = client_result.data[0]['id']
                            session['client_id'] = client_id
                
                if not client_id:
                    flash("Klant niet gevonden.", "error")
                    return render_template('edit_order.html', order=order_info, companies=companies)
                
                # Coerce house_number to integer if possible
                house_number_raw = request.form.get("house_number")
                try:
                    house_number_val = int(house_number_raw) if house_number_raw is not None else None
                except ValueError:
                    house_number_val = None
                
                address_update_data = {
                    "client_id": client_id,
                    "street_name": request.form.get("street_name"),
                    "house_number": house_number_val,
                    "city": request.form.get("city"),
                    "phone_number": request.form.get("phone_number")
                }
                
                if order_info['address_id']:
                    address_check = sb.table('Address').select('client_id').eq('id', order_info['address_id']).eq('client_id', client_id).limit(1).execute()
                    if address_check.data and len(address_check.data) > 0:
                        address_update_result = sb.table('Address').update(address_update_data).eq('id', order_info['address_id']).eq('client_id', client_id).execute()
                    else:
                        flash("Adres kan niet worden bijgewerkt omdat het niet aan jou toebehoort.", "error")
                        return render_template('edit_order.html', order=order_info, companies=companies)
                else:
                    # If no address_id, create a new address
                    address_result = sb.table('Address').insert(address_update_data).execute()
                    if address_result.data and len(address_result.data) > 0:
                        order_info['address_id'] = address_result.data[0]['id']
                
                company_id = request.form.get("company_id")
                if not company_id:
                    flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                    return render_template('edit_order.html', order=order_info, companies=companies)
                
                try:
                    company_id = int(company_id)
                except (ValueError, TypeError):
                    flash("Ongeldig bedrijf geselecteerd.", "error")
                    return render_template('edit_order.html', order=order_info, companies=companies)
                
                order_update_data = {
                    "deadline": request.form.get("deadline"),
                    "task_type": request.form.get("task_type"),
                    "product_type": request.form.get("product_type"),
                    "company_id": company_id
                }
                
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
                return render_template('edit_order.html', order=order_info, companies=companies)
        
        # GET request - show edit form
        return render_template('edit_order.html', order=order_info, companies=companies)
    
    except Exception as e:
        flash(f"Fout bij het ophalen van bestelling: {str(e)}", "error")
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
        company_email = session.get('email')
        company_id = None
        
        company_result = sb.table('Companies').select('id').eq('emailaddress', company_email).limit(1).execute()
        if company_result.data and len(company_result.data) > 0:
            company_id = company_result.data[0]['id']
        
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return render_template('company_dashboard.html', orders=[], drivers=[], user_email=company_email)
        
        # Haal alle chauffeurs van dit bedrijf op
        drivers_result = sb.table('Drivers').select('id, name, email_address').eq('company_id', company_id).order('name').execute()
        drivers = drivers_result.data if drivers_result.data else []
        
        orders_result = sb.table('Orders').select('*, Address!orders_address_id_fkey(*)').eq('company_id', company_id).order('created_at', desc=True).limit(100).execute()
        all_orders_raw = orders_result.data if orders_result.data else []
        
        driver_workload_hours = {}
        if drivers and all_orders_raw:
            orders_for_algo = []
            for order in all_orders_raw:
                orders_for_algo.append({
                    'driver_id': order.get('driver_id'),
                    'status': order.get('status'),
                    'deadline': order.get('deadline'),
                    'task_type': order.get('task_type'),
                    'Weight': order.get('Weight') or order.get('weight')
                })
            
            for driver in drivers:
                driver_id = driver['id']
                total_hours = calculate_driver_workload_hours(driver_id, orders_for_algo)
                driver_workload_hours[driver_id] = total_hours
        
        orders = []
        if all_orders_raw:
            for order in all_orders_raw:
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
                    'status': order.get('status'),
                    'Weight': order.get('Weight') or order.get('weight')
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
                
                address_id = order.get('address_id')
                customer_email = order.get('customer_email')
                client_id = None
                
                if address_id:
                    try:
                        address_result = sb.table('Address').select('client_id').eq('id', address_id).limit(1).execute()
                        if address_result.data and len(address_result.data) > 0:
                            client_id = address_result.data[0].get('client_id')
                    except Exception:
                        pass
                
                if not client_id and customer_email:
                    try:
                        client_lookup = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                        if client_lookup.data and len(client_lookup.data) > 0:
                            client_id = client_lookup.data[0]['id']
                    except Exception:
                        pass
                
                if client_id:
                    try:
                        client_result = sb.table('Client').select('Name, Lastname').eq('id', client_id).limit(1).execute()
                        if client_result.data and len(client_result.data) > 0:
                            order_info['customer_name'] = client_result.data[0].get('Name', '')
                            order_info['customer_lastname'] = client_result.data[0].get('Lastname', '')
                    except Exception:
                        pass
                
                if (not order_info['customer_name'] and not order_info['customer_lastname']) and customer_email:
                    try:
                        client_result = sb.table('Client').select('Name, Lastname').eq('emailaddress', customer_email).limit(1).execute()
                        if client_result.data and len(client_result.data) > 0:
                            order_info['customer_name'] = client_result.data[0].get('Name', '')
                            order_info['customer_lastname'] = client_result.data[0].get('Lastname', '')
                    except Exception:
                        pass
                
                # Bereken geschatte tijd voor deze order
                order_info['estimated_time_hours'] = calculate_order_time_hours(order_info)
                
                # Als er nog geen chauffeur is toegewezen, stel automatisch de beste voor
                if not order_info.get('driver_id') and drivers:
                    # Converteer alle orders naar dict formaat voor algoritme
                    orders_for_algo = []
                    for o in all_orders_raw:
                        orders_for_algo.append({
                            'driver_id': o.get('driver_id'),
                            'status': o.get('status'),
                            'deadline': o.get('deadline'),
                            'task_type': o.get('task_type'),
                            'Weight': o.get('Weight') or o.get('weight')
                        })
                    
                    suggestion = suggest_best_driver(drivers, order_info, driver_workload_hours, orders_for_algo)
                    if suggestion:
                        order_info['suggested_driver'] = suggestion
                    
                    # Bereken beschikbare tijd per chauffeur voor deze order
                    order_deadline_date = None
                    if order_info.get('deadline'):
                        try:
                            order_deadline_date = datetime.strptime(order_info['deadline'], '%Y-%m-%d').date()
                        except (ValueError, TypeError):
                            pass
                    
                    driver_availability = []
                    for driver in drivers:
                        driver_id = driver['id']
                        if order_deadline_date:
                            hours_on_deadline = calculate_driver_workload_hours(driver_id, orders_for_algo, order_deadline_date)
                            available_hours = 10.0 - hours_on_deadline
                        else:
                            total_hours = driver_workload_hours.get(driver_id, 0.0)
                            available_hours = 10.0 - (total_hours % 10.0) if total_hours > 0 else 10.0
                        
                        driver_availability.append({
                            'driver_id': driver_id,
                            'driver_name': driver.get('name', 'Onbekend'),
                            'available_hours': max(0.0, available_hours)
                        })
                    
                    order_info['driver_availability'] = driver_availability
                
                orders.append(order_info)
        
        # Sorteer bestellingen op prioriteit (urgentste eerst) met het algoritme
        orders = sort_orders_by_priority(orders)
        
        # Splits orders in actieve en voltooide
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('company_dashboard.html', active_orders=active_orders, completed_orders=completed_orders, drivers=drivers, user_email=session.get('email', ''))
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('company_dashboard.html', active_orders=[], completed_orders=[], drivers=[], user_email=session.get('email', ''))


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
    
    try:
        sb = get_authenticated_supabase()
        companies_result = sb.table('Companies').select('id, name').order('name').execute()
        companies = companies_result.data if companies_result.data else []
        
        driver_result = sb.table('Drivers').select('company_id').eq('email_address', user_email).limit(1).execute()
        if driver_result.data and len(driver_result.data) > 0 and driver_result.data[0].get('company_id'):
            # Already has company, redirect to home
            return redirect(url_for('routes.home'))
        
        return render_template('driver_select_company.html', companies=companies)
    except Exception as e:
        flash(f"Fout bij het ophalen van bedrijven: {str(e)}", "error")
        return render_template('driver_select_company.html', companies=[])


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
        orders_result = sb.table('Orders').select('*, Address!orders_address_id_fkey(*), Companies(*)').eq('driver_id', driver_id).in_('status', ['accepted', 'completed']).order('deadline', desc=False).limit(100).execute()
        
        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = {
                    'id': order.get('id'),
                    'deadline': order.get('deadline'),
                    'task_type': order.get('task_type'),
                    'product_type': order.get('product_type'),
                    'created_at': order.get('created_at'),
                    'status': order.get('status'),
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
        
        # Splits orders in actieve en voltooide
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('driver_dashboard.html', active_orders=active_orders, completed_orders=completed_orders, user_email=user_email)
    except Exception as e:
        flash(f"Fout bij het ophalen van ritten: {str(e)}", "error")
        return render_template('driver_dashboard.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))

@bp.route('/driver/complete-order/<int:order_id>', methods=['POST'])
@login_required
def driver_complete_order(order_id):
    user_type = session.get('user_type', 'customer')
    if user_type != 'driver':
        flash("Je hebt geen toegang tot deze actie.", "error")
        return redirect(url_for('routes.profile'))

    try:
        sb = get_authenticated_supabase()
        driver_email = session.get('email')

        driver_result = sb.table('Drivers').select('id').eq('email_address', driver_email).limit(1).execute()
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Chauffeur niet gevonden.", "error")
            return redirect(url_for('routes.driver_dashboard'))

        driver_id = driver_result.data[0]['id']

        order_result = sb.table('Orders').select('id, driver_id').eq('id', order_id).eq('driver_id', driver_id).limit(1).execute()
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of niet aan jou toegewezen.", "error")
            return redirect(url_for('routes.driver_dashboard'))

        update_result = sb.table('Orders').update({
            'status': 'completed'
        }).eq('id', order_id).eq('driver_id', driver_id).execute()

        if update_result.data:
            flash("Taak gemarkeerd als uitgevoerd!", "success")
        else:
            flash("Taak kon niet worden bijgewerkt.", "error")

    except Exception as e:
        flash(f"Fout bij het markeren van taak: {e}", "error")

    return redirect(url_for('routes.driver_dashboard'))

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
    except Exception as e:
        flash(f"Kon bedrijven niet ophalen: {e}", "error")
    
    addresses = []
    try:
        client_id = session.get('client_id')
        if not client_id:
            # Try to get client_id from email
            customer_email = session.get('email')
            if customer_email:
                client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                if client_result.data and len(client_result.data) > 0:
                    client_id = client_result.data[0]['id']
                    session['client_id'] = client_id
        
        if client_id:
            addresses_result = sb.table('Address').select('*').eq('client_id', client_id).order('created_at', desc=False).execute()
            if addresses_result.data:
                addresses = addresses_result.data
    except Exception as e:
        flash(f"Warning: Kon adressen niet ophalen: {e}", "error")
    
    if request.method == 'POST':
        try:
            address_id_str = request.form.get("address_id")
            
            if address_id_str:
                try:
                    address_id = int(address_id_str)
                    client_id = session.get('client_id')
                    if not client_id:
                        customer_email = session.get('email')
                        if customer_email:
                            client_result = sb.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                            if client_result.data and len(client_result.data) > 0:
                                client_id = client_result.data[0]['id']
                                session['client_id'] = client_id
                    
                    if client_id:
                        address_check = sb.table('Address').select('id').eq('id', address_id).eq('client_id', client_id).limit(1).execute()
                        if not address_check.data or len(address_check.data) == 0:
                            flash("Ongeldig adres geselecteerd.", "error")
                            return render_template('order.html', companies=companies, addresses=addresses)
                except (ValueError, TypeError):
                    flash("Ongeldig adres geselecteerd.", "error")
                    return render_template('order.html', companies=companies, addresses=addresses)
            else:
                flash("Selecteer een adres of voeg eerst een adres toe in je profiel.", "error")
                return render_template('order.html', companies=companies, addresses=addresses)

            company_id = request.form.get("company_id")
            if not company_id:
                flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                return render_template('order.html', companies=companies, addresses=addresses)
            
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                flash("Ongeldig bedrijf geselecteerd.", "error")
                return render_template('order.html', companies=companies, addresses=addresses)
            
            weight = None
            weight_str = request.form.get("weight", "").strip()
            if weight_str:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                    return render_template('order.html', companies=companies, addresses=addresses)
            
            if weight is None or weight <= 0:
                flash("Gewicht is verplicht en moet groter zijn dan 0.", "error")
                return render_template('order.html', companies=companies, addresses=addresses)
            
            client_id = session.get('client_id')
            if not client_id:
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
                        new_client = sb.table('Client').insert({
                            "emailaddress": customer_email,
                            "created_at": datetime.utcnow().isoformat()
                        }).execute()
                        if new_client.data:
                            client_id = new_client.data[0]['id']
                            session['client_id'] = client_id
                except Exception:
                    pass
            
            order_data = {
                "deadline": request.form.get("deadline"),
                "task_type": request.form.get("task_type"),
                "product_type": request.form.get("product_type"),
                "address_id": address_id,
                "company_id": company_id,
                "customer_email": session.get('email'),
                "status": "pending",
                "Weight": weight
            }
            
            order_result = sb.table('Orders').insert(order_data).execute()

            if order_result.data:
                flash("Bestelling geplaatst!", "success")
                return redirect(url_for('routes.home'))
            else:
                flash("Bestelling kon niet worden geplaatst.", "error")
        except Exception as e:
            flash(f"Fout bij het plaatsen van bestelling: {str(e)}", "error")
            return render_template('order.html', companies=companies, addresses=addresses)

    return render_template('order.html', companies=companies, addresses=addresses)
