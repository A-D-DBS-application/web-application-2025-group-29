from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from .models import get_user_by_email, insert_order, insert_farmer

bp = Blueprint('routes', __name__)

@bp.route('/')
def home():
    return render_template('home.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        user = get_user_by_email(email)
        if user:
            session['user'] = user
            flash("Succesvol ingelogd!", "success")
            return redirect(url_for('routes.profile'))
        else:
            flash("Gebruiker niet gevonden.", "error")
    return render_template('login.html')

@bp.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user' not in session:
        return redirect(url_for('routes.login'))
    user = session['user']
    return render_template('profile.html', user=user)

@bp.route('/order', methods=['GET', 'POST'])
def order():
    if 'user' not in session:
        return redirect(url_for('routes.login'))
    if request.method == 'POST':
        data = {
            "deadline": request.form["deadline"],
            "task_type": request.form["task_type"],
            "product_type": request.form["product_type"],
            "address_id": request.form["address_id"]
        }
        insert_order(data)
        flash("Bestelling geplaatst!", "success")
        return redirect(url_for('routes.home'))
    return render_template('order.html')

