from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from config import Config
from models.database import db
from models.user import User
from models.student import Student, StudentSemesterFee
import os
from flask import Blueprint, jsonify
from models.transaction import Announcement
from utils.email import mail
from sqlalchemy import text


app = Flask(__name__)
from utils.filters import format_inr

app.jinja_env.filters['inr'] = format_inr

app.config.from_object(Config)

# Initialize database
db.init_app(app)
mail.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login_selector'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create upload folder
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Register blueprints
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.agent import agent_bp
from routes.student import student_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(agent_bp, url_prefix='/agent')
app.register_blueprint(student_bp, url_prefix='/student')


def migrate_consultancies_email_unique_constraint():
    """
    SQLite migration:
    Remove UNIQUE constraint from consultancies.email so one consultant email
    can be reused across multiple hostels.
    """
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite'):
        return

    with db.engine.begin() as conn:
        table_sql = conn.execute(
            text("SELECT sql FROM sqlite_master WHERE type='table' AND name='consultancies'")
        ).scalar()
        if not table_sql:
            return

        email_unique_present = (
            'email VARCHAR(120) UNIQUE' in table_sql or
            'UNIQUE (email)' in table_sql or
            'UNIQUE(email)' in table_sql
        )
        if not email_unique_present:
            return

        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text("""
            CREATE TABLE consultancies_new (
                id INTEGER NOT NULL PRIMARY KEY,
                name VARCHAR(200) NOT NULL UNIQUE,
                hostel_code VARCHAR(20) NOT NULL UNIQUE,
                contact_person VARCHAR(100) NOT NULL,
                email VARCHAR(120) NOT NULL,
                phone VARCHAR(20) NOT NULL,
                address TEXT,
                reset_otp VARCHAR(6),
                reset_otp_expiry DATETIME,
                created_at DATETIME,
                is_active BOOLEAN
            )
        """))
        conn.execute(text("""
            INSERT INTO consultancies_new (
                id, name, hostel_code, contact_person, email, phone, address,
                reset_otp, reset_otp_expiry,
                created_at, is_active
            )
            SELECT
                id, name, hostel_code, contact_person, email, phone, address,
                reset_otp, reset_otp_expiry,
                created_at, is_active
            FROM consultancies
        """))
        conn.execute(text("DROP TABLE consultancies"))
        conn.execute(text("ALTER TABLE consultancies_new RENAME TO consultancies"))
        conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_consultancies_hostel_code ON consultancies (hostel_code)"))
        conn.execute(text('PRAGMA foreign_keys=ON'))


def migrate_users_agent_2fa_columns():
    """
    SQLite migration:
    Add per-agent authenticator columns if they are missing.
    """
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite'):
        return

    with db.engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()
        }

        if 'agent_totp_secret' not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_secret VARCHAR(64)"))
        if 'agent_totp_enabled' not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_enabled BOOLEAN DEFAULT 0"))
        if 'agent_totp_enabled_at' not in columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_enabled_at DATETIME"))

        conn.execute(text("UPDATE users SET agent_totp_enabled = 0 WHERE agent_totp_enabled IS NULL"))


def migrate_students_semester_fees():
    """
    Backfill semester-wise fee rows for legacy students.
    Existing students without semester rows are assigned a default Semester 1 row
    based on their current total/paid values.
    """
    created = False
    for student in Student.query.all():
        if student.semester_fees:
            continue
        if not (student.total_fees or student.fees_paid):
            continue
        student.semester_fees.append(StudentSemesterFee(
            semester=1,
            total_fees=student.total_fees or 0.0,
            fees_paid=student.fees_paid or 0.0
        ))
        created = True

    if created:
        db.session.commit()

# Home route
@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role == 'admin':
            return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'agent':
            return redirect(url_for('agent.dashboard'))
        elif current_user.role == 'student':
            return redirect(url_for('student.dashboard'))
    return render_template('home.html')

# Create tables and default admin
with app.app_context():
    db.create_all()
    migrate_consultancies_email_unique_constraint()
    migrate_users_agent_2fa_columns()
    db.create_all()
    migrate_students_semester_fees()
    
    # Create default admin only when there is no admin role in the database.
    from werkzeug.security import generate_password_hash
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        default_username = 'admin'
        if User.query.filter_by(username=default_username).first():
            suffix = 1
            while User.query.filter_by(username=f'admin{suffix}').first():
                suffix += 1
            default_username = f'admin{suffix}'

        default_email = 'admin@hostel.com'
        if User.query.filter_by(email=default_email).first():
            suffix = 1
            while User.query.filter_by(email=f'admin{suffix}@hostel.local').first():
                suffix += 1
            default_email = f'admin{suffix}@hostel.local'

        admin = User(
            username=default_username,
            password=generate_password_hash('admin123'),
            role='admin',
            email=default_email
        )
        db.session.add(admin)
        db.session.commit()

@app.route('/api/active-announcements')
def get_active_announcements():
    try:
        announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
        return jsonify({
            'success': True,
            'announcements': [
                {
                    'id': a.id,
                    'message': a.message,
                    'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S')
                }
                for a in announcements
            ]
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': str(e),
            'announcements': []
        }), 500


if __name__ == '__main__':
    app.run(debug=True)

@app.route('/test-email/<email>')
def test_email(email):
    from utils.email import send_reset_otp
    try:
        result = send_reset_otp(email, '123456')
        return jsonify({'success': result, 'message': 'Check logs'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500
