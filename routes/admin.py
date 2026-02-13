from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash
from werkzeug.utils import secure_filename
from utils.decorators import admin_required
from utils.excel_handler import import_students_from_excel, export_students_to_excel, export_transactions_to_excel
from models.database import db
from models.user import User
from models.consultancy import Consultancy
from models.student import Student
from models.transaction import Transaction, Announcement
from sqlalchemy import func
import os
from io import BytesIO
import pandas as pd
import json
from datetime import datetime
from models.transaction import ChangeLog
from utils.hostels import HOSTELS


admin_bp = Blueprint('admin', __name__)

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
        pass  # Don't fail if logging fails

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # Get statistics
    total_consultancies = Consultancy.query.filter_by(is_active=True).count()
    total_students = Student.query.count()
    
    # Calculate fees
    total_fees = db.session.query(func.sum(Student.total_fees)).scalar() or 0
    fees_paid = db.session.query(func.sum(Student.fees_paid)).scalar() or 0
    fees_pending = total_fees - fees_paid
    
    # Get active announcements
    announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    
    stats = {
        'total_fees': total_fees,
        'fees_paid': fees_paid,
        'fees_pending': fees_pending,
        'total_consultancies': total_consultancies,
        'total_students': total_students
    }
    
    return render_template('admin/dashboard.html', stats=stats, announcements=announcements)


