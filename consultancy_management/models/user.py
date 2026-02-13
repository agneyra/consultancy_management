from flask_login import UserMixin
from models.database import db
from datetime import datetime

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, agent, student

    # 🔐 Password reset (OTP)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    consultancy_id = db.Column(db.Integer, db.ForeignKey('consultancies.id'), nullable=True)
    student_data = db.relationship('Student', backref='user', uselist=False)
    
    def __repr__(self):
        return f'<User {self.username}>'
