from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from datetime import datetime
from .config import supabase, Config
from supabase import create_client
bp = Blueprint('routes', __name__)

def get_authenticated_supabase():
    """Get Supabase client with session token if available"""
    # Always use a fresh client instance to avoid session conflicts
    client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
    # If user has an access token in session, set it for authenticated requests
    if session.get('sb_access_token') and session.get('sb_refresh_token'):
        try:
            client.auth.set_session(access_token=session.get('sb_access_token'), refresh_token=session.get('sb_refresh_token'))
        except Exception:
            # If session setting fails, continue with unauthenticated client
            pass
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


@bp.before_app_request
def load_current_user():
    g.current_user_id = session.get('sb_user_id')
    g.current_user_email = session.get('email')


@bp.route('/')
def home():
    return render_template('home.html')


@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not email or not password:
            flash("E-mail en wachtwoord zijn verplicht.", "error")
            return render_template('login.html')

        try:
            result = supabase.auth.sign_in_with_password({"email": email, "password": password})
            user = result.user
            if user is None:
                flash("Ongeldige inloggegevens.", "error")
                return render_template('login.html')

            # Persist minimal user info and session tokens for future API calls/refresh
            session['sb_user_id'] = user.id
            session['email'] = email
            if getattr(result, 'session', None):
                session['sb_access_token'] = result.session.access_token
                session['sb_refresh_token'] = result.session.refresh_token
            flash("Succesvol ingelogd!", "success")
            return redirect(url_for('routes.profile'))
        except Exception:
            flash("Inloggen mislukt. Controleer gegevens of probeer later opnieuw.", "error")
            return render_template('login.html')

    return render_template('login.html')


@bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        if not email or not password:
            flash("E-mail en wachtwoord zijn verplicht.", "error")
            return render_template('signup.html')

        try:
            result = supabase.auth.sign_up({"email": email, "password": password})
            if result.user is None:
                flash("Registratie mislukt. Probeer het opnieuw.", "error")
                return render_template('signup.html')

            flash("Account aangemaakt. Controleer je e-mail om te bevestigen.", "success")
            return redirect(url_for('routes.login'))
        except Exception:
            flash("Registratie mislukt. Probeer later opnieuw.", "error")
            return render_template('signup.html')

    return render_template('signup.html')


@bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    # Avoid DB call; pass minimal user context for UI
    user_ctx = {"emailaddress": session.get('email', '')}
    return render_template('profile.html', user=user_ctx)

@bp.route('/logout')
def logout():
    session.clear()
    flash("Uitgelogd.", "success")
    return redirect(url_for('routes.home'))


@bp.route('/order', methods=['GET', 'POST'])
@login_required
def order():
    if request.method == 'POST':
        try:
            # Get authenticated Supabase client
            sb = get_authenticated_supabase()
            
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
                return render_template('order.html')

            address_id = address_result.data[0]['id']

            # Create order via Supabase REST API
            order_data = {
                "deadline": request.form.get("deadline"),
                "task_type": request.form.get("task_type"),
                "product_type": request.form.get("product_type"),
                "address_id": address_id
            }
            order_result = sb.table('Orders').insert(order_data).execute()

            if order_result.data:
                flash("Bestelling geplaatst!", "success")
                return redirect(url_for('routes.home'))
            else:
                flash("Bestelling kon niet worden geplaatst.", "error")
        except Exception as e:
            flash(f"Fout bij het plaatsen van bestelling: {str(e)}", "error")
            return render_template('order.html')

    return render_template('order.html')
