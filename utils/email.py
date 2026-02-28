import os
from flask import current_app
from threading import Thread
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail


def send_async_email(app, message):
    with app.app_context():
        try:
            sg = SendGridAPIClient(os.environ.get("SENDGRID_API_KEY"))
            response = sg.send(message)
            print(f"Successfully sent OTP. Status code: {response.status_code}")
        except Exception as e:
            print(f"Mail sending failed: {str(e)}")


def send_reset_otp(email, otp):
    app = current_app._get_current_object()

    message = Mail(
        from_email="sandiphostelservices@sandiphostelservices.com",  # MUST be verified in SendGrid
        to_emails=email,
        subject="Password Reset OTP",
        plain_text_content=f"Your OTP is {otp}. It is valid for 10 minutes.",
    )

    Thread(target=send_async_email, args=(app, message)).start()
    return True
