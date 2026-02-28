from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file, session
from flask_login import login_required, current_user
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename
from utils.decorators import admin_required
from utils.excel_handler import import_students_from_excel, export_students_to_excel
from models.database import db
from models.user import User, AgentConsultancy
from models.consultancy import Consultancy
from models.student import Student, StudentSemesterFee
from models.transaction import Transaction, Announcement
from sqlalchemy import func
import os
from io import BytesIO
import pandas as pd
import json
import re
from datetime import datetime
from models.transaction import ChangeLog
from utils.hostels import HOSTELS


admin_bp = Blueprint('admin', __name__)


def normalize_email(value):
    return ''.join((value or '').strip().lower().split())


def normalize_phone(value):
    return ''.join(ch for ch in str(value or '') if ch.isdigit())


def is_valid_email(value):
    pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'
    return bool(re.match(pattern, value or ''))


def validate_student_contact_uniqueness(email, phone, exclude_student_id=None):
    """Return an error message if student email/phone conflicts with existing records."""
    normalized_email = normalize_email(email)
    normalized_phone = normalize_phone(phone)

    if not normalized_email:
        return 'Email is required!'
    if not is_valid_email(normalized_email):
        return 'Enter a valid email address (example: name@example.com)!'
    if not normalized_phone:
        return 'Phone number is required!'

    # Block if email/phone already used by any hostel (consultancy).
    for consultancy in Consultancy.query.all():
        if normalize_email(consultancy.email) == normalized_email:
            return f'Email already used by hostel "{consultancy.name}"!'
        if normalize_phone(consultancy.phone) == normalized_phone:
            return f'Phone number already used by hostel "{consultancy.name}"!'

    # Block if email/phone already used by another student.
    students_query = Student.query
    if exclude_student_id:
        students_query = students_query.filter(Student.id != exclude_student_id)
    for student in students_query.all():
        if normalize_email(student.email) == normalized_email:
            return 'Email already used by another student!'
        if normalize_phone(student.phone) == normalized_phone:
            return 'Phone number already used by another student!'

    # Guard against existing user uniqueness conflicts as well.
    excluded_user_id = None
    if exclude_student_id:
        excluded_student = Student.query.get(exclude_student_id)
        if excluded_student:
            excluded_user_id = excluded_student.user_id

    for user in User.query.all():
        if excluded_user_id and user.id == excluded_user_id:
            continue
        if normalize_email(user.email) == normalized_email:
            return 'Email already used by another account!'
        if normalize_phone(user.phone) == normalized_phone:
            return 'Phone number already used by another account!'

    return None


def parse_semester_value(raw_value):
    try:
        semester = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return None
    if 1 <= semester <= 8:
        return semester
    return None


def semester_fee_payload(semester_fee):
    return {
        'id': semester_fee.id,
        'student_id': semester_fee.student_id,
        'semester': semester_fee.semester,
        'total_fees': semester_fee.total_fees,
        'fees_paid': semester_fee.fees_paid,
        'fees_pending': semester_fee.fees_pending
    }


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
    consultancies = (
        Consultancy.query
        .filter_by(is_active=True)
        .order_by(Consultancy.hostel_code.asc())
        .all()
    )
    consultancy_ids = [c.id for c in consultancies]

    selected_hostel_id = request.args.get('hostel_id', type=int)
    if selected_hostel_id not in consultancy_ids:
        selected_hostel_id = None

    selected_semester = request.args.get('semester', type=int)
    if selected_semester not in range(1, 9):
        selected_semester = None

    # Get statistics
    total_consultancies = len(consultancies)
    student_query = Student.query
    if selected_hostel_id:
        student_query = student_query.filter(Student.consultancy_id == selected_hostel_id)
        total_consultancies = 1
    total_students = student_query.count()

    # Calculate fees
    if selected_semester:
        semester_query = (
            StudentSemesterFee.query
            .join(Student, Student.id == StudentSemesterFee.student_id)
            .filter(StudentSemesterFee.semester == selected_semester)
        )
        if selected_hostel_id:
            semester_query = semester_query.filter(Student.consultancy_id == selected_hostel_id)
        semester_rows = semester_query.all()
        total_fees = sum(row.total_fees for row in semester_rows)
        fees_paid = sum(row.fees_paid for row in semester_rows)
        fees_pending = total_fees - fees_paid
        total_students = len({row.student_id for row in semester_rows})
    else:
        fee_totals_query = db.session.query(
            func.sum(Student.total_fees),
            func.sum(Student.fees_paid)
        )
        if selected_hostel_id:
            fee_totals_query = fee_totals_query.filter(Student.consultancy_id == selected_hostel_id)
        fee_totals = fee_totals_query.one()
        total_fees = fee_totals[0] or 0
        fees_paid = fee_totals[1] or 0
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

    return render_template(
        'admin/dashboard.html',
        stats=stats,
        announcements=announcements,
        selected_semester=selected_semester,
        selected_hostel_id=selected_hostel_id,
        consultancies=consultancies
    )