@admin_bp.route('/students/sample-template')
@login_required
@admin_required
def download_sample_template():
    df = pd.DataFrame(columns=[
        'PRN',
        'Name',
        'Branch',
        'Email',
        'Phone',
        'Hostel_Code',   # ✅ FIXED
        'Total_Fees',
        'Fees_Paid',
        'Pending_Fee'
    ])

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Sample')

    output.seek(0)

    return send_file(
        output,
        download_name='students_sample_template.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@admin_bp.route('/consultancies')
@login_required
@admin_required
def manage_consultancies():
    consultancies = Consultancy.query.all()

    # ✅ ONLY active hostels are considered "used"
    used_codes = {
        c.hostel_code
        for c in consultancies
        if c.is_active
    }

    available_hostels = {
        code: name
        for code, name in HOSTELS.items()
        if code not in used_codes
    }

    return render_template(
        'admin/manage_consultancies.html',
        consultancies=consultancies,
        available_hostels=available_hostels
    )


@admin_bp.route('/consultancies/add', methods=['POST'])
@login_required
@admin_required
def add_consultancy():
    name = request.form.get('name')
    contact_person = request.form.get('contact_person')
    email = request.form.get('email')
    phone = request.form.get('phone')
    address = request.form.get('address')
    payment_gateway_id = request.form.get('payment_gateway_id')
    payment_gateway_key = request.form.get('payment_gateway_key')
    
    # Create agent username and password
    agent_username = request.form.get('agent_username')
    agent_password = request.form.get('agent_password')
    
    try:
        # Create consultancy
        hostel_code = request.form.get('hostel_code')
        if hostel_code not in HOSTELS:
            flash('Invalid hostel selected!', 'error')
            return redirect(url_for('admin.manage_consultancies'))
        hostel_name = HOSTELS[hostel_code]

        # Safety check
        if not hostel_code:
            flash('Hostel code is required!', 'error')
            return redirect(url_for('admin.manage_consultancies'))

        # Ensure hostel code is unique
        existing = Consultancy.query.filter_by(hostel_code=hostel_code).first()

        if existing:
            if not existing.is_active:
                existing.is_active = True
                existing.contact_person = contact_person
                existing.email = email
                existing.phone = phone
                existing.address = address
                existing.payment_gateway_id = payment_gateway_id
                existing.payment_gateway_key = payment_gateway_key

                db.session.commit()
                flash('Hostel reactivated successfully!', 'success')
                return redirect(url_for('admin.manage_consultancies'))
            else:
                flash('Hostel code already exists!', 'error')
                return redirect(url_for('admin.manage_consultancies'))

        consultancy = Consultancy(
            name=hostel_name,  
            hostel_code=hostel_code,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address,
            payment_gateway_id=payment_gateway_id,
            payment_gateway_key=payment_gateway_key
        )
        db.session.add(consultancy)
        db.session.flush()
        
        # Create agent user
        agent = User(
            username=agent_username,
            password=generate_password_hash(agent_password),
            email=email,
            role='agent',
            consultancy_id=consultancy.id
        )
        db.session.add(agent)
        db.session.commit()
        
        flash('Hostel and agent added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding consultancy: {str(e)}', 'error')
    
    return redirect(url_for('admin.manage_consultancies'))

@admin_bp.route('/consultancies/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_consultancy(id):
    consultancy = Consultancy.query.get_or_404(id)
    
    try:
        # Get all students associated with this consultancy
        students = Student.query.filter_by(consultancy_id=consultancy.id).all()
        
        # Delete all student users first
        for student in students:
            user = student.user
            # Delete transactions
            Transaction.query.filter_by(student_id=student.id).delete()
            # Delete student
            db.session.delete(student)
            # Delete user
            if user:
                db.session.delete(user)
        
        # Delete agent users associated with this consultancy
        agents = User.query.filter_by(consultancy_id=consultancy.id, role='agent').all()
        for agent in agents:
            db.session.delete(agent)
        
        # Delete the consultancy itself
        db.session.delete(consultancy)
        db.session.commit()
        
        flash('Hostel and all associated data deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting hostel: {str(e)}', 'error')
    
    return redirect(url_for('admin.manage_consultancies'))


@admin_bp.route('/students/add')
@login_required
@admin_required
def add_student_page():
    consultancies = Consultancy.query.filter_by(is_active=True).all()
    return render_template(
        'admin/add_student.html',
        consultancies=consultancies
    )

@admin_bp.route('/students/upload', methods=['POST'])
@login_required
@admin_required
def upload_students():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join('static/uploads', filename)
        file.save(filepath)
        
        success, result = import_students_from_excel(filepath)
        
        # Clean up file
        os.remove(filepath)
        
        if success:
            return jsonify({
                'success': True,
                'message': f"Import complete! Success: {result['success']}, Failed: {result['failed']}",
                'details': result
            })
        else:
            return jsonify({'success': False, 'message': result}), 400
    
    return jsonify({'success': False, 'message': 'Invalid file'}), 400

@admin_bp.route('/students/filtered')
@login_required
@admin_required
def filtered_data():
    hostel_code = request.args.get('hostel_code', '')
    pending_filter = request.args.get('pending_filter', '')
    search = request.args.get('search', '')
    
    consultancies = Consultancy.query.all()

    query = Student.query.join(Consultancy)

    # 🔥 Filter by hostel code
    if hostel_code:
        query = query.filter(Consultancy.hostel_code == hostel_code)

    # Pending fee filter
    if pending_filter == 'has_pending':
        query = query.filter(Student.total_fees > Student.fees_paid)
    elif pending_filter == 'no_pending':
        query = query.filter(Student.total_fees <= Student.fees_paid)

    # Search filter
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            db.or_(
                Student.prn.ilike(search_term),
                Student.full_name.ilike(search_term),
                Student.email.ilike(search_term),
                Student.branch.ilike(search_term)
            )
        )

    students = query.all()

    return render_template(
        'admin/filtered_data.html',
        students=students,
        consultancies=consultancies,
        selected_hostel_code=hostel_code
    )

@admin_bp.route('/students/export')
@login_required
@admin_required
def export_students():
    hostel_code = request.args.get('hostel_code', '')

    query = Student.query.join(Consultancy)

    if hostel_code:
        query = query.filter(Consultancy.hostel_code == hostel_code)

    students = query.all()

    df = export_students_to_excel(students)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Students')
    output.seek(0)

    return send_file(
        output,
        download_name='students_data.xlsx',
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

@admin_bp.route('/announcements')
@login_required
@admin_required
def announcements():
    announcements = Announcement.query.order_by(Announcement.created_at.desc()).all()
    return render_template('admin/announcements.html', announcements=announcements)

@admin_bp.route('/announcements/add', methods=['POST'])
@login_required
@admin_required
def add_announcement():
    message = request.form.get('message')
    
    announcement = Announcement(
        message=message,
        created_by=current_user.id,
        is_active=True
    )
    db.session.add(announcement)
    db.session.commit()
    
    flash('Announcement added successfully!', 'success')
    return redirect(url_for('admin.announcements'))


@admin_bp.route('/announcements/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_announcement(id):
    announcement = Announcement.query.get_or_404(id)
    try:
        # Permanently delete instead of just deactivating
        db.session.delete(announcement)
        db.session.commit()
        flash('Announcement deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting announcement: {str(e)}', 'error')
    
    return redirect(url_for('admin.announcements'))

@admin_bp.route('/payment-history')
@login_required
@admin_required
def payment_history():
    search = request.args.get('search', '')
    
    query = Transaction.query.join(Student)
    
    if search:
        query = query.filter(
            db.or_(
                Transaction.transaction_id.contains(search),
                Student.full_name.contains(search),
                Student.prn.contains(search)
            )
        )
    
    transactions = query.order_by(Transaction.payment_date.desc()).all()
    
    return render_template('admin/payment_history.html', 
                         transactions=transactions,
                         search=search)

@admin_bp.route('/payment-history/export')
@login_required
@admin_required
def export_payment_history():
    transactions = Transaction.query.order_by(Transaction.payment_date.desc()).all()
    df = export_transactions_to_excel(transactions)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Transactions')
    output.seek(0)
    
    return send_file(output,
                    download_name='payment_history.xlsx',
                    as_attachment=True,
                    mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


@admin_bp.route('/students/update/<int:id>', methods=['POST'])
@login_required
@admin_required
def update_student(id):
    student = Student.query.get_or_404(id)
    
    try:
        # Get data from request
        data = request.get_json()
        
        # Log the change
        log_change(
            user_id=current_user.id,
            user_role='admin',
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
            from werkzeug.security import generate_password_hash
            student.user.password = generate_password_hash(data['phone'])
        if 'total_fees' in data:
            student.total_fees = float(data['total_fees'])
        if 'consultancy_id' in data:
            student.consultancy_id = int(data['consultancy_id'])
            student.user.consultancy_id = int(data['consultancy_id'])
        
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
                'consultancy_id': student.consultancy_id,
                'consultancy_name': student.consultancy.name,
                'hostel_code': student.consultancy.hostel_code,
                'hostel_name': student.consultancy.name,
                'total_fees': student.total_fees,
                'fees_paid': student.fees_paid,
                'fees_pending': student.fees_pending
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    
@admin_bp.route('/students/delete/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_student(id):
    student = Student.query.get_or_404(id)
    user = student.user
    
    try:
        # Log the deletion
        log_change(
            user_id=current_user.id,
            user_role='admin',
            action='delete',
            table='students',
            record_id=student.id,
            changes={'student_name': student.full_name, 'prn': student.prn}
        )
        
        # Delete transactions first
        Transaction.query.filter_by(student_id=student.id).delete()
        
        # Delete student
        db.session.delete(student)
        
        # Delete user
        db.session.delete(user)
        
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'Student deleted successfully'})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400
    
@admin_bp.route('/students/add-single', methods=['POST'])
@login_required
@admin_required
def add_single_student():
    try:
        prn = request.form.get('prn')
        full_name = request.form.get('full_name')
        branch = request.form.get('branch')
        email = request.form.get('email')
        phone = request.form.get('phone')
        consultancy_id = request.form.get('consultancy_id')
        total_fees = float(request.form.get('total_fees'))
        fees_paid = float(request.form.get('fees_paid', 0))
        
        # Check if student already exists
        existing_student = Student.query.filter_by(prn=prn).first()
        if existing_student:
            flash('Student with this PRN already exists!', 'error')
            return redirect(url_for('admin.add_student_page'))
        # Check if consultancy exists
        consultancy = Consultancy.query.get(consultancy_id)

        if not consultancy:
            flash('Selected hostel not found!', 'error')
            return redirect(url_for('admin.add_student_page'))

        if not consultancy.is_active:
            flash('Selected hostel is deactivated. Activate it before adding students.', 'error')
            return redirect(url_for('admin.add_student_page'))

        
        # Create user (username = PRN, password = phone number)
        user = User(
            username=prn,
            password=generate_password_hash(phone),
            email=email,
            role='student',
            consultancy_id=consultancy_id
        )
        db.session.add(user)
        db.session.flush()
        
        # Create student
        student = Student(
            user_id=user.id,
            consultancy_id=consultancy_id,
            prn=prn,
            full_name=full_name,
            branch=branch,
            email=email,
            phone=phone,
            total_fees=total_fees,
            fees_paid=fees_paid
        )
        db.session.add(student)
        db.session.commit()
        
        flash(f'Student {full_name} added successfully! Login: Username={prn}, Password={phone}', 'success')
        return redirect(url_for('admin.add_student_page'))
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding student: {str(e)}', 'error')
        return redirect(url_for('admin.add_student_page'))

# Add these routes to routes/admin.py


@admin_bp.route('/consultancies/<int:id>')
@login_required
@admin_required
def get_consultancy(id):
    c = Consultancy.query.get_or_404(id)
    return jsonify({
        'id': c.id,
        'name': c.name,
        'contact_person': c.contact_person,
        'email': c.email,
        'phone': c.phone
    })

# Replace the update_consultancy route in routes/admin.py with this complete version

@admin_bp.route('/consultancies/update/<int:id>', methods=['POST'])
@login_required
@admin_required
def update_consultancy(id):
    consultancy = Consultancy.query.get_or_404(id)
    
    try:
        # Get data from request
        data = request.get_json()
        
        # Update consultancy fields
        if 'name' in data:
            consultancy.name = data['name']
        if 'contact_person' in data:
            consultancy.contact_person = data['contact_person']
        if 'email' in data:
            consultancy.email = data['email']
        if 'phone' in data:
            consultancy.phone = data['phone']
        if 'address' in data:
            consultancy.address = data.get('address', '')
        if 'payment_gateway_id' in data:
            consultancy.payment_gateway_id = data.get('payment_gateway_id', '')
        if 'payment_gateway_key' in data:
            consultancy.payment_gateway_key = data.get('payment_gateway_key', '')
        
        # Update agent information
        agent_id = data.get('agent_id')
        if agent_id:
            agent = User.query.get(agent_id)
            if agent:
                # Update agent username
                if 'agent_username' in data:
                    agent.username = data['agent_username']
                
                # Update agent email (sync with consultancy email)
                if 'email' in data:
                    agent.email = data['email']
                
                # Update agent password only if provided
                if 'agent_password' in data and data['agent_password']:
                    agent.password = generate_password_hash(data['agent_password'])
        agent_id = data.get('agent_id')
        agent_username = data.get('agent_username')
        agent_password = data.get('agent_password')

        if agent_id:
            # ✅ UPDATE EXISTING AGENT
            agent = User.query.get(agent_id)
            if agent:
                agent.username = agent_username
                agent.email = consultancy.email
                if agent_password:
                    agent.password = generate_password_hash(agent_password)

        else:
            # ✅ CREATE AGENT IF MISSING (THIS IS WHY B6 WAS FAILING)
            if agent_username:
                new_agent = User(
                    username=agent_username,
                    password=generate_password_hash(agent_password or "123456"),
                    email=consultancy.email,
                    role='agent',
                    consultancy_id=consultancy.id
                )
                db.session.add(new_agent)

        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Hostel and agent updated successfully',
            'consultancy': {
                'id': consultancy.id,
                'name': consultancy.name,
                'contact_person': consultancy.contact_person,
                'email': consultancy.email,
                'phone': consultancy.phone,
                'address': consultancy.address,
                'payment_gateway_id': consultancy.payment_gateway_id
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@admin_bp.route('/consultancies/deactivate/<int:id>', methods=['POST'])
@login_required
@admin_required
def deactivate_consultancy(id):
    """Deactivate hostel without deleting students"""
    consultancy = Consultancy.query.get_or_404(id)
    
    try:
        # Just deactivate - students remain in system
        consultancy.is_active = False
        db.session.commit()
        
        flash(f'Hostel "{consultancy.name}" has been deactivated. Students remain in the system.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deactivating hostel: {str(e)}', 'error')
    
    return redirect(url_for('admin.manage_consultancies'))


# ALTERNATIVE: If you want to completely delete hostel but keep students
@admin_bp.route('/consultancies/delete-keep-students/<int:id>', methods=['POST'])
@login_required
@admin_required
def delete_consultancy_keep_students(id):
    """
    Delete hostel but preserve all students.
    Students will have consultancy_id set to NULL or a default hostel.
    """
    consultancy = Consultancy.query.get_or_404(id)
    
    try:
        # Option 1: Set students' consultancy_id to NULL
        students = Student.query.filter_by(consultancy_id=consultancy.id).all()
        for student in students:
            student.consultancy_id = None  # Or set to a default hostel ID
            # student.consultancy_id = 1  # Example: Move to "Unassigned Hostel"
        
        # Option 2: Or create an "Unassigned" hostel first
        # unassigned = Consultancy.query.filter_by(name='Unassigned').first()
        # if not unassigned:
        #     unassigned = Consultancy(name='Unassigned', ...)
        #     db.session.add(unassigned)
        #     db.session.flush()
        # 
        # for student in students:
        #     student.consultancy_id = unassigned.id
        #     student.user.consultancy_id = unassigned.id
        
        # Delete agent users
        agents = User.query.filter_by(consultancy_id=consultancy.id, role='agent').all()
        for agent in agents:
            db.session.delete(agent)
        
        # Delete the consultancy
        db.session.delete(consultancy)
        db.session.commit()
        
        flash(f'Hostel deleted. {len(students)} students preserved and need reassignment.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting hostel: {str(e)}', 'error')
    
    return redirect(url_for('admin.manage_consultancies'))


# Replace the old delete_consultancy route with deactivate_consultancy
# Or rename it to make it clear what it does