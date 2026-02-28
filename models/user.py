import base64
import os
from flask_login import UserMixin
from models.database import db
from datetime import datetime
from sqlalchemy import UniqueConstraint

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)

    username = db.Column(db.String(80), unique=True, nullable=False)

    email = db.Column(db.String(120), unique=True, nullable=False)   # ✅ global unique
    phone = db.Column(db.String(15), unique=True, nullable=True)     # ✅ ADD THIS

    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False)  # admin, agent, student

    # 🔐 Password reset (OTP)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)
    agent_totp_secret = db.Column(db.String(64), nullable=True)
    agent_totp_enabled = db.Column(db.Boolean, nullable=False, default=False)
    agent_totp_enabled_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    consultancy_id = db.Column(db.Integer, db.ForeignKey('consultancies.id'), nullable=True)
    student_data = db.relationship('Student', backref='user', uselist=False)
    assigned_consultancies = db.relationship(
        'AgentConsultancy',
        backref='agent',
        lazy=True,
        cascade='all, delete-orphan'
    )

    def get_accessible_consultancy_ids(self):
        ids = set()
        if self.consultancy_id:
            ids.add(self.consultancy_id)
        if self.role == 'agent':
            ids.update(link.consultancy_id for link in self.assigned_consultancies)
        return list(ids)

    @staticmethod
    def generate_totp_secret():
        return base64.b32encode(os.urandom(20)).decode('utf-8').rstrip('=')

    def ensure_agent_totp_secret(self):
        if self.role == 'agent' and not self.agent_totp_secret:
            self.agent_totp_secret = self.generate_totp_secret()
        return self.agent_totp_secret
    
    def __repr__(self):
        return f'<User {self.username}>'


class AgentConsultancy(db.Model):
    __tablename__ = 'agent_consultancies'
    __table_args__ = (
        UniqueConstraint('agent_id', 'consultancy_id', name='uq_agent_consultancy'),
    )

    id = db.Column(db.Integer, primary_key=True)
    agent_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    consultancy_id = db.Column(db.Integer, db.ForeignKey('consultancies.id'), nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
