from models.database import db
from datetime import datetime

class Consultancy(db.Model):
    __tablename__ = 'consultancies'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), unique=True, nullable=False)
    contact_person = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text)
    
    # Payment gateway credentials
    payment_gateway_id = db.Column(db.String(100))
    payment_gateway_key = db.Column(db.String(255))

    # 🔐 Password reset (OTP)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    
    # Relationships
    agents = db.relationship('User', backref='consultancy', lazy=True)
    students = db.relationship('Student', backref='consultancy', lazy=True)
    
    def __repr__(self):
        return f'<Consultancy {self.name}>'