@admin_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@admin_required
def change_password():
    if request.method == 'POST':
        new_username = request.form.get('new_username', '').strip()
        new_email = normalize_email(request.form.get('new_email', ''))
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')

        if not old_password:
            flash('Old password is required', 'error')
            return redirect(url_for('admin.change_password'))

        if not check_password_hash(current_user.password, old_password):
            flash('Old password is incorrect', 'error')
            return redirect(url_for('admin.change_password'))

        if not new_username:
            flash('Username is required', 'error')
            return redirect(url_for('admin.change_password'))

        if not new_email:
            flash('Recovery email is required', 'error')
            return redirect(url_for('admin.change_password'))

        if not is_valid_email(new_email):
            flash('Enter a valid recovery email address', 'error')
            return redirect(url_for('admin.change_password'))

        existing_username = User.query.filter(
            User.username == new_username,
            User.id != current_user.id
        ).first()
        if existing_username:
            flash('Username already exists. Please choose another username.', 'error')
            return redirect(url_for('admin.change_password'))

        existing_email = User.query.filter(
            User.email == new_email,
            User.id != current_user.id
        ).first()
        if existing_email:
            flash('Email already exists. Please choose another recovery email.', 'error')
            return redirect(url_for('admin.change_password'))

        if new_password:
            if len(new_password) < 6:
                flash('New password must be at least 6 characters', 'error')
                return redirect(url_for('admin.change_password'))

            if new_password != confirm_password:
                flash('New passwords do not match', 'error')
                return redirect(url_for('admin.change_password'))

            if old_password == new_password:
                flash('New password must be different from old password', 'error')
                return redirect(url_for('admin.change_password'))
        elif confirm_password:
            flash('Enter new password before confirm password', 'error')
            return redirect(url_for('admin.change_password'))

        username_changed = new_username != current_user.username
        email_changed = new_email != normalize_email(current_user.email)
        password_changed = bool(new_password)

        if not (username_changed or email_changed or password_changed):
            flash('No changes found. Update username, email, or password.', 'error')
            return redirect(url_for('admin.change_password'))

        current_user.username = new_username
        current_user.email = new_email
        if password_changed:
            current_user.password = generate_password_hash(new_password)
            session['current_login_password'] = new_password
        else:
            # Preserve plain password view value for this session.
            session['current_login_password'] = old_password

        db.session.commit()
        return redirect(url_for('admin.change_password', updated='1'))

    credentials_updated = request.args.get('updated') == '1'
    current_plain_password = session.get('current_login_password', '')
    return render_template(
        'admin/change_password.html',
        credentials_updated=credentials_updated,
        current_plain_password=current_plain_password
    )


