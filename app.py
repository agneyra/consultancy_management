import os
from flask import Flask, render_template, redirect, url_for, Blueprint, jsonify
from flask_login import LoginManager, current_user
from sqlalchemy import text
from flask_sqlalchemy import SQLAlchemy

# Configuration and Database imports
from config import Config
from models.database import db # This is the ONLY db instance we use
from models.user import User
from models.student import Student, StudentSemesterFee
from models.transaction import Announcement

# Utils
from utils.email import send_reset_otp
from utils.filters import format_inr

app = Flask(__name__)

# 1. Load Configurations FIRST
app.config.from_object(Config)
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.jinja_env.filters['inr'] = format_inr

# 2. Initialize database ONCE
db.init_app(app)

# 3. Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login_selector'

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Create upload folder
os.makedirs(app.config.get('UPLOAD_FOLDER', 'uploads'), exist_ok=True)

# Register blueprints
from routes.auth import auth_bp
from routes.admin import admin_bp
from routes.agent import agent_bp
from routes.student import student_bp

app.register_blueprint(auth_bp)
app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(agent_bp, url_prefix='/agent')
app.register_blueprint(student_bp, url_prefix='/student')

# --- MIGRATION FUNCTIONS (KEEP AS IS) ---
def migrate_consultancies_email_unique_constraint():
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite'): return
    with db.engine.begin() as conn:
        table_sql = conn.execute(text("SELECT sql FROM sqlite_master WHERE type='table' AND name='consultancies'")).scalar()
        if not table_sql or 'email VARCHAR(120) UNIQUE' not in table_sql: return
        conn.execute(text('PRAGMA foreign_keys=OFF'))
        conn.execute(text("CREATE TABLE consultancies_new (id INTEGER NOT NULL PRIMARY KEY, name VARCHAR(200) NOT NULL UNIQUE, hostel_code VARCHAR(20) NOT NULL UNIQUE, contact_person VARCHAR(100) NOT NULL, email VARCHAR(120) NOT NULL, phone VARCHAR(20) NOT NULL, address TEXT, reset_otp VARCHAR(6), reset_otp_expiry DATETIME, created_at DATETIME, is_active BOOLEAN)"))
        conn.execute(text("INSERT INTO consultancies_new SELECT id, name, hostel_code, contact_person, email, phone, address, reset_otp, reset_otp_expiry, created_at, is_active FROM consultancies"))
        conn.execute(text("DROP TABLE consultancies"))
        conn.execute(text("ALTER TABLE consultancies_new RENAME TO consultancies"))
        conn.execute(text('PRAGMA foreign_keys=ON'))

def migrate_users_agent_2fa_columns():
    db_uri = app.config.get('SQLALCHEMY_DATABASE_URI', '')
    if not db_uri.startswith('sqlite'): return
    with db.engine.begin() as conn:
        columns = {row[1] for row in conn.execute(text("PRAGMA table_info(users)")).fetchall()}
        if 'agent_totp_secret' not in columns: conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_secret VARCHAR(64)"))
        if 'agent_totp_enabled' not in columns: conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_enabled BOOLEAN DEFAULT 0"))
        if 'agent_totp_enabled_at' not in columns: conn.execute(text("ALTER TABLE users ADD COLUMN agent_totp_enabled_at DATETIME"))

def migrate_students_semester_fees():
    created = False
    for student in Student.query.all():
        if student.semester_fees or not (student.total_fees or student.fees_paid): continue
        student.semester_fees.append(StudentSemesterFee(semester=1, total_fees=student.total_fees or 0.0, fees_paid=student.fees_paid or 0.0))
        created = True
    if created: db.session.commit()

# --- ROUTES ---
@app.route('/')
def home():
    if current_user.is_authenticated:
        if current_user.role == 'admin': return redirect(url_for('admin.dashboard'))
        elif current_user.role == 'agent': return redirect(url_for('agent.dashboard'))
        elif current_user.role == 'student': return redirect(url_for('student.dashboard'))
    return render_template('home.html')

@app.route('/api/active-announcements')
def get_active_announcements():
    try:
        announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
        return jsonify({'success': True, 'announcements': [{'id': a.id, 'message': a.message, 'created_at': a.created_at.strftime('%Y-%m-%d %H:%M:%S')} for a in announcements]})
    except Exception as e:
        return jsonify({'success': False, 'message': str(e), 'announcements': []}), 500

# 4. Create tables and context initialization
with app.app_context():
    db.create_all()
    migrate_consultancies_email_unique_constraint()
    migrate_users_agent_2fa_columns()
    migrate_students_semester_fees()
    
    from werkzeug.security import generate_password_hash
    admin = User.query.filter_by(role='admin').first()
    if not admin:
        admin = User(username='admin', password=generate_password_hash('admin123'), role='admin', email='admin@hostel.com')
        db.session.add(admin)
        db.session.commit()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
