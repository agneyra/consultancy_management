from flask_mail import Message
from flask import current_app
from flask_mail import Mail, Message

mail = Mail()

def send_reset_otp(email, otp):
    msg = Message(
        subject="Password Reset OTP",
        recipients=[email],
        body=f"Your OTP is {otp}. It is valid for 10 minutes."
    )
    mail.send(msg)