@admin_bp.route('/students/sample-template')
@login_required
@admin_required
def download_sample_template():
    df = pd.DataFrame([{
        'PRN': '2023001',
        'Name': 'John Doe',
        'Branch': 'Computer Science',
        'Email': 'john@example.com',
        'Phone': '9876543210',
        'Hostel_Code': 'B1',
        'Semester': 1,
        'Total_Fees': 50000,
        'Fees_Paid': 10000
    }])

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
    agents = User.query.filter_by(role='agent').order_by(User.username.asc()).all()

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

    for agent in agents:
        if agent.consultancy_id and not AgentConsultancy.query.filter_by(
            agent_id=agent.id,
            consultancy_id=agent.consultancy_id
        ).first():
            db.session.add(AgentConsultancy(agent_id=agent.id, consultancy_id=agent.consultancy_id))
    db.session.commit()

    agent_usernames_by_hostel = {}
    primary_agent_by_hostel = {}
    agent_defaults = {}
    for consultancy in consultancies:
        linked = (
            db.session.query(User.id, User.username)
            .join(AgentConsultancy, AgentConsultancy.agent_id == User.id)
            .filter(AgentConsultancy.consultancy_id == consultancy.id, User.role == 'agent')
            .order_by(User.username.asc())
            .all()
        )
        usernames = [row[1] for row in linked]
        if linked:
            primary_agent_by_hostel[consultancy.id] = {'id': linked[0][0], 'username': linked[0][1]}
        if not usernames:
            legacy_agent = User.query.filter_by(role='agent', consultancy_id=consultancy.id).first()
            if legacy_agent:
                usernames = [legacy_agent.username]
                primary_agent_by_hostel[consultancy.id] = {'id': legacy_agent.id, 'username': legacy_agent.username}
        agent_usernames_by_hostel[consultancy.id] = ", ".join(usernames) if usernames else "N/A"

    for agent in agents:
        source_consultancy = None
        if agent.consultancy_id:
            source_consultancy = Consultancy.query.get(agent.consultancy_id)
        if not source_consultancy:
            first_link = AgentConsultancy.query.filter_by(agent_id=agent.id).first()
            if first_link:
                source_consultancy = Consultancy.query.get(first_link.consultancy_id)

        if source_consultancy:
            agent_defaults[agent.id] = {
                'contact_person': source_consultancy.contact_person or '',
                'email': source_consultancy.email or '',
                'phone': source_consultancy.phone or '',
                'address': source_consultancy.address or ''
            }
        else:
            agent_defaults[agent.id] = {
                'contact_person': '',
                'email': agent.email or '',
                'phone': agent.phone or '',
                'address': ''
            }

    return render_template(
        'admin/manage_consultancies.html',
        consultancies=consultancies,
        available_hostels=available_hostels,
        available_agents=agents,
        agent_usernames_by_hostel=agent_usernames_by_hostel,
        primary_agent_by_hostel=primary_agent_by_hostel,
        agent_defaults=agent_defaults
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
    
    existing_agent_id = request.form.get('existing_agent_id')
    agent_username = (request.form.get('agent_username') or '').strip()
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

                db.session.commit()
                flash('Hostel reactivated successfully!', 'success')
                return redirect(url_for('admin.manage_consultancies'))
            else:
                flash('Hostel code already exists!', 'error')
                return redirect(url_for('admin.manage_consultancies'))

        selected_existing_agent = None
        if existing_agent_id:
            selected_existing_agent = User.query.filter_by(id=int(existing_agent_id), role='agent').first()
            if not selected_existing_agent:
                flash('Selected consultant not found!', 'error')
                return redirect(url_for('admin.manage_consultancies'))

            source_consultancy = None
            if selected_existing_agent.consultancy_id:
                source_consultancy = Consultancy.query.get(selected_existing_agent.consultancy_id)
            if not source_consultancy:
                first_link = AgentConsultancy.query.filter_by(agent_id=selected_existing_agent.id).first()
                if first_link:
                    source_consultancy = Consultancy.query.get(first_link.consultancy_id)

            if source_consultancy:
                contact_person = source_consultancy.contact_person
                email = source_consultancy.email
                phone = source_consultancy.phone
                address = source_consultancy.address

        consultancy = Consultancy(
            name=hostel_name,  
            hostel_code=hostel_code,
            contact_person=contact_person,
            email=email,
            phone=phone,
            address=address
        )
        db.session.add(consultancy)
        db.session.flush()
        
        # Assign existing consultant OR create a new one.
        agent = None
        if existing_agent_id:
            agent = selected_existing_agent
        elif agent_username:
            existing_agent = User.query.filter_by(username=agent_username).first()
            if existing_agent:
                if existing_agent.role != 'agent':
                    flash('Username already exists with non-agent role!', 'error')
                    db.session.rollback()
                    return redirect(url_for('admin.manage_consultancies'))
                agent = existing_agent
            else:
                if not agent_password:
                    flash('Agent password is required for new consultant!', 'error')
                    db.session.rollback()
                    return redirect(url_for('admin.manage_consultancies'))
                agent = User(
                    username=agent_username,
                    password=generate_password_hash(agent_password),
                    email=email,
                    phone=phone,
                    role='agent',
                    consultancy_id=consultancy.id,
                    agent_totp_secret=User.generate_totp_secret(),
                    agent_totp_enabled=False
                )
                db.session.add(agent)
                db.session.flush()
        else:
            flash('Select an existing consultant or enter new consultant details.', 'error')
            db.session.rollback()
            return redirect(url_for('admin.manage_consultancies'))

        if not agent.consultancy_id:
            agent.consultancy_id = consultancy.id
        if agent.role == 'agent':
            agent.ensure_agent_totp_secret()

        if not AgentConsultancy.query.filter_by(agent_id=agent.id, consultancy_id=consultancy.id).first():
            db.session.add(AgentConsultancy(agent_id=agent.id, consultancy_id=consultancy.id))

        db.session.commit()
        
        flash('Hostel added and consultant assigned successfully!', 'success')
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
        
        # Remove agent-hostel links for this hostel.
        links = AgentConsultancy.query.filter_by(consultancy_id=consultancy.id).all()
        impacted_agent_ids = {link.agent_id for link in links}
        legacy_agents = User.query.filter_by(role='agent', consultancy_id=consultancy.id).all()
        impacted_agent_ids.update(agent.id for agent in legacy_agents)
        for link in links:
            db.session.delete(link)

        # Keep shared consultants if they still have other hostels.
        if impacted_agent_ids:
            agents = User.query.filter(User.role == 'agent', User.id.in_(impacted_agent_ids)).all()
            for agent in agents:
                remaining_link = AgentConsultancy.query.filter_by(agent_id=agent.id).first()
                if agent.consultancy_id == consultancy.id:
                    agent.consultancy_id = remaining_link.consultancy_id if remaining_link else None
                if not remaining_link and not agent.consultancy_id:
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
    consultancies = Consultancy.query.filter_by(is_active=True).order_by(Consultancy.hostel_code).all()
    return render_template('admin/add_student.html', consultancies=consultancies)

@admin_bp.route('/students/upload', methods=['POST'])
@login_required
@admin_required
def upload_students():
    if 'file' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'success': False, 'message': 'No file selected'}), 400
    
    filename = secure_filename(file.filename)
    if not filename:
        return jsonify({'success': False, 'message': 'Invalid file name'}), 400

    upload_dir = os.path.join('static', 'uploads')
    os.makedirs(upload_dir, exist_ok=True)
    filepath = os.path.join(upload_dir, filename)

    try:
        file.save(filepath)
        success, result = import_students_from_excel(filepath)

        if success:
            return jsonify({
                'success': True,
                'message': f"Import complete! Success: {result['success']}, Failed: {result['failed']}",
                'details': result
            })
        return jsonify({'success': False, 'message': result}), 400
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': f'Error processing file: {str(e)}'}), 400
    finally:
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
            except OSError:
                pass

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


