import base64
import hashlib
import hmac
import os
import random
import struct
import time
from datetime import datetime, timedelta
from urllib.parse import quote, urljoin, urlparse

from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.security import check_password_hash, generate_password_hash

from models.database import db
from models.user import User
from utils.email import send_reset_otp


auth_bp = Blueprint('auth', __name__)

ADMIN_GAUTH_SECRET = os.environ.get('ADMIN_GAUTH_SECRET') or 'JBSWY3DPEHPK3PXP'

ROLE_LOGIN_CONFIG = {
    'admin': {
        'db_role': 'admin',
        'title': 'Admin Login',
        'subtitle': 'Only admin accounts can sign in from this page.'
    },
    'consultant': {
        'db_role': 'agent',
        'title': 'Consultant Login',
        'subtitle': 'Only consultant accounts can sign in from this page.'
    },
    'student': {
        'db_role': 'student',
        'title': 'Student Login',
        'subtitle': 'Only student accounts can sign in from this page.'
    }
}


def _dashboard_endpoint_for_role(role):
    if role == 'admin':
        return 'admin.dashboard'
    if role == 'agent':
        return 'agent.dashboard'
    if role == 'student':
        return 'student.dashboard'
    return None


def _is_safe_next_url(target):
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc


def _redirect_after_login(user, next_url=None):
    if next_url and _is_safe_next_url(next_url):
        return redirect(next_url)

    endpoint = _dashboard_endpoint_for_role(user.role)
    if endpoint:
        return redirect(url_for(endpoint))
    return redirect(url_for('home'))


def _normalize_totp_secret(secret):
    return ''.join((secret or '').strip().split()).upper()


def _generate_totp_code(secret, counter, digits=6):
    normalized_secret = _normalize_totp_secret(secret)
    padding = '=' * ((8 - (len(normalized_secret) % 8)) % 8)
    key = base64.b32decode(normalized_secret + padding, casefold=True)

    msg = struct.pack('>Q', counter)
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code_int = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(code_int % (10 ** digits)).zfill(digits)


def _verify_totp_code(code, secret, valid_window=1, interval=30, digits=6):
    otp = ''.join(ch for ch in str(code or '') if ch.isdigit())
    if len(otp) != digits:
        return False

    try:
        current_counter = int(time.time() // interval)
        for offset in range(-valid_window, valid_window + 1):
            counter = current_counter + offset
            if counter < 0:
                continue
            expected = _generate_totp_code(secret, counter, digits=digits)
            if hmac.compare_digest(expected, otp):
                return True
    except Exception:
        return False

    return False


def _admin_totp_secret():
    return _normalize_totp_secret(ADMIN_GAUTH_SECRET)


def _clear_pending_admin_2fa():
    session.pop('pending_admin_2fa_user_id', None)
    session.pop('pending_admin_2fa_password', None)
    session.pop('pending_admin_2fa_next', None)


def _clear_pending_agent_2fa():
    session.pop('pending_agent_2fa_user_id', None)
    session.pop('pending_agent_2fa_password', None)
    session.pop('pending_agent_2fa_next', None)
    session.pop('pending_agent_2fa_recovery_sent', None)


def _build_totp_uri(secret, account_name, issuer='Sandip Hostel Services'):
    normalized_secret = _normalize_totp_secret(secret)
    label = quote(f'{issuer}:{account_name}')
    encoded_issuer = quote(issuer)
    return (
        f'otpauth://totp/{label}'
        f'?secret={normalized_secret}'
        f'&issuer={encoded_issuer}'
        '&algorithm=SHA1&digits=6&period=30'
    )


def _build_qr_code_url(otpauth_uri):
    encoded_data = quote(otpauth_uri, safe='')
    return f'https://api.qrserver.com/v1/create-qr-code/?size=240x240&data={encoded_data}'


def _complete_pending_2fa_login(user, pending_prefix, clear_pending_func):
    login_user(user)
    plain_password = session.pop(f'{pending_prefix}_password', '')
    if plain_password:
        session['current_login_password'] = plain_password
    else:
        session.pop('current_login_password', None)

    next_url = session.get(f'{pending_prefix}_next')
    clear_pending_func()
    return _redirect_after_login(user, next_url=next_url)


def _pending_agent_user_or_none():
    pending_user_id = session.get('pending_agent_2fa_user_id')
    if not pending_user_id:
        return None
    user = User.query.get(pending_user_id)
    if not user or user.role != 'agent':
        _clear_pending_agent_2fa()
        return None
    return user


def _mask_email(email):
    value = (email or '').strip()
    if '@' not in value:
        return value

    local_part, domain = value.split('@', 1)
    if len(local_part) <= 2:
        masked_local = local_part[:1] + '*'
    else:
        masked_local = local_part[:2] + ('*' * (len(local_part) - 2))
    return f'{masked_local}@{domain}'


@auth_bp.route('/login')
def login():
    # Keep compatibility for existing links while routing users to role selector.
    return redirect(url_for('auth.login_selector', next=request.args.get('next')))


@auth_bp.route('/login/select')
def login_selector():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)
    return render_template('login_selector.html', next_url=request.args.get('next'))


