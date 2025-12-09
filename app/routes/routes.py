from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime, timezone
from ..config import supabase
from ..algorithms import suggest_best_driver, sort_orders_by_priority, calculate_driver_workload_hours, calculate_order_time_hours, filter_duplicate_orders
bp = Blueprint('routes', __name__)

def login_required(view_func):
    def wrapped(*args, **kwargs):
        if 'email' not in session or 'user_type' not in session:
            flash("Je moet ingelogd zijn.", "error")
            return redirect(url_for('routes.login'))
        return view_func(*args, **kwargs)
    wrapped.__name__ = view_func.__name__
    return wrapped

def get_client_id():
    client_id = session.get('client_id')
    if not client_id:
        customer_email = session.get('email')
        if customer_email:
            try:
                client_result = supabase.table('Client').select('id').eq('emailaddress', customer_email).limit(1).execute()
                if client_result.data:
                    client_id = client_result.data[0]['id']
                    session['client_id'] = client_id
            except Exception:
                pass
    return client_id

def get_company_id():
    company_id = session.get('company_id')
    if not company_id:
        company_email = session.get('email')
        if company_email:
            try:
                company_result = supabase.table('Companies').select('id').eq('emailaddress', company_email).limit(1).execute()
                if company_result.data:
                    company_id = company_result.data[0]['id']
                    session['company_id'] = company_id
            except Exception:
                pass
    return company_id

def get_task_type_name(task_type_id, task_types_data=None):
    if task_types_data:
        return task_types_data.get('task_type')
    if task_type_id:
        try:
            result = supabase.table('TaskTypes').select('task_type').eq('id', task_type_id).limit(1).execute()
            if result.data:
                return result.data[0].get('task_type')
        except Exception:
            pass
    return None

def get_customer_info_from_address(address_id):
    if not address_id:
        return None, None
    try:
        address_result = supabase.table('Address').select('client_id').eq('id', address_id).limit(1).execute()
        if address_result.data:
            client_id = address_result.data[0].get('client_id')
            if client_id:
                client_result = supabase.table('Client').select('Name, Lastname').eq('id', client_id).limit(1).execute()
                if client_result.data:
                    return client_result.data[0].get('Name', ''), client_result.data[0].get('Lastname', '')
    except Exception:
        pass
    return None, None

def format_address_data(address_data):
    if not address_data:
        return None
    return {
        'street_name': address_data.get('street_name'),
        'house_number': address_data.get('house_number'),
        'city': address_data.get('city'),
        'phone_number': address_data.get('phone_number')
    }

def convert_orders_for_algorithm(orders_raw):
    return [{
        'driver_id': o.get('driver_id'),
        'status': o.get('status'),
        'deadline': o.get('deadline'),
        'task_type_id': o.get('task_type_id'),
        'task_type': o.get('task_type'),
        'Weight': o.get('Weight') or o.get('weight'),
        'weight': o.get('Weight') or o.get('weight')
    } for o in orders_raw]

def calculate_driver_availability(drivers, orders_for_algo, order_deadline, driver_workload_hours, custom_task_times):
    driver_availability = []
    for driver in drivers:
        driver_id = driver['id']
        if order_deadline:
            hours_on_deadline = calculate_driver_workload_hours(driver_id, orders_for_algo, order_deadline, custom_task_times)
            available_hours = 12.0 - hours_on_deadline
        else:
            total_hours = driver_workload_hours.get(driver_id, 0.0)
            available_hours = 12.0 - (total_hours % 12.0) if total_hours > 0 else 12.0
        
        driver_availability.append({
            'driver_id': driver_id,
            'driver_name': driver.get('name', 'Onbekend'),
            'available_hours': max(0.0, available_hours)
        })
    return driver_availability

def build_order_info(order, custom_task_times=None):
    task_type_id = order.get('task_type_id')
    task_type_name = get_task_type_name(task_type_id, order.get('TaskTypes'))
    
    order_info = {
        'id': order.get('id'),
        'deadline': order.get('deadline'),
        'task_type': task_type_name,
        'task_type_id': task_type_id,
        'product_type': order.get('product_type'),
        'created_at': order.get('created_at'),
        'address': format_address_data(order.get('Address')),
        'driver_id': order.get('driver_id'),
        'status': order.get('status'),
        'Weight': order.get('Weight') or order.get('weight')
    }
    
    address_id = order.get('address_id')
    customer_name, customer_lastname = get_customer_info_from_address(address_id)
    order_info['customer_name'] = customer_name
    order_info['customer_lastname'] = customer_lastname
    
    if custom_task_times and task_type_id:
        order_for_time = order_info.copy()
        if task_type_id in custom_task_times:
            order_for_time['_custom_time_per_1000kg'] = custom_task_times[task_type_id]
        order_info['estimated_time_hours'] = calculate_order_time_hours(
            order_for_time, 
            custom_task_times if task_type_id in custom_task_times else None
        )
    
    return order_info

def validate_user_type(required_type):
    user_type = session.get('user_type', 'customer')
    if user_type != required_type:
        flash(f"Je hebt geen toegang tot deze pagina.", "error")
        return False
    return True

def get_custom_task_times(company_id):
    try:
        result = supabase.table('TaskTypes').select('id, task_type, time_per_1000kg').eq('company_id', company_id).execute()
        if result.data:
            return {tt['id']: float(tt.get('time_per_1000kg', 1.0)) for tt in result.data}
    except Exception:
        pass
    return {}

