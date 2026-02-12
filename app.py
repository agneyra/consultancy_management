from flask import Flask, render_template, redirect, url_for
from flask_login import LoginManager, current_user
from config import Config
from models.database import db
from models.user import User
import os
from flask import Blueprint, jsonify
from models.transaction import Announcement
from utils.email import mail

app = Flask(__name__)
app.config.from_object(Config)

# Initialize database
db.init_app(app)
mail.init_app(app)

# Initialize login manager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'

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
    
    # Create default admin if not exists
    from werkzeug.security import generate_password_hash
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        admin = User(
            username='admin',
            password=generate_password_hash('admin123'),
            role='admin',
            email='admin@hostel.com'
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