@auth_bp.route('/login/<role_key>', methods=['GET', 'POST'])
def role_login(role_key):
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    role_key = (role_key or '').lower()
    role_config = ROLE_LOGIN_CONFIG.get(role_key)
    if not role_config:
        flash('Invalid login type selected.', 'error')
        return redirect(url_for('auth.login_selector'))

    next_url = request.args.get('next')

    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        user = User.query.filter_by(username=username).first()

        if user and check_password_hash(user.password, password):
            if user.role != role_config['db_role']:
                flash(f"This account is not allowed in {role_config['title']}.", 'error')
            else:
                if user.role == 'admin':
                    _clear_pending_admin_2fa()
                    _clear_pending_agent_2fa()
                    session['pending_admin_2fa_user_id'] = user.id
                    session['pending_admin_2fa_password'] = password
                    session['pending_admin_2fa_next'] = next_url
                    return redirect(url_for('auth.admin_2fa'))

                if user.role == 'agent':
                    user.ensure_agent_totp_secret()
                    db.session.commit()

                    _clear_pending_agent_2fa()
                    _clear_pending_admin_2fa()
                    session['pending_agent_2fa_user_id'] = user.id
                    session['pending_agent_2fa_password'] = password
                    session['pending_agent_2fa_next'] = next_url

                    if user.agent_totp_enabled:
                        return redirect(url_for('auth.agent_2fa'))
                    return redirect(url_for('auth.agent_2fa_setup'))

                login_user(user)
                # Keep current login password in session for admin-details reveal UI.
                session['current_login_password'] = password
                _clear_pending_admin_2fa()
                _clear_pending_agent_2fa()
                return _redirect_after_login(user, next_url=next_url)
        else:
            flash('Invalid username or password', 'error')

    return render_template(
        'login.html',
        form_action=url_for('auth.role_login', role_key=role_key, next=next_url),
        login_title=role_config['title'],
        login_subtitle=role_config['subtitle'],
        next_url=next_url,
        login_role=role_key
    )


@auth_bp.route('/login/admin-2fa', methods=['GET', 'POST'])
def admin_2fa():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    pending_user_id = session.get('pending_admin_2fa_user_id')
    if not pending_user_id:
        flash('Please login with admin username and password first.', 'error')
        return redirect(url_for('auth.role_login', role_key='admin'))

    user = User.query.get(pending_user_id)
    if not user or user.role != 'admin':
        _clear_pending_admin_2fa()
        flash('Admin verification session expired. Please login again.', 'error')
        return redirect(url_for('auth.role_login', role_key='admin'))

    secret = _admin_totp_secret()
    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        if _verify_totp_code(otp_code, secret, valid_window=1):
            return _complete_pending_2fa_login(
                user,
                pending_prefix='pending_admin_2fa',
                clear_pending_func=_clear_pending_admin_2fa
            )

        flash('Invalid Google Authenticator code. Please try again.', 'error')

    return render_template('admin_2fa.html')