@admin_bp.route('/students/delete-filtered', methods=['POST'])
@login_required
@admin_required
def delete_filtered_students():
    try:
        data = request.get_json() or {}
        hostel_code = (data.get('hostel_code') or '').strip()
        pending_filter = (data.get('pending_filter') or '').strip()
        search = (data.get('search') or '').strip()

        query = Student.query.join(Consultancy)

        if hostel_code:
            query = query.filter(Consultancy.hostel_code == hostel_code)

        if pending_filter == 'has_pending':
            query = query.filter(Student.total_fees > Student.fees_paid)
        elif pending_filter == 'no_pending':
            query = query.filter(Student.total_fees <= Student.fees_paid)

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
        if not students:
            return jsonify({'success': False, 'message': 'No students found for current filters'}), 404

        # Safety guard: avoid deleting every student accidentally with no filter/search.
        if not hostel_code and not search and not pending_filter:
            return jsonify({'success': False, 'message': 'Apply at least one filter before bulk delete'}), 400

        deleted_count = 0
        for student in students:
            user = student.user

            log_change(
                user_id=current_user.id,
                user_role='admin',
                action='delete',
                table='students',
                record_id=student.id,
                changes={'student_name': student.full_name, 'prn': student.prn, 'mode': 'bulk'}
            )

            Transaction.query.filter_by(student_id=student.id).delete()
            db.session.delete(student)
            if user:
                db.session.delete(user)
            deleted_count += 1

        db.session.commit()
        return jsonify({'success': True, 'deleted_count': deleted_count})
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

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
    flash('Payment History is disabled in the admin panel.', 'error')
    return redirect(url_for('admin.dashboard'))

