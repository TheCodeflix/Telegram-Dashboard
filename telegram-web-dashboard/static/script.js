// Telegram Web Dashboard - Main Script

document.addEventListener('DOMContentLoaded', function () {
    checkHealth();
});

async function checkHealth() {
    try {
        const response = await fetch('/health');
        const data = await response.json();
        const indicator = document.getElementById('health-indicator');
        if (indicator) {
            if (data.status === 'healthy') {
                indicator.textContent = 'Online';
                indicator.classList.add('status-active');
            } else {
                indicator.textContent = 'Offline';
                indicator.classList.add('status-inactive');
            }
        }
    } catch (err) {
        const indicator = document.getElementById('health-indicator');
        if (indicator) {
            indicator.textContent = 'Unreachable';
            indicator.classList.add('status-inactive');
        }
    }
}

function showAlert(message, type = 'info') {
    const container = document.getElementById('alert-container');
    if (!container) return;
    const alert = document.createElement('div');
    alert.className = `alert alert-${type} alert-dismissible fade show`;
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    container.appendChild(alert);
    setTimeout(() => alert.remove(), 5000);
}
