// Payment Processing Functions

// Initialize Razorpay Payment
async function initiatePayment(amount) {
    try {
        // Create order on server
        const response = await fetch('/student/create-payment-order', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ amount: amount })
        });
        
        const data = await response.json();
        
        if (!data.success) {
            alert('Failed to create payment order');
            return;
        }
        
        // Initialize Razorpay
        const options = {
            key: data.key_id,
            amount: data.amount,
            currency: data.currency,
            name: 'Consultancy Management',
            description: 'Fee Payment',
            order_id: data.order_id,
            handler: async function(response) {
                // Verify payment on server
                const verifyResponse = await fetch('/student/verify-payment', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        order_id: response.razorpay_order_id,
                        payment_id: response.razorpay_payment_id,
                        signature: response.razorpay_signature,
                        amount: data.amount
                    })
                });
                
                const verifyData = await verifyResponse.json();
                
                if (verifyData.success) {
                    alert('Payment successful! Transaction ID: ' + verifyData.transaction_id);
                    window.location.reload();
                } else {
                    alert('Payment verification failed');
                }
            },
            prefill: {
                name: document.getElementById('studentName')?.textContent || '',
                email: document.getElementById('studentEmail')?.textContent || ''
            },
            theme: {
                color: '#2563eb'
            }
        };
        
        const rzp = new Razorpay(options);
        rzp.open();
        
    } catch (error) {
        console.error('Payment error:', error);
        alert('Payment failed: ' + error.message);
    }
}

// Handle Payment Form Submission
document.addEventListener('DOMContentLoaded', function() {
    const paymentForm = document.getElementById('paymentForm');
    
    if (paymentForm) {
        paymentForm.addEventListener('submit', function(e) {
            e.preventDefault();
            
            const amount = parseFloat(document.getElementById('paymentAmount').value);
            const pendingAmount = parseFloat(document.getElementById('pendingAmount')?.textContent || 0);
            
            if (amount <= 0) {
                alert('Please enter a valid amount');
                return;
            }
            
            if (amount > pendingAmount) {
                alert('Amount cannot exceed pending fees');
                return;
            }
            
            initiatePayment(amount);
        });
        
        // Quick pay buttons
        const quickPayButtons = document.querySelectorAll('.quick-pay-btn');
        quickPayButtons.forEach(btn => {
            btn.addEventListener('click', function() {
                const amount = parseFloat(this.dataset.amount);
                document.getElementById('paymentAmount').value = amount;
            });
        });
    }
});

// Format amount in payment field
function formatPaymentAmount(input) {
    let value = input.value.replace(/[^0-9.]/g, '');
    input.value = value;
}