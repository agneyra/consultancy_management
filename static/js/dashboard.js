// Dashboard Chart Functions using Chart.js
const FEE_CHART_COLORS = ['#2563eb', '#10b981', '#f59e0b'];

function parseChartNumber(value) {
    if (typeof value === 'number') {
        return Number.isFinite(value) ? value : 0;
    }

    if (value === null || value === undefined) {
        return 0;
    }

    const cleaned = String(value).replace(/[^0-9.-]/g, '');
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : 0;
}

// Initialize Pie Chart
function initFeeChart(totalFees, feesPaid, feesPending) {
    const ctx = document.getElementById('feeChart');
    if (!ctx) return;

    const labels = ['Total Fees', 'Fees Paid', 'Fees Pending'];
    const rawData = [
        Math.max(0, parseChartNumber(totalFees)),
        Math.max(0, parseChartNumber(feesPaid)),
        Math.max(0, parseChartNumber(feesPending))
    ];

    // Chart.js renders no slices when every pie value is 0.
    const hasPositiveData = rawData.some(value => value > 0);
    const chartData = hasPositiveData ? rawData : [1, 1, 1];
    const colors = FEE_CHART_COLORS;

    new Chart(ctx, {
        type: 'pie',
        data: {
            labels: labels,
            datasets: [{
                data: chartData,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#ffffff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            aspectRatio: 1,
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
                subtitle: {
                    display: !hasPositiveData,
                    text: 'No fee data available yet',
                    color: '#64748b',
                    padding: {
                        bottom: 8
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = rawData[context.dataIndex] || 0;
                            return `${label}: \u20B9${value.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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
                    ...FEE_CHART_COLORS,
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
        element.textContent = '\u20B9' + Math.floor(current).toLocaleString('en-IN');
    }, 16);
}

// Load Dashboard on page load
document.addEventListener('DOMContentLoaded', function() {
    const chartElement = document.getElementById('feeChart');
    if (chartElement) {
        const totalFees = parseChartNumber(chartElement.dataset.total);
        const feesPaid = parseChartNumber(chartElement.dataset.paid);
        const feesPending = parseChartNumber(chartElement.dataset.pending);

        initFeeChart(totalFees, feesPaid, feesPending);
    }
});
