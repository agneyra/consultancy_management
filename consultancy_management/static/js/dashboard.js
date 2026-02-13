// Dashboard Chart Functions using Chart.js

// Initialize Pie Chart
function initFeeChart(totalFees, feesPaid, feesPending) {
    const ctx = document.getElementById('feeChart');
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'pie',
        data: {
            labels: ['Total Fees', 'Fees Paid', 'Fees Pending'],
            datasets: [{
                data: [totalFees, feesPaid, feesPending],
                backgroundColor: [
                    '#2563eb',
                    '#10b981',
                    '#f59e0b'
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        padding: 15,
                        font: {
                            size: 12
                        }
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            return label + ': ₹' + value.toLocaleString('en-IN');
                        }
                    }
                }
            }
        }
    });
}

// Initialize Doughnut Chart
function initDoughnutChart(elementId, labels, data, colors) {
    const ctx = document.getElementById(elementId);
    if (!ctx) return;
    
    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: data,
                backgroundColor: colors || [
                    '#2563eb',
                    '#10b981',
                    '#f59e0b',
                    '#ef4444'
                ],
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            plugins: {
                legend: {
                    position: 'bottom'
                }
            }
        }
    });
}

// Update Stats Animation
function animateValue(elementId, start, end, duration) {
    const element = document.getElementById(elementId);
    if (!element) return;
    
    const range = end - start;
    const increment = range / (duration / 16);
    let current = start;
    
    const timer = setInterval(() => {
        current += increment;
        if ((increment > 0 && current >= end) || (increment < 0 && current <= end)) {
            current = end;
            clearInterval(timer);
        }
        element.textContent = '₹' + Math.floor(current).toLocaleString('en-IN');
    }, 16);
}

// Load Dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    const chartElement = document.getElementById('feeChart');
    if (chartElement) {
        const totalFees = parseFloat(chartElement.dataset.total) || 0;
        const feesPaid = parseFloat(chartElement.dataset.paid) || 0;
        const feesPending = parseFloat(chartElement.dataset.pending) || 0;
        
        initFeeChart(totalFees, feesPaid, feesPending);
    }
});