@admin_bp.route('/payment-history/export')
@login_required
@admin_required
def export_payment_history():
    flash('Payment History export is disabled in the admin panel.', 'error')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/students/update/<int:id>', methods=['POST'])
@login_required
@admin_required
def update_student(id):
    student = Student.query.get_or_404(id)
    
    try:
        # Get data from request
        data = request.get_json()

        incoming_email = normalize_email(data.get('email', student.email))
        incoming_phone = normalize_phone(data.get('phone', student.phone))
        contact_error = validate_student_contact_uniqueness(
            email=incoming_email,
            phone=incoming_phone,
            exclude_student_id=student.id
        )
        if contact_error:
            return jsonify({'success': False, 'message': contact_error}), 400
        
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
            student.email = normalize_email(data['email'])
            student.user.email = normalize_email(data['email'])
        if 'phone' in data:
            student.phone = normalize_phone(data['phone'])
            student.user.phone = normalize_phone(data['phone'])
            # Update password to new phone number
            from werkzeug.security import generate_password_hash
            student.user.password = generate_password_hash(normalize_phone(data['phone']))
        if 'total_fees' in data:
            student.total_fees = float(data['total_fees'])
        if 'fees_paid' in data:
            student.fees_paid = float(data['fees_paid'])
        if 'consultancy_id' in data:
            student.consultancy_id = int(data['consultancy_id'])
            student.user.consultancy_id = int(data['consultancy_id'])

        if student.fees_paid > student.total_fees:
            return jsonify({'success': False, 'message': 'Paid fees cannot be greater than total fees'}), 400
        
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


@admin_bp.route('/students/<int:student_id>/semester-fees/add', methods=['POST'])
@login_required
@admin_required
def add_semester_fee(student_id):
    return jsonify({
        'success': False,
        'message': 'Adding semester fees is disabled in admin view data.'
    }), 403


