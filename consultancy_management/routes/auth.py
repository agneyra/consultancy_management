from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from werkzeug.security import check_password_hash
from models.user import User
import random
from datetime import datetime, timedelta
from flask import session
from werkzeug.security import generate_password_hash
from models.database import db
from utils.email import send_reset_otp


auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        if user and check_password_hash(user.password, password):
            login_user(user)
            
            # Redirect based on role
            if user.role == 'admin':
                return redirect(url_for('admin.dashboard'))
            elif user.role == 'agent':
                return redirect(url_for('agent.dashboard'))
            elif user.role == 'student':
                return redirect(url_for('student.dashboard'))
        else:
            flash('Invalid username or password', 'error')
    
    return render_template('login.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')

        # ✅ Allow BOTH students and agents
        user = User.query.filter_by(email=email).first()

        if not user:
            flash('No account found with this email', 'error')
            return redirect(url_for('auth.forgot_password'))

        # OPTIONAL (but recommended): block inactive hostels for agents
        if user.role == 'agent':
            consultancy = user.consultancy
            if consultancy and not consultancy.is_active:
                flash('Your hostel is deactivated. Contact admin.', 'error')
                return redirect(url_for('auth.forgot_password'))

        if not user:
            flash('Consultant email not found', 'error')
            return redirect(url_for('auth.forgot_password'))

        otp = str(random.randint(100000, 999999))
        user.reset_otp = otp
        user.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        db.session.commit()
        send_reset_otp(email, otp)

        session['reset_user_id'] = user.id
        return redirect(url_for('auth.verify_otp'))

    return render_template('forgot_password.html')

@auth_bp.route('/verify-otp', methods=['GET', 'POST'])
def verify_otp():
    if request.method == 'POST':
        otp = request.form.get('otp')
        user_id = session.get('reset_user_id')

        user = User.query.get(user_id)

        if not user or user.reset_otp != otp:
            flash('Invalid OTP', 'error')
            return redirect(url_for('auth.verify_otp'))

        if user.reset_otp_expiry < datetime.utcnow():
            flash('OTP expired', 'error')
            return redirect(url_for('auth.forgot_password'))

        return redirect(url_for('auth.reset_password'))

    return render_template('verify_otp.html')

@auth_bp.route('/reset-password', methods=['GET', 'POST'])
def reset_password():
    if request.method == 'POST':
        password = request.form.get('password')
        user_id = session.get('reset_user_id')

        user = User.query.get(user_id)
        user.password = generate_password_hash(password)

        user.reset_otp = None
        user.reset_otp_expiry = None

        db.session.commit()
        session.clear()

        flash('Password reset successful', 'success')
        return redirect(url_for('auth.login'))

    return render_template('reset_password.html')
