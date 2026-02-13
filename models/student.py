from models.database import db
from datetime import datetime

class Student(db.Model):
    __tablename__ = 'students'
    
    id = db.Column(db.Integer, primary_key=True)

    # 🔗 Auth & Hostel linkage
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), unique=True, nullable=False)
    consultancy_id = db.Column(db.Integer, db.ForeignKey('consultancies.id'), nullable=False)

    prn = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(200), nullable=False)
    branch = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(20))
    
    total_fees = db.Column(db.Float, default=0.0)
    fees_paid = db.Column(db.Float, default=0.0)
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relationships
    transactions = db.relationship('Transaction', backref='student', lazy=True)

    # 🔎 Derived hostel data (NO duplication)
    @property
    def hostel_code(self):
        return self.consultancy.hostel_code

    @property
    def hostel_name(self):
        return self.consultancy.name
    
    @property
    def fees_pending(self):
        return self.total_fees - self.fees_paid
    
    def __repr__(self):
        return f'<Student {self.prn} - {self.full_name}>'