@admin_bp.route('/students/semester-fees/update/<int:semester_fee_id>', methods=['POST'])
@login_required
@admin_required
def update_semester_fee(semester_fee_id):
    semester_fee = StudentSemesterFee.query.get_or_404(semester_fee_id)
    student = semester_fee.student
    data = request.get_json() or {}

    semester = parse_semester_value(data.get('semester', semester_fee.semester))
    if semester is None:
        return jsonify({'success': False, 'message': 'Semester must be between 1 and 8'}), 400

    try:
        total_fees = float(data.get('total_fees', semester_fee.total_fees))
        fees_paid = float(data.get('fees_paid', semester_fee.fees_paid))
    except (TypeError, ValueError):
        return jsonify({'success': False, 'message': 'Fees must be valid numbers'}), 400

    if total_fees < 0 or fees_paid < 0:
        return jsonify({'success': False, 'message': 'Fees cannot be negative'}), 400
    if fees_paid > total_fees:
        return jsonify({'success': False, 'message': 'Paid fees cannot be greater than total fees'}), 400

    duplicate_semester = StudentSemesterFee.query.filter(
        StudentSemesterFee.student_id == student.id,
        StudentSemesterFee.semester == semester,
        StudentSemesterFee.id != semester_fee.id
    ).first()
    if duplicate_semester:
        return jsonify({'success': False, 'message': 'Another fee row already exists for this semester'}), 400

    try:
        semester_fee.semester = semester
        semester_fee.total_fees = total_fees
        semester_fee.fees_paid = fees_paid

        student.recalculate_fee_totals()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Semester fee updated successfully',
            'semester_fee': semester_fee_payload(semester_fee),
            'student_totals': {
                'total_fees': student.total_fees,
                'fees_paid': student.fees_paid,
                'fees_pending': student.fees_pending
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400


@admin_bp.route('/students/semester-fees/delete/<int:semester_fee_id>', methods=['POST'])
@login_required
@admin_required
def delete_semester_fee(semester_fee_id):
    semester_fee = StudentSemesterFee.query.get_or_404(semester_fee_id)
    student = semester_fee.student

    try:
        db.session.delete(semester_fee)
        db.session.flush()
        student.recalculate_fee_totals()
        db.session.commit()

        return jsonify({
            'success': True,
            'message': 'Semester fee deleted successfully',
            'student_id': student.id,
            'student_totals': {
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
        email = normalize_email(request.form.get('email'))
        phone = normalize_phone(request.form.get('phone'))
        consultancy_id = request.form.get('consultancy_id')
        semester_raw = request.form.get('semester')
        total_fees = float(request.form.get('total_fees'))
        fees_paid = float(request.form.get('fees_paid', 0))

        semester = parse_semester_value(semester_raw)
        if semester is None:
            flash('Please select a valid semester (1 to 8).', 'error')
            return redirect(url_for('admin.add_student_page'))

        if fees_paid > total_fees:
            flash('Fees paid cannot be greater than total fees.', 'error')
            return redirect(url_for('admin.add_student_page'))
        
        # Check if student already exists
        existing_student = Student.query.filter_by(prn=prn).first()
        if existing_student:
            flash('Student with this PRN already exists!', 'error')
            return redirect(url_for('admin.add_student_page'))

        contact_error = validate_student_contact_uniqueness(email=email, phone=phone)
        if contact_error:
            flash(contact_error, 'error')
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
            phone=phone,
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
            total_fees=0,
            fees_paid=0
        )
        db.session.add(student)
        db.session.flush()

        student.semester_fees.append(StudentSemesterFee(
            semester=semester,
            total_fees=total_fees,
            fees_paid=fees_paid
        ))
        student.recalculate_fee_totals()
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
                if agent.role == 'agent':
                    agent.ensure_agent_totp_secret()
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
                if agent.role == 'agent':
                    agent.ensure_agent_totp_secret()

        else:
            # ✅ CREATE AGENT IF MISSING (THIS IS WHY B6 WAS FAILING)
            if agent_username:
                new_agent = User(
                    username=agent_username,
                    password=generate_password_hash(agent_password or "123456"),
                    email=consultancy.email,
                    role='agent',
                    consultancy_id=consultancy.id,
                    agent_totp_secret=User.generate_totp_secret(),
                    agent_totp_enabled=False
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
                'address': consultancy.address
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