def get_previous_orders_for_customer(client_id):
    previous_orders = []
    if not client_id:
        return previous_orders
    try:
        addresses_result = supabase.table('Address').select('id').eq('client_id', client_id).execute()
        address_ids = [addr['id'] for addr in addresses_result.data] if addresses_result.data else []
        if not address_ids:
            return previous_orders
        orders_result = supabase.table('Orders').select('*, Address!orders_address_id_fkey(*), TaskTypes(*)').in_('address_id', address_ids).eq('status', 'completed').order('created_at', desc=True).limit(10).execute()
        if orders_result and orders_result.data:
            for order in orders_result.data:
                task_type_name = None
                task_type_id = order.get('task_type_id')
                company_id_from_task = None
                if order.get('TaskTypes'):
                    task_type_name = order['TaskTypes'].get('task_type')
                    company_id_from_task = order['TaskTypes'].get('company_id')
                elif task_type_id:
                    try:
                        task_type_result = supabase.table('TaskTypes').select('task_type, company_id').eq('id', task_type_id).limit(1).execute()
                        if task_type_result.data:
                            task_type_name = task_type_result.data[0].get('task_type')
                            company_id_from_task = task_type_result.data[0].get('company_id')
                    except:
                        pass
                order_info = {
                    'id': order.get('id'),
                    'task_type': task_type_name,
                    'task_type_id': task_type_id,
                    'product_type': order.get('product_type'),
                    'weight': order.get('Weight') or order.get('weight'),
                    'company_id': company_id_from_task,
                    'company_name': None,
                    'address_id': order.get('address_id'),
                    'address': None,
                    'deadline': order.get('deadline'),
                    'created_at': order.get('created_at')
                }
                if company_id_from_task:
                    try:
                        company_result = supabase.table('Companies').select('name').eq('id', company_id_from_task).limit(1).execute()
                        if company_result.data:
                            order_info['company_name'] = company_result.data[0].get('name')
                    except:
                        pass
                if order.get('Address'):
                    addr = order['Address']
                    order_info['address'] = {
                        'id': addr.get('id'),
                        'street_name': addr.get('street_name'),
                        'house_number': addr.get('house_number'),
                        'city': addr.get('city'),
                        'phone_number': addr.get('phone_number')
                    }
                previous_orders.append(order_info)
    except Exception:
        pass
    return filter_duplicate_orders(previous_orders)

def get_companies_list():
    companies = []
    try:
        companies_result = supabase.table('Companies').select('id, name, emailaddress').order('name').execute()
        if companies_result.data:
            companies = [{'id': c['id'], 'name': c['name']} for c in companies_result.data]
    except Exception:
        pass
    return companies

def get_addresses_for_client(client_id):
    addresses = []
    if not client_id:
        return addresses
    try:
        addresses_result = supabase.table('Address').select('*').eq('client_id', client_id).order('created_at', desc=False).execute()
        if addresses_result.data:
            addresses = addresses_result.data
    except Exception:
        pass
    return addresses

def build_order_info_for_edit(order_data):
    task_type_name = None
    task_type_id = order_data.get('task_type_id')
    if order_data.get('TaskTypes'):
        task_type_name = order_data['TaskTypes'].get('task_type')
    elif task_type_id:
        try:
            task_type_result = supabase.table('TaskTypes').select('task_type').eq('id', task_type_id).limit(1).execute()
            if task_type_result.data:
                task_type_name = task_type_result.data[0].get('task_type')
        except Exception:
            pass
    order_info = {
        'id': order_data.get('id'),
        'deadline': order_data.get('deadline'),
        'task_type': task_type_name,
        'task_type_id': task_type_id,
        'product_type': order_data.get('product_type'),
        'weight': order_data.get('Weight') or order_data.get('weight'),
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
    if task_type_id and order_data.get('TaskTypes'):
        company_id = order_data['TaskTypes'].get('company_id')
        if company_id:
            try:
                company_result = supabase.table('Companies').select('id, name').eq('id', company_id).limit(1).execute()
                if company_result.data:
                    company = company_result.data[0]
                    order_info['company'] = {'name': company.get('name'), 'id': company.get('id')}
            except Exception:
                pass
    return order_info

def parse_date_utc(date_str):
    if not date_str:
        return None
    try:
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
        dt = datetime.strptime(date_str, '%Y-%m-%d')
        return dt.replace(tzinfo=timezone.utc)
    except:
        return None

def kg_to_tons(weight_kg):
    if weight_kg is None:
        return 0.0
    try:
        return float(weight_kg) / 1000.0
    except (ValueError, TypeError):
        return 0.0

def calculate_statistics_by_task_type(orders, custom_task_types):
    stats = {}
    for task_type_id, task_type_name in custom_task_types.items():
        stats[task_type_id] = {'name': task_type_name, 'tons': 0.0}
    for order in orders:
        task_type_id = order.get('task_type_id')
        weight = order.get('Weight') or order.get('weight')
        if task_type_id and task_type_id in custom_task_types:
            if task_type_id not in stats:
                stats[task_type_id] = {'name': custom_task_types[task_type_id], 'tons': 0.0}
            stats[task_type_id]['tons'] += kg_to_tons(weight)
    return stats

def generate_available_months(all_orders):
    available_months = []
    if not all_orders:
        return available_months
    first_date = None
    for order in all_orders:
        order_date_str = order.get('created_at') or order.get('deadline')
        order_date = parse_date_utc(order_date_str)
        if order_date:
            if first_date is None or order_date < first_date:
                first_date = order_date
    if first_date:
        month_names = {1: 'januari', 2: 'februari', 3: 'maart', 4: 'april', 5: 'mei', 6: 'juni', 7: 'juli', 8: 'augustus', 9: 'september', 10: 'oktober', 11: 'november', 12: 'december'}
        now = datetime.now(timezone.utc)
        current = datetime(first_date.year, first_date.month, 1, tzinfo=timezone.utc)
        end = datetime(now.year, now.month, 1, tzinfo=timezone.utc)
        while current <= end:
            month_str = f"{current.year}-{current.month:02d}"
            month_label = f"{month_names[current.month].capitalize()} {current.year}"
            available_months.append({'value': month_str, 'label': month_label})
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1, tzinfo=timezone.utc)
            else:
                current = datetime(current.year, current.month + 1, 1, tzinfo=timezone.utc)
        available_months.reverse()
    return available_months


