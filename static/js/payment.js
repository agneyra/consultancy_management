// Fee payment handling
document.addEventListener('DOMContentLoaded', function () {
    const paymentForm = document.getElementById('paymentForm');
    if (!paymentForm) return;

    paymentForm.addEventListener('submit', async function (e) {
        e.preventDefault();

        const amountInput = document.getElementById('paymentAmount');
        const amount = parseFloat(amountInput.value || '0');
        const maxAmount = parseFloat(amountInput.getAttribute('max') || '0');

        if (isNaN(amount) || amount <= 0) {
            alert('Please enter a valid amount');
            return;
        }

        if (amount > maxAmount) {
            alert('Amount cannot exceed pending fees');
            return;
        }

        try {
            const response = await fetch('/student/pay-fees', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ amount: amount })
            });

            const data = await response.json();
            if (!data.success) {
                alert(data.message || 'Payment failed');
                return;
            }

            alert('Payment successful! Transaction ID: ' + data.transaction_id);
            window.location.reload();
        } catch (error) {
            alert('Payment failed: ' + error.message);
        }
    });

    document.querySelectorAll('.quick-pay-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
            const amount = parseFloat(this.dataset.amount || '0');
            if (!isNaN(amount)) {
                document.getElementById('paymentAmount').value = amount;
            }
        });
    });
});

function formatPaymentAmount(input) {
    input.value = input.value.replace(/[^0-9.]/g, '');
}
