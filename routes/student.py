from flask import Blueprint, render_template, request, jsonify
from flask_login import login_required, current_user
from utils.decorators import student_required
from flask import redirect, url_for, flash
from utils.payment_gateway import PaymentGateway, generate_transaction_id
from models.database import db
from models.student import Student
from models.transaction import Transaction, Announcement
from config import Config

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
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    consultancy = student.consultancy
    
    return render_template('student/pay_fees.html', 
                         student=student,
                         consultancy=consultancy)

@student_bp.route('/create-payment-order', methods=['POST'])
@login_required
@student_required
def create_payment_order():
    data = request.get_json()
    amount = float(data.get('amount', 0))
    
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    consultancy = student.consultancy
    
    # Initialize payment gateway with consultancy credentials
    pg = PaymentGateway(
        consultancy.payment_gateway_id or Config.RAZORPAY_KEY_ID,
        consultancy.payment_gateway_key or Config.RAZORPAY_KEY_SECRET
    )
    
    # Create order
    success, result = pg.create_order(amount)
    
    if success:
        return jsonify({
            'success': True,
            'order_id': result['id'],
            'amount': result['amount'],
            'currency': result['currency'],
            'key_id': consultancy.payment_gateway_id or Config.RAZORPAY_KEY_ID
        })
    else:
        return jsonify({'success': False, 'message': result}), 400

@student_bp.route('/verify-payment', methods=['POST'])
@login_required
@student_required
def verify_payment():
    data = request.get_json()
    
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    consultancy = student.consultancy
    
    # Initialize payment gateway
    pg = PaymentGateway(
        consultancy.payment_gateway_id or Config.RAZORPAY_KEY_ID,
        consultancy.payment_gateway_key or Config.RAZORPAY_KEY_SECRET
    )
    
    # Verify payment
    is_valid = pg.verify_payment(
        data.get('order_id'),
        data.get('payment_id'),
        data.get('signature')
    )
    
    if is_valid:
        # Create transaction record
        transaction = Transaction(
            transaction_id=generate_transaction_id(),
            student_id=student.id,
            consultancy_id=consultancy.id,
            amount=data.get('amount') / 100,  # Convert from paise to rupees
            payment_method='razorpay',
            status='completed',
            gateway_response=str(data)
        )
        db.session.add(transaction)
        
        # Update student fees
        student.fees_paid += transaction.amount
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'message': 'Payment successful!',
            'transaction_id': transaction.transaction_id
        })
    else:
        return jsonify({'success': False, 'message': 'Payment verification failed'}), 400

@student_bp.route('/transaction-history')
@login_required
@student_required
def transaction_history():
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    transactions = Transaction.query.filter_by(student_id=student.id).order_by(Transaction.payment_date.desc()).all()
    
    return render_template('student/transaction_history.html', 
                         transactions=transactions,
                         student=student)

@student_bp.route('/change-password', methods=['GET'])
@login_required
@student_required
def change_password():
    from werkzeug.security import check_password_hash, generate_password_hash
    from flask import flash
    
    student = Student.query.filter_by(user_id=current_user.id).first_or_404()
    
    if request.method == 'POST':
        current_password = request.form.get('current_password')
        new_password = request.form.get('new_password')
        confirm_password = request.form.get('confirm_password')
        verification_code = request.form.get('verification_code')
        
        # Verify current password
        if not check_password_hash(current_user.password, current_password):
            flash('Current password is incorrect', 'error')
            return redirect(url_for('student.change_password'))
        
        # Verify new passwords match
        if new_password != confirm_password:
            flash('New passwords do not match', 'error')
            return redirect(url_for('student.change_password'))
        
        # Verify that verification code matches phone or email
        if verification_code != student.phone and verification_code != student.email:
            flash('Verification failed. Enter your registered phone number or email', 'error')
            return redirect(url_for('student.change_password'))
        
        # Update password
        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        
        flash('Password changed successfully!', 'success')
        return redirect(url_for('student.dashboard'))
    
    return render_template('student/change_password.html', student=student)

# Add these routes to routes/student.py
import random
import uuid
from datetime import datetime, timedelta

# Store OTP sessions in memory (in production, use Redis or database)
otp_sessions = {}

@student_bp.route('/send-otp', methods=['POST'])
@login_required
@student_required
def send_otp():
    try:
        data = request.get_json()
        method = data.get('method')  # 'phone' or 'email'
        
        student = Student.query.filter_by(user_id=current_user.id).first_or_404()
        
        # Generate 6-digit OTP
        otp_code = ''.join([str(random.randint(0, 9)) for _ in range(6)])
        
        # Create session
        session_id = str(uuid.uuid4())
        otp_sessions[session_id] = {
            'otp': otp_code,
            'user_id': current_user.id,
            'method': method,
            'created_at': datetime.utcnow(),
            'expires_at': datetime.utcnow() + timedelta(minutes=10)
        }
        
        # In production, send actual OTP via SMS/Email
        # For now, we'll just log it (in development, you can print it)
        print(f"OTP for {student.full_name}: {otp_code}")
        
        # Simulate sending OTP
        if method == 'phone':
            # Here you would integrate with SMS gateway like Twilio
            destination = student.phone
            print(f"Sending OTP {otp_code} to phone: {destination}")
        elif method == 'email':
            # Here you would send email
            destination = student.email
            print(f"Sending OTP {otp_code} to email: {destination}")
        
        return jsonify({
            'success': True,
            'session_id': session_id,
            'message': f'OTP sent to your {method}',
            # Remove this in production - only for development/testing
            'otp_code': otp_code  
        })
        
    except Exception as e:
        return jsonify({'success': False, 'message': str(e)}), 400


@student_bp.route('/verify-otp-change-password', methods=['POST'])
@login_required
@student_required
def verify_otp_change_password():
    from werkzeug.security import check_password_hash, generate_password_hash
    
    try:
        data = request.get_json()
        session_id = data.get('session_id')
        otp_code = data.get('otp_code')
        current_password = data.get('current_password')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        # Verify session exists
        if session_id not in otp_sessions:
            return jsonify({'success': False, 'message': 'Invalid or expired OTP session'}), 400
        
        session = otp_sessions[session_id]
        
        # Check if OTP is expired
        if datetime.utcnow() > session['expires_at']:
            del otp_sessions[session_id]
            return jsonify({'success': False, 'message': 'OTP has expired. Please request a new one.'}), 400
        
        # Verify OTP
        if session['otp'] != otp_code:
            return jsonify({'success': False, 'message': 'Invalid OTP code'}), 400
        
        # Verify user
        if session['user_id'] != current_user.id:
            return jsonify({'success': False, 'message': 'Session mismatch'}), 400
        
        # Verify current password
        if not check_password_hash(current_user.password, current_password):
            return jsonify({'success': False, 'message': 'Current password is incorrect'}), 400
        
        # Verify new passwords match
        if new_password != confirm_password:
            return jsonify({'success': False, 'message': 'New passwords do not match'}), 400
        
        # Update password
        current_user.password = generate_password_hash(new_password)
        db.session.commit()
        
        # Clean up OTP session
        del otp_sessions[session_id]
        
        return jsonify({
            'success': True,
            'message': 'Password changed successfully!'
        })
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'success': False, 'message': str(e)}), 400