@bp.before_request
def load_current_user():
    g.current_user_id = session.get('email')
    g.current_user_email = session.get('email')
    g.current_user_type = session.get('user_type', 'customer')
    
    if g.current_user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        g.current_user_display_name = f"{first_name} {last_name}" if first_name and last_name else g.current_user_email
    else:
        g.current_user_display_name = g.current_user_email


@bp.route('/')
def home():
    user_type = session.get('user_type', 'customer')
    user_email = session.get('email')
    
    if user_type == 'company' and user_email:
        try:
            sb = supabase
            company_result = sb.table('Companies').select('id, name').eq('emailaddress', user_email).limit(1).execute()
            company_id = None
            company_name = None
            
            if company_result.data:
                company_id = company_result.data[0]['id']
                company_name = company_result.data[0].get('name', 'Bedrijf')
            
            stats = {
                'total_orders': 0,
                'pending_orders': 0,
                'completed_orders': 0,
                'recent_orders': []
            }
            
            if company_id:
                orders_result = sb.table('Orders').select('id, deadline, created_at, status, TaskTypes!inner(company_id)').eq('TaskTypes.company_id', company_id).execute()
                if orders_result.data:
                    stats['total_orders'] = len(orders_result.data)
                    stats['completed_orders'] = sum(1 for o in orders_result.data if o.get('status') == 'completed')
                    stats['pending_orders'] = stats['total_orders'] - stats['completed_orders']
                    stats['recent_orders'] = sorted(orders_result.data, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
            
            return render_template('home.html', user_type='company', company_name=company_name, stats=stats)
        except Exception as e:
            flash(f"Error loading company home: {e}", "error")
            return render_template('home.html', user_type='company', company_name=None, stats={'total_orders': 0, 'pending_orders': 0, 'completed_orders': 0, 'recent_orders': []})
    
    if user_type == 'driver' and user_email:
        return render_template('home.html', user_type='driver')
    
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

            sb = supabase

            client_id = None
            company_id = None
            driver_id = None
            first_name = None
            last_name = None
            user_type = None

            result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', username).limit(1).execute()
            if result.data:
                row = result.data[0]
                client_id = row['id']
                first_name = row.get('Name')
                last_name = row.get('Lastname')
                user_type = 'customer'
            else:
                result = sb.table('Companies').select('id, name').eq('emailaddress', username).limit(1).execute()
                if result.data:
                    company_id = result.data[0]['id']
                    user_type = 'company'
                else:
                    result = sb.table('Drivers').select('id, name').eq('email_address', username).limit(1).execute()
                    if result.data:
                        driver_id = result.data[0]['id']
                        user_type = 'driver'

            if not user_type:
                flash("Geen gebruiker gevonden met deze gebruikersnaam.", "error")
                return render_template('login.html')

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
            
            sb = supabase

            if user_type == 'customer':
                existing = sb.table('Client').select('id').eq('emailaddress', username).limit(1).execute()
                if existing.data:
                    flash("Er bestaat al een klant met deze gebruikersnaam. Log in.", "info")
                    return redirect(url_for('routes.login', user_type=user_type))
                    
                sb.table('Client').insert({
                    "emailaddress": username,
                    "Name": first_name,
                    "Lastname": last_name,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()
                            
            elif user_type == 'company':
                existing = sb.table('Companies').select('id').eq('emailaddress', username).limit(1).execute()
                if existing.data:
                    flash("Er bestaat al een bedrijf met deze gebruikersnaam. Log in.", "info")
                    return redirect(url_for('routes.login', user_type=user_type))

                company_result = sb.table('Companies').insert({
                    "name": username,
                    "emailaddress": username,
                    "created_at": datetime.utcnow().isoformat()
                }).execute()
                
                if company_result.data:
                    pass

            elif user_type == 'driver':
                existing = sb.table('Drivers').select('id').eq('email_address', username).limit(1).execute()
                if existing.data:
                    flash("Er bestaat al een chauffeur met deze gebruikersnaam. Log in.", "info")
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
    custom_task_types = []
    sb = supabase
    
    if user_type == 'driver':
        try:
            driver_result = sb.table('Drivers').select('id, name, company_id').eq('email_address', session.get('email')).limit(1).execute()
            if driver_result.data:
                driver_data = driver_result.data[0]
                if driver_data.get('name'):
                    user_ctx['display_name'] = driver_data['name']
                company_id = driver_data.get('company_id')
                if company_id:
                    company_result = sb.table('Companies').select('name').eq('id', company_id).limit(1).execute()
                    if company_result.data:
                        user_ctx['company_name'] = company_result.data[0].get('name', '')
        except Exception:
            pass
    
    elif user_type == 'customer':
        first_name = session.get('first_name', '')
        last_name = session.get('last_name', '')
        if not (first_name or last_name):
            try:
                client_id = session.get('client_id') or get_client_id()
                if client_id:
                    client_result = sb.table('Client').select('Name, Lastname').eq('id', client_id).limit(1).execute()
                    if client_result.data:
                        client_data = client_result.data[0]
                        first_name = client_data.get('Name', '')
                        last_name = client_data.get('Lastname', '')
                        if first_name or last_name:
                            session['first_name'] = first_name
                            session['last_name'] = last_name
            except Exception:
                pass
        
        if first_name or last_name:
            user_ctx['first_name'] = first_name
            user_ctx['last_name'] = last_name
            user_ctx['display_name'] = f"{first_name} {last_name}".strip()
        
        try:
            client_id = get_client_id()
            if client_id:
                addresses_result = sb.table('Address').select('*').eq('client_id', client_id).order('created_at', desc=False).execute()
                addresses = addresses_result.data if addresses_result.data else []
        except Exception as e:
            flash(f"Kon adressen niet ophalen: {e}", "error")
    
    elif user_type == 'company':
        try:
            company_id = get_company_id()
            if company_id:
                task_types_result = sb.table('TaskTypes').select('*').eq('company_id', company_id).order('task_type').execute()
                custom_task_types = task_types_result.data if task_types_result.data else []
        except Exception as e:
            flash(f"Kon taaktypes niet ophalen: {e}", "error")
    
    return render_template('profile.html', user=user_ctx, addresses=addresses, custom_task_types=custom_task_types)


@bp.route('/profile/add-address', methods=['POST'])
@login_required
def add_address():
    if not validate_user_type('customer'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        client_id = get_client_id()
        
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
    if not validate_user_type('customer'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        client_id = get_client_id()
        
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for('routes.profile'))
        
        address_result = sb.table('Address').select('client_id').eq('id', address_id).eq('client_id', client_id).limit(1).execute()
        if not address_result.data or len(address_result.data) == 0:
            flash("Adres niet gevonden of je hebt geen toegang tot dit adres.", "error")
            return redirect(url_for('routes.profile'))
        
        orders_result = sb.table('Orders').select('id').eq('address_id', address_id).limit(1).execute()
        if orders_result.data:
            flash("Dit adres kan niet worden verwijderd omdat het gebruikt wordt in een bestelling.", "error")
            return redirect(url_for('routes.profile'))
        
        delete_result = sb.table('Address').delete().eq('id', address_id).eq('client_id', client_id).execute()
        
        if delete_result.data:
            flash("Adres succesvol verwijderd!", "success")
        else:
            flash("Adres kon niet worden verwijderd.", "error")
    except Exception as e:
        flash(f"Fout bij het verwijderen van adres: {str(e)}", "error")
    
    return redirect(url_for('routes.profile'))

@bp.route('/company/add-task-type', methods=['POST'])
@login_required
def company_add_task_type():
    if not validate_user_type('company'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        company_email = session.get('email')
        company_id = None
        
        company_id = get_company_id()
        
        if not company_id:
            flash("Bedrijf niet gevonden.", "error")
            return redirect(url_for('routes.profile'))
        
        task_type_name = request.form.get('task_type_name', '').strip().lower()
        time_per_1000kg_str = request.form.get('time_per_1000kg', '').strip()
        
        if not task_type_name:
            flash("Taaktype naam is verplicht.", "error")
            return redirect(url_for('routes.profile'))
        
        try:
            time_per_1000kg = float(time_per_1000kg_str)
            if time_per_1000kg <= 0:
                raise ValueError("Tijd moet groter zijn dan 0")
        except (ValueError, TypeError):
            flash("Ongeldige tijd per 1000kg. Voer een geldig positief getal in (bijv. 0.1 voor 0.1 uur per 1000kg).", "error")
            return redirect(url_for('routes.profile'))
        
        existing = sb.table('TaskTypes').select('id').eq('company_id', company_id).eq('task_type', task_type_name).limit(1).execute()
        if existing.data:
            flash(f"Taaktype '{task_type_name}' bestaat al voor dit bedrijf.", "error")
            return redirect(url_for('routes.profile'))
        
        try:
            insert_result = sb.table('TaskTypes').insert({
                'company_id': company_id,
                'task_type': task_type_name,
                'time_per_1000kg': time_per_1000kg
            }).execute()
            
            if insert_result.data:
                flash(f"Taaktype '{task_type_name}' succesvol toegevoegd!", "success")
            else:
                flash("Taaktype kon niet worden toegevoegd. Controleer de database instellingen.", "error")
        except Exception as insert_error:
            error_msg = str(insert_error)
            if 'row-level security' in error_msg.lower() or '42501' in error_msg:
                flash(f"Fout: Row-Level Security policy blokkeert het toevoegen. Neem contact op met de beheerder om de RLS policies voor de TaskTypes tabel aan te passen. Details: {error_msg}", "error")
            else:
                flash(f"Fout bij het toevoegen van taaktype: {error_msg}", "error")
            raise
    except Exception as e:
        if 'row-level security' not in str(e).lower() and '42501' not in str(e):
            flash(f"Fout bij het toevoegen van taaktype: {str(e)}", "error")
    
    return redirect(url_for('routes.profile'))

@bp.route('/company/delete-task-type/<int:task_type_id>', methods=['POST'])
@login_required
def company_delete_task_type(task_type_id):
    if not validate_user_type('company'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        company_email = session.get('email')
        company_id = None
        
        company_id = get_company_id()
        
        if not company_id:
            flash("Bedrijf niet gevonden.", "error")
            return redirect(url_for('routes.profile'))
        
        delete_result = sb.table('TaskTypes').delete().eq('id', task_type_id).eq('company_id', company_id).execute()
        if delete_result.data:
            flash("Taaktype succesvol verwijderd!", "success")
        else:
            flash("Taaktype niet gevonden of je hebt geen toegang.", "error")
    except Exception as e:
        flash(f"Fout bij het verwijderen van taaktype: {str(e)}", "error")
    
    return redirect(url_for('routes.profile'))


@bp.route('/customer/orders')
@login_required
def customer_orders():
    if not validate_user_type('customer'):
        return redirect(url_for('routes.profile'))
    
    try:
        client_id = get_client_id()
        if not client_id:
            return render_template('customer_orders.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))
        
        addresses_result = supabase.table('Address').select('id').eq('client_id', client_id).execute()
        address_ids = [addr['id'] for addr in addresses_result.data] if addresses_result.data else []
        
        if not address_ids:
            return render_template('customer_orders.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))
        
        orders_result = supabase.table('Orders').select('*, Address!orders_address_id_fkey(*), TaskTypes(*)').in_('address_id', address_ids).order('created_at', desc=True).limit(100).execute()
        
        orders = []
        if orders_result and orders_result.data:
            for order in orders_result.data:
                order_info = {
                    'id': order.get('id'),
                    'deadline': order.get('deadline'),
                    'task_type': get_task_type_name(order.get('task_type_id'), order.get('TaskTypes')),
                    'product_type': order.get('product_type'),
                    'created_at': order.get('created_at'),
                    'address': format_address_data(order.get('Address')),
                    'company': None,
                    'driver_id': order.get('driver_id'),
                    'driver_name': None,
                    'status': order.get('status')
                }
                
                task_type_id = order.get('task_type_id')
                if task_type_id and order.get('TaskTypes'):
                    company_id_from_task = order['TaskTypes'].get('company_id')
                    if company_id_from_task:
                        try:
                            company_result = supabase.table('Companies').select('name, id').eq('id', company_id_from_task).limit(1).execute()
                            if company_result.data:
                                company = company_result.data[0]
                                order_info['company'] = {'name': company.get('name'), 'id': company.get('id')}
                        except Exception:
                            pass
                
                driver_id = order.get('driver_id')
                if driver_id:
                    try:
                        driver_result = supabase.table('Drivers').select('name').eq('id', driver_id).limit(1).execute()
                        if driver_result.data:
                            order_info['driver_name'] = driver_result.data[0].get('name', 'Onbekend')
                    except Exception:
                        pass
                
                orders.append(order_info)
        
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('customer_orders.html', active_orders=active_orders, completed_orders=completed_orders, user_email=session.get('email', ''))
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('customer_orders.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))


@bp.route('/customer/cancel-order/<int:order_id>', methods=['POST'])
@login_required
def cancel_order(order_id):
    if not validate_user_type('customer'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        client_id = get_client_id()
        
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order_result = sb.table('Orders').select('id, driver_id, status, address_id, Address!orders_address_id_fkey!inner(client_id)').eq('id', order_id).eq('Address.client_id', client_id).limit(1).execute()
        
        if not order_result.data or len(order_result.data) == 0:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order = order_result.data[0]
        
        if order.get('driver_id'):
            flash("Deze bestelling kan niet worden geannuleerd omdat deze al is toegewezen aan een chauffeur.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        if order.get('status') == 'completed':
            flash("Deze bestelling kan niet worden geannuleerd omdat deze al is voltooid.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        delete_result = sb.table('Orders').delete().eq('id', order_id).execute()
        
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
    if not validate_user_type('customer'):
        return redirect(url_for('routes.profile'))
    
    sb = supabase
    
    try:
        client_id = get_client_id()
        if not client_id:
            flash("Klant niet gevonden.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order_result = sb.table('Orders').select('*, Address!orders_address_id_fkey!inner(*), TaskTypes(*)').eq('id', order_id).eq('Address.client_id', client_id).limit(1).execute()
        if not order_result.data:
            flash("Bestelling niet gevonden of je hebt geen toegang tot deze bestelling.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        order_data = order_result.data[0]
        driver_id = order_data.get('driver_id')
        if driver_id:
            driver_name = "een chauffeur"
            try:
                driver_result = sb.table('Drivers').select('name').eq('id', driver_id).limit(1).execute()
                if driver_result.data:
                    driver_name = driver_result.data[0].get('name') or driver_name
            except Exception:
                pass
            flash(f"Deze bestelling kan niet meer bewerkt worden omdat deze is toegewezen aan {driver_name}.", "error")
            return redirect(url_for('routes.customer_orders'))
        
        companies = get_companies_list()
        addresses = get_addresses_for_client(client_id)
        order_info = build_order_info_for_edit(order_data)
        
        template_vars = {'order': order_info, 'companies': companies, 'addresses': addresses}
        
        if request.method == 'POST':
            try:
                address_id_str = request.form.get("address_id")
                if not address_id_str:
                    flash("Selecteer een adres.", "error")
                    return render_template('edit_order.html', **template_vars)
                
                try:
                    selected_address_id = int(address_id_str)
                    address_check = sb.table('Address').select('id').eq('id', selected_address_id).eq('client_id', client_id).limit(1).execute()
                    if not address_check.data:
                        flash("Ongeldig adres geselecteerd.", "error")
                        return render_template('edit_order.html', **template_vars)
                except (ValueError, TypeError):
                    flash("Ongeldig adres geselecteerd.", "error")
                    return render_template('edit_order.html', **template_vars)
                
                company_id = request.form.get("company_id")
                if not company_id:
                    flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                    return render_template('edit_order.html', **template_vars)
                
                try:
                    company_id = int(company_id)
                except (ValueError, TypeError):
                    flash("Ongeldig bedrijf geselecteerd.", "error")
                    return render_template('edit_order.html', **template_vars)
                
                task_type_value = request.form.get("task_type")
                task_type_id = None
                if task_type_value:
                    try:
                        task_type_id = int(task_type_value)
                    except (ValueError, TypeError):
                        pass
                
                weight_str = request.form.get("weight", "").strip()
                weight = None
                if weight_str:
                    try:
                        weight = float(weight_str)
                    except (ValueError, TypeError):
                        flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                        return render_template('edit_order.html', **template_vars)
                
                order_update_data = {
                    "deadline": request.form.get("deadline"),
                    "task_type_id": task_type_id if task_type_id else None,
                    "product_type": request.form.get("product_type"),
                    "Weight": weight,
                    "address_id": selected_address_id
                }
                
                order_update_result = sb.table('Orders').update(order_update_data).eq('id', order_id).execute()
                
                if order_update_result.data:
                    flash("Bestelling bijgewerkt!", "success")
                    return redirect(url_for('routes.customer_orders'))
                else:
                    flash("Bestelling kon niet worden bijgewerkt.", "error")
            except Exception as e:
                flash(f"Fout bij het bijwerken van bestelling: {str(e)}", "error")
                return render_template('edit_order.html', **template_vars)
        
        return render_template('edit_order.html', **template_vars)
    
    except Exception as e:
        flash(f"Fout bij het ophalen van bestelling: {str(e)}", "error")
        return redirect(url_for('routes.customer_orders'))


@bp.route('/company/dashboard')
@login_required
def company_dashboard():
    if not validate_user_type('company'):
        return redirect(url_for('routes.profile'))
    
    try:
        company_id = get_company_id()
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return render_template('company_dashboard.html', orders=[], drivers=[], user_email=session.get('email', ''))
        
        drivers_result = supabase.table('Drivers').select('id, name, email_address').eq('company_id', company_id).order('name').execute()
        drivers = drivers_result.data if drivers_result.data else []
        custom_task_times = get_custom_task_times(company_id)
        
        orders_result = supabase.table('Orders').select('*, Address!orders_address_id_fkey(*), TaskTypes!inner(*)').eq('TaskTypes.company_id', company_id).order('created_at', desc=True).limit(100).execute()
        all_orders_raw = orders_result.data if orders_result.data else []
        
        driver_workload_hours = {}
        if drivers and all_orders_raw:
            orders_for_algo = convert_orders_for_algorithm(all_orders_raw)
            for driver in drivers:
                driver_workload_hours[driver['id']] = calculate_driver_workload_hours(
                    driver['id'], orders_for_algo, None, custom_task_times
                )
        
        orders = []
        orders_for_algo = convert_orders_for_algorithm(all_orders_raw) if all_orders_raw else []
        
        for order in all_orders_raw:
            order_info = build_order_info(order, custom_task_times)
            
            if not order_info.get('driver_id') and drivers:
                suggestion = suggest_best_driver(drivers, order_info, driver_workload_hours, orders_for_algo, custom_task_times)
                if suggestion:
                    order_info['suggested_driver'] = suggestion
                
                order_deadline_date = None
                if order_info.get('deadline'):
                    try:
                        order_deadline_date = datetime.strptime(order_info['deadline'], '%Y-%m-%d').date()
                    except (ValueError, TypeError):
                        pass
                
                order_info['driver_availability'] = calculate_driver_availability(
                    drivers, orders_for_algo, order_deadline_date, driver_workload_hours, custom_task_times
                )
            
            orders.append(order_info)
        
        orders = sort_orders_by_priority(orders)
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('company_dashboard.html', 
                             active_orders=active_orders, 
                             completed_orders=completed_orders, 
                             drivers=drivers, 
                             user_email=session.get('email', ''))
    except Exception as e:
        flash(f"Fout bij het ophalen van bestellingen: {str(e)}", "error")
        return render_template('company_dashboard.html', active_orders=[], completed_orders=[], drivers=[], user_email=session.get('email', ''))


@bp.route('/company/statistics')
@login_required
def company_statistics():
    if not validate_user_type('company'):
        return redirect(url_for('routes.profile'))
    
    try:
        sb = supabase
        company_email = session.get('email')
        company_id = None
        company_name = None
        
        company_result = sb.table('Companies').select('id, name').eq('emailaddress', company_email).limit(1).execute()
        if company_result.data:
            company_id = company_result.data[0]['id']
            company_name = company_result.data[0].get('name', 'Bedrijf')
        
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return redirect(url_for('routes.home'))
        
        orders_result = sb.table('Orders').select('*, TaskTypes!inner(*)').eq('TaskTypes.company_id', company_id).eq('status', 'completed').execute()
        all_orders = orders_result.data if orders_result.data else []
        
        selected_month = request.args.get('month')
        if not selected_month:
            now = datetime.now(timezone.utc)
            selected_month = f"{now.year}-{now.month:02d}"
        
        try:
            selected_year, selected_month_num = map(int, selected_month.split('-'))
            if not (1 <= selected_month_num <= 12):
                raise ValueError("Ongeldige maand")
        except (ValueError, AttributeError):
            now = datetime.now(timezone.utc)
            selected_year = now.year
            selected_month_num = now.month
            selected_month = f"{selected_year}-{selected_month_num:02d}"
        
        now = datetime.now(timezone.utc)
        current_year_start = datetime(now.year, 1, 1, tzinfo=timezone.utc)
        
        selected_month_start = datetime(selected_year, selected_month_num, 1, tzinfo=timezone.utc)
        if selected_month_num == 12:
            selected_month_end = datetime(selected_year + 1, 1, 1, tzinfo=timezone.utc)
        else:
            selected_month_end = datetime(selected_year, selected_month_num + 1, 1, tzinfo=timezone.utc)
        
        orders_selected_month = []
        orders_this_year = []
        for order in all_orders:
            order_date_str = order.get('created_at') or order.get('deadline')
            order_date = parse_date_utc(order_date_str)
            if order_date:
                if selected_month_start <= order_date < selected_month_end:
                    orders_selected_month.append(order)
                if order_date >= current_year_start:
                    orders_this_year.append(order)
        
        custom_task_types_result = sb.table('TaskTypes').select('id, task_type').eq('company_id', company_id).order('task_type').execute()
        custom_task_types = {}
        if custom_task_types_result.data:
            for tt in custom_task_types_result.data:
                custom_task_types[tt['id']] = tt['task_type']
        
        stats_by_task_selected_month = calculate_statistics_by_task_type(orders_selected_month, custom_task_types)
        year_stats_by_task = calculate_statistics_by_task_type(orders_this_year, custom_task_types)
        total_year_tons = sum(kg_to_tons(order.get('Weight') or order.get('weight')) for order in orders_this_year)
        
        total_selected_month = sum(d['tons'] for d in stats_by_task_selected_month.values())
        
        available_months = generate_available_months(all_orders)
        
        month_names = {1: 'januari', 2: 'februari', 3: 'maart', 4: 'april', 5: 'mei', 6: 'juni', 7: 'juli', 8: 'augustus', 9: 'september', 10: 'oktober', 11: 'november', 12: 'december'}
        selected_month_label = f"{month_names[selected_month_num].capitalize()} {selected_year}"
        
        current_year = now.year
        
        return render_template('company_statistics.html', 
                             company_name=company_name,
                             stats_by_task_selected_month=stats_by_task_selected_month,
                             stats_by_task_year=year_stats_by_task,
                             total_year_tons=total_year_tons,
                             total_selected_month=total_selected_month,
                             selected_month=selected_month,
                             selected_month_label=selected_month_label,
                             selected_year=current_year,
                             available_months=available_months)
    except Exception as e:
        flash(f"Fout bij het ophalen van statistieken: {str(e)}", "error")
        return redirect(url_for('routes.home'))


@bp.route('/company/assign-driver/<int:order_id>', methods=['POST'])
@login_required
def company_assign_driver(order_id):
    if not validate_user_type('company'):
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
        sb = supabase
        company_email = session.get('email')

        company_id = get_company_id()
        if not company_id:
            flash("Bedrijf niet gevonden. Neem contact op met de beheerder.", "error")
            return redirect(url_for('routes.company_dashboard'))

        driver_result = sb.table('Drivers').select('id').eq('id', driver_id_int).eq('company_id', company_id).limit(1).execute()
        if not driver_result.data or len(driver_result.data) == 0:
            flash("Deze chauffeur hoort niet bij jouw bedrijf.", "error")
            return redirect(url_for('routes.company_dashboard'))

        order_check = sb.table('Orders').select('task_type_id, TaskTypes!inner(company_id)').eq('id', order_id).eq('TaskTypes.company_id', company_id).limit(1).execute()
        if not order_check.data:
            flash("Bestelling niet gevonden of je hebt geen toegang.", "error")
            return redirect(url_for('routes.company_dashboard'))
        
        update_result = sb.table('Orders').update({
            'driver_id': driver_id_int,
            'status': 'accepted'
        }).eq('id', order_id).execute()

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
    if not validate_user_type('driver'):
        return redirect(url_for('routes.profile'))
    
    user_email = session.get('email')
    
    if request.method == 'POST':
        company_id = request.form.get('company_id')
        if not company_id:
            flash("Selecteer een bedrijf.", "error")
            return redirect(url_for('routes.driver_select_company'))
        
        try:
            sb = supabase
            driver_result = sb.table('Drivers').select('id').eq('email_address', user_email).limit(1).execute()
            
            if driver_result.data:
                driver_id = driver_result.data[0]['id']
                sb.table('Drivers').update({'company_id': int(company_id)}).eq('id', driver_id).execute()
            else:
                sb.table('Drivers').insert({
                    'email_address': user_email,
                    'company_id': int(company_id),
                    'name': user_email.split('@')[0]
                }).execute()
            
            flash("Bedrijf succesvol geselecteerd!", "success")
            return redirect(url_for('routes.home'))
        except Exception as e:
            flash(f"Fout bij het selecteren van bedrijf: {str(e)}", "error")
    
    try:
        sb = supabase
        companies_result = sb.table('Companies').select('id, name').order('name').execute()
        companies = companies_result.data if companies_result.data else []
        
        driver_result = sb.table('Drivers').select('company_id').eq('email_address', user_email).limit(1).execute()
        if driver_result.data and driver_result.data[0].get('company_id'):
            return redirect(url_for('routes.home'))
        
        return render_template('driver_select_company.html', companies=companies)
    except Exception as e:
        flash(f"Fout bij het ophalen van bedrijven: {str(e)}", "error")
        return render_template('driver_select_company.html', companies=[])


@bp.route('/driver/dashboard')
@login_required
def driver_dashboard():
    if not validate_user_type('driver'):
        return redirect(url_for('routes.profile'))
    
    try:
        user_email = session.get('email')
        
        driver_result = supabase.table('Drivers').select('id, company_id').eq('email_address', user_email).limit(1).execute()
        if not driver_result.data:
            return redirect(url_for('routes.driver_select_company'))
        
        driver_id = driver_result.data[0]['id']
        company_id = driver_result.data[0].get('company_id')
        
        if not company_id:
            return redirect(url_for('routes.driver_select_company'))
        
        custom_task_times = get_custom_task_times(company_id)
        
        orders_result = supabase.table('Orders').select('*, Address!orders_address_id_fkey(*), TaskTypes(*)').eq('driver_id', driver_id).in_('status', ['accepted', 'completed']).order('deadline', desc=False).limit(100).execute()
        
        orders = []
        if orders_result.data:
            for order in orders_result.data:
                order_info = build_order_info(order, custom_task_times)
                order_info['weight'] = order.get('Weight') or order.get('weight')
                
                order_for_time = {
                    'task_type_id': order.get('task_type_id'),
                    'Weight': order_info['weight'],
                    'weight': order_info['weight']
                }
                if order.get('task_type_id') and order.get('task_type_id') in custom_task_times:
                    order_for_time['_custom_time_per_1000kg'] = custom_task_times[order.get('task_type_id')]
                
                order_info['work_time_hours'] = max(0.0, calculate_order_time_hours(order_for_time, custom_task_times) - 0.75)
                
                if order.get('Companies'):
                    order_info['company'] = {'name': order['Companies'].get('name')}
                
                orders.append(order_info)
        
        active_orders = [o for o in orders if o.get('status') != 'completed']
        completed_orders = [o for o in orders if o.get('status') == 'completed']
        
        return render_template('driver_dashboard.html', active_orders=active_orders, completed_orders=completed_orders, user_email=user_email)
    except Exception as e:
        flash(f"Fout bij het ophalen van ritten: {str(e)}", "error")
        return render_template('driver_dashboard.html', active_orders=[], completed_orders=[], user_email=session.get('email', ''))

@bp.route('/driver/complete-order/<int:order_id>', methods=['POST'])
@login_required
def driver_complete_order(order_id):
    if not validate_user_type('driver'):
        return redirect(url_for('routes.profile'))

    try:
        sb = supabase
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
    user_type = session.get('user_type', 'customer')
    if user_type == 'company':
        flash("Bedrijven kunnen geen bestellingen plaatsen. Gebruik het dashboard om bestellingen te bekijken.", "error")
        return redirect(url_for('routes.company_dashboard'))
    
    sb = supabase
    client_id = get_client_id()
    companies = get_companies_list()
    addresses = get_addresses_for_client(client_id)
    previous_orders = get_previous_orders_for_customer(client_id)
    previous_orders.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    if request.method == 'POST':
        try:
            address_id_str = request.form.get("address_id")
            
            if address_id_str:
                try:
                    address_id = int(address_id_str)
                    client_id = get_client_id()
                    
                    if client_id:
                        address_check = sb.table('Address').select('id').eq('id', address_id).eq('client_id', client_id).limit(1).execute()
                        if not address_check.data or len(address_check.data) == 0:
                            flash("Ongeldig adres geselecteerd.", "error")
                            return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
                except (ValueError, TypeError):
                    flash("Ongeldig adres geselecteerd.", "error")
                    return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
            else:
                flash("Selecteer een adres of voeg eerst een adres toe in je profiel.", "error")
                return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)

            company_id = request.form.get("company_id")
            if not company_id:
                flash("Bedrijf is verplicht. Selecteer een bedrijf.", "error")
                return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
            
            try:
                company_id = int(company_id)
            except (ValueError, TypeError):
                flash("Ongeldig bedrijf geselecteerd.", "error")
                return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
            
            weight = None
            weight_str = request.form.get("weight", "").strip()
            if weight_str:
                try:
                    weight = float(weight_str)
                except (ValueError, TypeError):
                    flash("Ongeldig gewicht. Voer een geldig getal in.", "error")
                    return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
            
            if weight is None or weight <= 0:
                flash("Gewicht is verplicht en moet groter zijn dan 0.", "error")
                return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)
            
            client_id = session.get('client_id')
            if not client_id:
                try:
                    customer_email = session.get('email')
                    client_result = sb.table('Client').select('id, Name, Lastname').eq('emailaddress', customer_email).limit(1).execute()
                    if client_result.data:
                        client_id = client_result.data[0]['id']
                        session['client_id'] = client_id
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
            
            task_type_value = request.form.get("task_type")
            task_type_id = None
            if task_type_value:
                try:
                    task_type_id = int(task_type_value)
                except (ValueError, TypeError):
                    pass
            
            order_data = {
                "deadline": request.form.get("deadline"),
                "task_type_id": task_type_id if task_type_id else None,
                "product_type": request.form.get("product_type"),
                "address_id": address_id,
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
            return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)

    return render_template('order.html', companies=companies, addresses=addresses, previous_orders=previous_orders)

@bp.route('/api/company/<int:company_id>/task-types', methods=['GET'])
def get_company_task_types(company_id):
    try:
        sb = supabase
        task_types_result = sb.table('TaskTypes').select('id, task_type').eq('company_id', company_id).order('task_type').execute()
        
        task_types = []
        if task_types_result.data:
            task_types = [{'id': tt['id'], 'name': tt['task_type']} for tt in task_types_result.data]
        
        from flask import jsonify
        return jsonify({'task_types': task_types, 'has_task_types': len(task_types) > 0})
    except Exception as e:
        from flask import jsonify
        return jsonify({'error': str(e)}), 500
