from flask import Blueprint, render_template, request, send_file
from flask_login import login_required, current_user
from utils.decorators import agent_required
from utils.excel_handler import export_students_to_excel, export_transactions_to_excel
from models.database import db
from models.student import Student
from models.transaction import Transaction, Announcement
from sqlalchemy import func
from io import BytesIO
import pandas as pd
import json
from datetime import datetime
from models.transaction import ChangeLog

agent_bp = Blueprint('agent', __name__)

def log_change(user_id, user_role, action, table, record_id, changes):
    """Log changes to database"""
    try:
        log_entry = ChangeLog(
            user_id=user_id,
            user_role=user_role,
            action=action,
            table_name=table,
            record_id=record_id,
            changes=json.dumps(changes),
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)
        db.session.commit()
    except Exception as e:
        print(f"Logging error: {str(e)}")
        pass  

@agent_bp.route('/dashboard')
@login_required
@agent_required
def dashboard():
    # Get consultancy statistics
    consultancy_id = current_user.consultancy_id
    
    students = Student.query.filter_by(consultancy_id=consultancy_id).all()
    total_students = len(students)
    
    total_fees = sum(s.total_fees for s in students)
    fees_paid = sum(s.fees_paid for s in students)
    fees_pending = total_fees - fees_paid
    
    # Get active announcements
    announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    
    stats = {
        'total_fees': total_fees,
        'fees_paid': fees_paid,
        'fees_pending': fees_pending,
        'total_students': total_students
    }
    
    return render_template('agent/dashboard.html', stats=stats, announcements=announcements)

@agent_bp.route('/students')
@login_required
@agent_required
def students_data():
    consultancy_id = current_user.consultancy_id
    pending_filter = request.args.get('pending_filter', '')
    search = request.args.get('search', '')
    
    # Base query
    query = Student.query.filter_by(consultancy_id=consultancy_id)
    
    # Apply pending fee filter
    if pending_filter == 'has_pending':
        query = query.filter(Student.total_fees > Student.fees_paid)
    elif pending_filter == 'no_pending':
        query = query.filter(Student.total_fees <= Student.fees_paid)
    
    # Apply search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Student.prn.like(search_term),
                Student.full_name.like(search_term),
                Student.email.like(search_term),
                Student.branch.like(search_term)
            )
        )
    
    students = query.all()
    
    return render_template('agent/students_data.html', students=students)

@agent_bp.route('/students/export')
@login_required
@agent_required
def export_students():
    consultancy_id = current_user.consultancy_id
    students = Student.query.filter_by(consultancy_id=consultancy_id).all()
    
    df = export_students_to_excel(students)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')
    output.seek(0)
    
    return send_file(output,
                    download_name='students_data.xlsx',
                    as_attachment=True,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@agent_bp.route('/payment-history')
@login_required
@agent_required
def payment_history():
    consultancy_id = current_user.consultancy_id
    search = request.args.get('search', '')
    
    query = Transaction.query.filter_by(consultancy_id=consultancy_id).join(Student)
    
    if search:
        query = query.filter(
            db.or_(
                Transaction.transaction_id.contains(search),
                Student.full_name.contains(search),
                Student.prn.contains(search)
            )
        )
    
    transactions = query.order_by(Transaction.payment_date.desc()).all()
    
    return render_template('agent/payment_history.html',
                         transactions=transactions,
                         search=search)

@agent_bp.route('/payment-history/export')
@login_required
@agent_required
def export_payment_history():
    consultancy_id = current_user.consultancy_id
    transactions = Transaction.query.filter_by(consultancy_id=consultancy_id).all()
    
    df = export_transactions_to_excel(transactions)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
    output.seek(0)
    
    return send_file(output,
                    download_name='payment_history.xlsx',
                    as_attachment=True,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@agent_bp.route('/students/update/<int:id>', methods=['POST'])
@login_required
@agent_required
def update_student(id):
    from flask import jsonify
    from werkzeug.security import generate_password_hash
    
    consultancy_id = current_user.consultancy_id
    student = Student.query.filter_by(id=id, consultancy_id=consultancy_id).first_or_404()
    
    try:
        # Get data from request
        data = request.get_json()
        
        # Log the change
        log_change(
            user_id=current_user.id,
            user_role='agent',
            action='update',
            table='students',
            record_id=student.id,
            changes=data
        )
        
        # Update student fields
        if 'prn' in data:
            student.prn = data['prn']
            student.user.username = data['prn']
        if 'full_name' in data:
            student.full_name = data['full_name']
        if 'branch' in data:
            student.branch = data['branch']
        if 'email' in data:
            student.email = data['email']
            student.user.email = data['email']
        if 'phone' in data:
            student.phone = data['phone']
            # Update password to new phone number
            student.user.password = generate_password_hash(data['phone'])
        if 'total_fees' in data:
            student.total_fees = float(data['total_fees'])
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Student updated successfully',
            'student': {
                'id': student.id,
                'prn': student.prn,
                'full_name': student.full_name,
                'branch': student.branch,
                'email': student.email,
                'phone': student.phone,
                'total_fees': student.total_fees,
                'fees_paid': student.fees_paid,
                'fees_pending': student.fees_pending
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

@agent_bp.route('/students/delete/<int:id>', methods=['POST'])
@login_required
@agent_required
def delete_student(id):
    from flask import jsonify
    
    consultancy_id = current_user.consultancy_id
    student = Student.query.filter_by(id=id, consultancy_id=consultancy_id).first_or_404()
    user = student.user
    
    try:
        # Log the deletion
        log_change(
            user_id=current_user.id,
            user_role='agent',
            action='delete',
            table='students',
            record_id=student.id,
            changes={'student_name': student.full_name, 'prn': student.prn}
        )
        
        db.session.delete(student)
        db.session.delete(user)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Student deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

def log_change(user_id, user_role, action, table, record_id, changes):
    """Log changes to database"""
    from models.transaction import ChangeLog
    from datetime import datetime
    import json
    
    try:
        log_entry = ChangeLog(
            user_id=user_id,
            user_role=user_role,
            action=action,
            table_name=table,
            record_id=record_id,
            changes=json.dumps(changes),
            timestamp=datetime.utcnow()
        )
        db.session.add(log_entry)
        db.session.commit()
    except:
        pass  # Don't fail if logging fails