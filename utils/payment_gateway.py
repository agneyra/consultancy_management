import razorpay
from datetime import datetime
import uuid

class PaymentGateway:
    def __init__(self, key_id, key_secret):
        self.client = razorpay.Client(auth=(key_id, key_secret))
    
    def create_order(self, amount, currency='INR', receipt=None):
        """Create a payment order"""
        try:
            if not receipt:
                receipt = f"receipt_{uuid.uuid4().hex[:10]}"
            
            order_data = {
                'amount': int(amount * 100),  # Amount in paise
                'currency': currency,
                'receipt': receipt,
                'payment_capture': 1
            }
            
            order = self.client.order.create(data=order_data)
            return True, order
        except Exception as e:
            return False, str(e)
    
    def verify_payment(self, order_id, payment_id, signature):
        """Verify payment signature"""
        try:
            params = {
                'razorpay_order_id': order_id,
                'razorpay_payment_id': payment_id,
                'razorpay_signature': signature
            }
            self.client.utility.verify_payment_signature(params)
            return True
        except:
            return False
    
    def get_payment_details(self, payment_id):
        """Get payment details"""
        try:
            payment = self.client.payment.fetch(payment_id)
            return True, payment
        except Exception as e:
            return False, str(e)

def generate_transaction_id():
    """Generate unique transaction ID"""
    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
    random_str = uuid.uuid4().hex[:6].upper()
    return f"TXN{timestamp}{random_str}"