@auth_bp.route('/login/consultant-2fa/setup', methods=['GET', 'POST'])
def agent_2fa_setup():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    user = _pending_agent_user_or_none()
    if not user:
        flash('Please login with consultant username and password first.', 'error')
        return redirect(url_for('auth.role_login', role_key='consultant'))

    user.ensure_agent_totp_secret()
    if db.session.is_modified(user, include_collections=False):
        db.session.commit()

    if user.agent_totp_enabled:
        return redirect(url_for('auth.agent_2fa'))

    secret = _normalize_totp_secret(user.agent_totp_secret)
    account_name = user.email or user.username
    otpauth_uri = _build_totp_uri(secret, account_name=account_name)
    qr_code_url = _build_qr_code_url(otpauth_uri)
    setup_key = ' '.join(secret[i:i + 4] for i in range(0, len(secret), 4))

    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        if _verify_totp_code(otp_code, secret, valid_window=1):
            user.agent_totp_enabled = True
            user.agent_totp_enabled_at = datetime.utcnow()
            db.session.commit()
            flash('Authenticator setup completed successfully.', 'success')
            return _complete_pending_2fa_login(
                user,
                pending_prefix='pending_agent_2fa',
                clear_pending_func=_clear_pending_agent_2fa
            )
        flash('Invalid authenticator code. Please try again.', 'error')

    return render_template(
        'agent_2fa_setup.html',
        qr_code_url=qr_code_url,
        setup_key=setup_key
    )


@auth_bp.route('/login/consultant-2fa', methods=['GET', 'POST'])
def agent_2fa():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    user = _pending_agent_user_or_none()
    if not user:
        flash('Please login with consultant username and password first.', 'error')
        return redirect(url_for('auth.role_login', role_key='consultant'))

    user.ensure_agent_totp_secret()
    if db.session.is_modified(user, include_collections=False):
        db.session.commit()

    if not user.agent_totp_enabled:
        return redirect(url_for('auth.agent_2fa_setup'))

    secret = _normalize_totp_secret(user.agent_totp_secret)
    if not secret:
        user.agent_totp_enabled = False
        user.ensure_agent_totp_secret()
        db.session.commit()
        return redirect(url_for('auth.agent_2fa_setup'))

    if request.method == 'POST':
        otp_code = request.form.get('otp_code', '').strip()
        if _verify_totp_code(otp_code, secret, valid_window=1):
            return _complete_pending_2fa_login(
                user,
                pending_prefix='pending_agent_2fa',
                clear_pending_func=_clear_pending_agent_2fa
            )

        flash('Invalid authenticator code. Please try again.', 'error')

    return render_template('agent_2fa.html')


@auth_bp.route('/login/consultant-2fa/recover', methods=['GET', 'POST'])
def agent_2fa_recover():
    if current_user.is_authenticated:
        return _redirect_after_login(current_user)

    user = _pending_agent_user_or_none()
    if not user:
        flash('Please login with consultant username and password first.', 'error')
        return redirect(url_for('auth.role_login', role_key='consultant'))

    if not user.email:
        flash('No recovery email configured for this consultant account.', 'error')
        return redirect(url_for('auth.role_login', role_key='consultant'))

    otp_sent = bool(session.get('pending_agent_2fa_recovery_sent'))

    if request.method == 'POST':
        action = (request.form.get('action') or '').strip().lower()

        if action == 'send_otp':
            otp = str(random.randint(100000, 999999))
            user.reset_otp = otp
            user.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)
            db.session.commit()

            try:
                if send_reset_otp(user.email, otp):
                    session['pending_agent_2fa_recovery_sent'] = True
                    flash('OTP sent to your registered email.', 'success')
                else:
                    flash('Failed to send OTP. Please try again.', 'error')
            except Exception as e:
                flash(f'Email error: {str(e)}', 'error')
            
            return redirect(url_for('auth.agent_2fa_recover'))

        if action == 'verify_otp':
            if not otp_sent:
                flash('Send OTP first.', 'error')
                return redirect(url_for('auth.agent_2fa_recover'))

            otp_code = (request.form.get('otp_code') or '').strip()
            if not user.reset_otp or user.reset_otp != otp_code:
                flash('Invalid OTP.', 'error')
                return redirect(url_for('auth.agent_2fa_recover'))

            if not user.reset_otp_expiry or user.reset_otp_expiry < datetime.utcnow():
                user.reset_otp = None
                user.reset_otp_expiry = None
                db.session.commit()
                session.pop('pending_agent_2fa_recovery_sent', None)
                flash('OTP expired. Please send OTP again.', 'error')
                return redirect(url_for('auth.agent_2fa_recover'))

            user.agent_totp_secret = User.generate_totp_secret()
            user.agent_totp_enabled = False
            user.agent_totp_enabled_at = None
            user.reset_otp = None
            user.reset_otp_expiry = None
            db.session.commit()
            session.pop('pending_agent_2fa_recovery_sent', None)

            flash('OTP verified. Configure your new authenticator setup.', 'success')
            return redirect(url_for('auth.agent_2fa_setup'))

        flash('Invalid action.', 'error')
        return redirect(url_for('auth.agent_2fa_recover'))

    return render_template(
        'agent_2fa_recover.html',
        masked_email=_mask_email(user.email),
        otp_sent=otp_sent
    )


