from datetime import datetime
from models.database import db


class Student(db.Model):
    __tablename__ = 'students'

    id = db.Column(db.Integer, primary_key=True)

    # Auth and hostel linkage
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

    transactions = db.relationship('Transaction', backref='student', lazy=True)
    semester_fees = db.relationship(
        'StudentSemesterFee',
        backref='student',
        lazy=True,
        cascade='all, delete-orphan',
        order_by='StudentSemesterFee.semester'
    )

    @property
    def hostel_code(self):
        return self.consultancy.hostel_code

    @property
    def hostel_name(self):
        return self.consultancy.name

    @property
    def fees_pending(self):
        return self.total_fees - self.fees_paid

    def recalculate_fee_totals(self):
        if self.semester_fees:
            self.total_fees = sum(item.total_fees for item in self.semester_fees)
            self.fees_paid = sum(item.fees_paid for item in self.semester_fees)
        else:
            self.total_fees = 0.0
            self.fees_paid = 0.0

    def __repr__(self):
        return f'<Student {self.prn} - {self.full_name}>'


class StudentSemesterFee(db.Model):
    __tablename__ = 'student_semester_fees'
    __table_args__ = (
        db.UniqueConstraint('student_id', 'semester', name='uq_student_semester_fee'),
    )

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('students.id'), nullable=False, index=True)
    semester = db.Column(db.Integer, nullable=False)
    total_fees = db.Column(db.Float, nullable=False, default=0.0)
    fees_paid = db.Column(db.Float, nullable=False, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def fees_pending(self):
        return self.total_fees - self.fees_paid

    def __repr__(self):
        return f'<StudentSemesterFee student_id={self.student_id} semester={self.semester}>'
