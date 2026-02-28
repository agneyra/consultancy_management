from flask import Blueprint, render_template, request
from flask_login import login_required, current_user
from utils.decorators import student_required
from flask import redirect, url_for, flash
from models.database import db
from models.student import Student
from models.transaction import Announcement
from werkzeug.security import check_password_hash, generate_password_hash

student_bp = Blueprint('student', __name__)

@student_bp.route('/dashboard')
@login_required
@student_required
def dashboard():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    stats = {
        'total_fees': student.total_fees,
        'fees_paid': student.fees_paid,
        'fees_pending': student.fees_pending
    }
    
    # Get active announcements
    announcements = Announcement.query.filter_by(is_active=True).order_by(Announcement.created_at.desc()).all()
    
    return render_template('student/dashboard.html', 
                         student=student, 
                         stats=stats,
                         announcements=announcements)

@student_bp.route('/pay-fees')
@login_required
@student_required
def pay_fees():
    flash('Pay Fees is disabled in this panel.', 'error')
    return redirect(url_for('student.dashboard'))


@student_bp.route('/pay-fees', methods=['POST'])
@login_required
@student_required
def pay_fees_submit():
    flash('Pay Fees is disabled in this panel.', 'error')
    return redirect(url_for('student.dashboard'))

@student_bp.route('/transaction-history')
@login_required
@student_required
def transaction_history():
    flash('Transaction History is disabled in this panel.', 'error')
    return redirect(url_for('student.dashboard'))

@student_bp.route('/need-help')
@login_required
@student_required
def need_help():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    return render_template('student/need_help.html', student=student)

@student_bp.route('/change-password', methods=['GET', 'POST'])
@login_required
@student_required
def change_password():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        old_password = request.form.get('old_password', '')
        new_password = request.form.get('new_password', '')
        confirm_password = request.form.get('confirm_password', '')
        
        if not check_password_hash(current_user.password, old_password):
            flash('Old password is incorrect', 'error')
            return redirect(url_for('student.change_password'))

        if len(new_password) < 6:
            flash('New password must be at least 6 characters', 'error')
            return redirect(url_for('student.change_password'))

        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('student.change_password'))

        if old_password == new_password:
            flash('New password must be different from old password', 'error')
            return redirect(url_for('student.change_password'))

        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('student.dashboard'))
    
    return render_template('student/change_password.html', student=student)