@auth_bp.route('/logout')
@login_required
def logout():
    _clear_pending_admin_2fa()
    _clear_pending_agent_2fa()
    session.pop('current_login_password', None)
    logout_user()
    return redirect(url_for('home'))


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form.get('email')
        user = User.query.filter_by(email=email).first()

        if not user:
            flash('No account found with this email', 'error')
            return redirect(url_for('auth.forgot_password'))

        # Optional: block inactive hostels for consultants.
        if user.role == 'agent':
            consultancy = user.consultancy
            if consultancy and not consultancy.is_active:
                flash('Your hostel is deactivated. Contact admin.', 'error')
                return redirect(url_for('auth.forgot_password'))

        otp = str(random.randint(100000, 999999))
        user.reset_otp = otp
        user.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        db.session.commit()
        
        try:
            if send_reset_otp(email, otp):
                session['reset_user_id'] = user.id
                return redirect(url_for('auth.verify_otp'))
            else:
                flash('Failed to send OTP. Please check email configuration.', 'error')
        except Exception as e:
            flash(f'Email error: {str(e)}', 'error')

    return render_template('forgot_password.html')


@auth_bp.route('/forgot-password/admin', methods=['GET', 'POST'])
def admin_forgot_password():
    username = (request.values.get('username') or '').strip()
    if not username:
        flash('Enter admin username first, then click Forgot password.', 'error')
        return redirect(url_for('auth.role_login', role_key='admin'))

    user = User.query.filter_by(username=username, role='admin').first()
    if not user:
        flash('Admin account not found for provided username.', 'error')
        return redirect(url_for('auth.role_login', role_key='admin'))

    if not user.email:
        flash('No recovery email configured for this admin account.', 'error')
        return redirect(url_for('auth.role_login', role_key='admin'))

    if request.method == 'POST':
        otp = str(random.randint(100000, 999999))
        user.reset_otp = otp
        user.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=10)

        db.session.commit()
        
        try:
            if send_reset_otp(user.email, otp):
                session['reset_user_id'] = user.id
                flash('OTP sent to your registered email.', 'success')
                return redirect(url_for('auth.verify_otp'))
            else:
                flash('Failed to send OTP. Please check email configuration.', 'error')
        except Exception as e:
            flash(f'Email error: {str(e)}', 'error')

    return render_template(
        'admin_forgot_password.html',
        username=username,
        masked_email=_mask_email(user.email)
    )


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
        password = request.form.get('password', '')
        confirm_password = request.form.get('confirm_password', '')
        user_id = session.get('reset_user_id')

        user = User.query.get(user_id)
        if not user:
            flash('Reset session expired. Please try again.', 'error')
            return redirect(url_for('auth.forgot_password'))

        if len(password) < 6:
            flash('New password must be at least 6 characters', 'error')
            return redirect(url_for('auth.reset_password'))

        if password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('auth.reset_password'))

        user.password = generate_password_hash(password)

        user.reset_otp = None
        user.reset_otp_expiry = None

        db.session.commit()
        session.clear()

        flash('Password reset successful', 'success')
        return redirect(url_for('auth.login_selector'))

    return render_template('reset_password.html')
