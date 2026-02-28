// Main JavaScript Functions
const nativeAlert = window.alert.bind(window);
const nativeConfirm = window.confirm.bind(window);
const THEME_STORAGE_KEY = 'shs-theme';

function getStoredTheme() {
    try {
        const savedTheme = localStorage.getItem(THEME_STORAGE_KEY);
        if (savedTheme === 'dark' || savedTheme === 'light') {
            return savedTheme;
        }
    } catch (error) {
        console.error('Theme storage read failed:', error);
    }
    return null;
}

function applyTheme(theme, persist = true) {
    const normalizedTheme = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', normalizedTheme);

    if (persist) {
        try {
            localStorage.setItem(THEME_STORAGE_KEY, normalizedTheme);
        } catch (error) {
            console.error('Theme storage write failed:', error);
        }
    }

    const toggle = document.getElementById('themeToggle');
    if (toggle) {
        const isDark = normalizedTheme === 'dark';
        toggle.setAttribute('aria-pressed', isDark ? 'true' : 'false');
        toggle.setAttribute('aria-label', isDark ? 'Switch to light theme' : 'Switch to dark theme');
        toggle.setAttribute('title', isDark ? 'Light Theme' : 'Dark Theme');
    }
}

function initializeThemeToggle() {
    const toggle = document.getElementById('themeToggle');
    if (!toggle) {
        return;
    }

    const currentTheme = document.documentElement.getAttribute('data-theme') || getStoredTheme() || 'light';
    applyTheme(currentTheme, false);

    toggle.addEventListener('click', () => {
        const nowDark = document.documentElement.getAttribute('data-theme') === 'dark';
        applyTheme(nowDark ? 'light' : 'dark', true);
    });
}

// Modal Functions
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'block';
        document.body.classList.add('modal-open');
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.style.display = 'none';
        const hasVisibleModal = Array.from(document.querySelectorAll('.modal'))
            .some(m => getComputedStyle(m).display !== 'none');
        if (!hasVisibleModal) {
            document.body.classList.remove('modal-open');
        }
    }
}

// Close modal when clicking outside
window.onclick = function (event) {
    if (event.target.classList.contains('modal')) {
        event.target.style.display = 'none';
        const hasVisibleModal = Array.from(document.querySelectorAll('.modal'))
            .some(m => getComputedStyle(m).display !== 'none');
        if (!hasVisibleModal) {
            document.body.classList.remove('modal-open');
        }
    }
}

// Flash Message Auto Hide
document.addEventListener('DOMContentLoaded', function () {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.opacity = '0';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });

    // Initialize responsive navigation
    initializeResponsiveNavigation();
    lockAuthHorizontalScroll();
    initializeThemeToggle();
});

// Confirm Delete
function confirmDelete(message) {
    return window.appConfirm(message || 'Are you sure you want to delete this item?');
}

function showAppDialog(message, isConfirm) {
    return new Promise((resolve) => {
        const overlay = document.getElementById('appDialogOverlay');
        const title = document.getElementById('appDialogTitle');
        const messageEl = document.getElementById('appDialogMessage');
        const okBtn = document.getElementById('appDialogOk');
        const cancelBtn = document.getElementById('appDialogCancel');

        if (!overlay || !title || !messageEl || !okBtn || !cancelBtn) {
            // Fallback in case dialog markup is unavailable
            if (isConfirm) {
                resolve(nativeConfirm(message));
            } else {
                nativeAlert(message);
                resolve(true);
            }
            return;
        }

        title.textContent = isConfirm ? 'Please Confirm' : 'Notice';
        messageEl.textContent = String(message || '');
        cancelBtn.style.display = isConfirm ? 'inline-block' : 'none';
        okBtn.textContent = isConfirm ? 'OK' : 'Close';

        const close = (result) => {
            overlay.style.display = 'none';
            okBtn.onclick = null;
            cancelBtn.onclick = null;
            overlay.onclick = null;
            document.removeEventListener('keydown', keyHandler);
            resolve(result);
        };

        const keyHandler = (event) => {
            if (event.key === 'Enter') {
                event.preventDefault();
                close(true);
            } else if (event.key === 'Escape' && isConfirm) {
                event.preventDefault();
                close(false);
            }
        };

        okBtn.onclick = () => close(true);
        cancelBtn.onclick = () => close(false);
        overlay.onclick = (event) => {
            if (event.target === overlay && isConfirm) {
                close(false);
            }
        };

        overlay.style.display = 'flex';
        document.addEventListener('keydown', keyHandler);
        okBtn.focus();
    });
}

// Search Function
function searchTable(inputId, tableId) {
    const input = document.getElementById(inputId);
    const filter = input.value.toUpperCase();
    const table = document.getElementById(tableId);
    const rows = table.getElementsByTagName('tr');

    for (let i = 1; i < rows.length; i++) {
        const row = rows[i];
        const cells = row.getElementsByTagName('td');
        let found = false;

        for (let j = 0; j < cells.length; j++) {
            const cell = cells[j];
            if (cell) {
                const textValue = cell.textContent || cell.innerText;
                if (textValue.toUpperCase().indexOf(filter) > -1) {
                    found = true;
                    break;
                }
            }
        }

        row.style.display = found ? '' : 'none';
    }
}

// Format Currency
function formatCurrency(amount) {
    return new Intl.NumberFormat('en-IN', {
        style: 'currency',
        currency: 'INR'
    }).format(amount);
}

// Format Date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString('en-IN', {
        year: 'numeric',
        month: 'short',
        day: 'numeric'
    });
}

// Show Loading Spinner
function showLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '<div class="spinner"></div>';
    }
}

// Hide Loading Spinner
function hideLoading(elementId) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = '';
    }
}

// Copy to Clipboard
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(() => {
        alert('Copied to clipboard!');
    }).catch(err => {
        console.error('Failed to copy:', err);
    });
}

// Download as CSV
function downloadTableAsCSV(tableId, filename) {
    const table = document.getElementById(tableId);
    let csv = [];
    const rows = table.querySelectorAll('tr');

    for (let i = 0; i < rows.length; i++) {
        const row = [];
        const cols = rows[i].querySelectorAll('td, th');

        for (let j = 0; j < cols.length; j++) {
            row.push(cols[j].innerText);
        }

        csv.push(row.join(','));
    }

    const csvFile = new Blob([csv.join('\n')], { type: 'text/csv' });
    const downloadLink = document.createElement('a');
    downloadLink.download = filename;
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.style.display = 'none';
    document.body.appendChild(downloadLink);
    downloadLink.click();
    document.body.removeChild(downloadLink);
}

/* ========================================
   HAMBURGER MENU & RESPONSIVE NAVIGATION
   ======================================== */

function initializeResponsiveNavigation() {
    // Check if sidebar exists (not on login/home page)
    const sidebar = document.querySelector('.sidebar');
    if (!sidebar) return;
    const sidebarNav = sidebar.querySelector('.sidebar-nav');
    const topNavLinks = document.querySelector('.nav-links');
    const themeToggleItem = topNavLinks ? topNavLinks.querySelector('.theme-toggle-nav-item') : null;
    const authNavItem = topNavLinks ? topNavLinks.querySelector('.auth-nav-item') : null;

    let sidebarThemeLabel = null;
    if (themeToggleItem) {
        sidebarThemeLabel = document.createElement('span');
        sidebarThemeLabel.className = 'sidebar-theme-label';
        sidebarThemeLabel.textContent = 'Theme';
    }

    // Create hamburger button
    const hamburger = document.createElement('button');
    hamburger.className = 'hamburger-menu';
    hamburger.setAttribute('aria-label', 'Toggle menu');
    hamburger.innerHTML = `
        <div class="hamburger-icon">
            <span></span>
            <span></span>
            <span></span>
        </div>
    `;

    // Create overlay
    const overlay = document.createElement('div');
    overlay.className = 'sidebar-overlay';

    // Create close button inside sidebar header (mobile)
    const sidebarHeader = sidebar.querySelector('.sidebar-header');
    const sidebarCloseBtn = document.createElement('button');
    sidebarCloseBtn.className = 'sidebar-close-btn';
    sidebarCloseBtn.setAttribute('aria-label', 'Close menu');
    sidebarCloseBtn.innerHTML = '<span class="sidebar-close-icon" aria-hidden="true">&times;</span>';
    if (sidebarHeader) {
        sidebarHeader.appendChild(sidebarCloseBtn);
    }

    // Add to navbar so it stays aligned with logout button area
    const navContainer = document.querySelector('.nav-container');
    if (navContainer) {
        navContainer.appendChild(hamburger);
    } else {
        document.body.appendChild(hamburger);
    }
    document.body.appendChild(overlay);
    document.body.classList.add('has-mobile-sidebar-toggle');

    // Toggle sidebar
    function toggleSidebar() {
        sidebar.classList.toggle('open');
        hamburger.classList.toggle('active');
        overlay.classList.toggle('active');
        document.body.classList.toggle('sidebar-open');
    }

    function closeSidebar() {
        sidebar.classList.remove('open');
        hamburger.classList.remove('active');
        overlay.classList.remove('active');
        document.body.classList.remove('sidebar-open');
    }

    function syncThemeTogglePlacement() {
        if (!themeToggleItem || !sidebarNav || !topNavLinks) {
            return;
        }

        const isMobileViewport = window.innerWidth <= 1024;
        const inSidebar = sidebarNav.contains(themeToggleItem);

        if (isMobileViewport) {
            if (!inSidebar) {
                if (sidebarThemeLabel && !themeToggleItem.contains(sidebarThemeLabel)) {
                    themeToggleItem.insertBefore(sidebarThemeLabel, themeToggleItem.firstChild);
                }
                sidebarNav.appendChild(themeToggleItem);
            }
        } else if (inSidebar) {
            if (sidebarThemeLabel && themeToggleItem.contains(sidebarThemeLabel)) {
                themeToggleItem.removeChild(sidebarThemeLabel);
            }
            if (authNavItem && topNavLinks.contains(authNavItem)) {
                topNavLinks.insertBefore(themeToggleItem, authNavItem);
            } else {
                topNavLinks.appendChild(themeToggleItem);
            }
        }
    }

    syncThemeTogglePlacement();

    // Event listeners
    hamburger.addEventListener('click', toggleSidebar);
    sidebarCloseBtn.addEventListener('click', closeSidebar);
    overlay.addEventListener('click', closeSidebar);

    // Close on nav link click
    const sidebarLinks = sidebar.querySelectorAll('a');
    sidebarLinks.forEach(link => {
        link.addEventListener('click', closeSidebar);
    });

    // Close on ESC key
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && sidebar.classList.contains('open')) {
            closeSidebar();
        }
    });

    // Close on window resize to desktop
    let resizeTimer;
    window.addEventListener('resize', function () {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function () {
            syncThemeTogglePlacement();
            if (window.innerWidth > 1024) {
                closeSidebar();
            }
        }, 250);
    });
}

function lockAuthHorizontalScroll() {
    const isAuthPage = document.querySelector('.auth-gloss-wrap, .role-selector-wrap');
    if (!isAuthPage) {
        return;
    }

    const resetScrollX = () => {
        if (window.scrollX !== 0) {
            window.scrollTo(0, window.scrollY);
        }
    };

    document.documentElement.style.overflowX = 'hidden';
    document.body.style.overflowX = 'hidden';

    resetScrollX();
    setTimeout(resetScrollX, 0);
    setTimeout(resetScrollX, 120);

    window.addEventListener('scroll', resetScrollX, { passive: true });
    window.addEventListener('resize', resetScrollX, { passive: true });
    window.addEventListener('orientationchange', resetScrollX, { passive: true });
}

// Make functions globally available
window.openModal = openModal;
window.closeModal = closeModal;
window.confirmDelete = confirmDelete;
window.appAlert = function (message) {
    return showAppDialog(message, false);
};
window.appConfirm = function (message) {
    return showAppDialog(message, true);
};
window.searchTable = searchTable;
window.formatCurrency = formatCurrency;
window.formatDate = formatDate;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
window.copyToClipboard = copyToClipboard;
window.downloadTableAsCSV = downloadTableAsCSV;

// Replace native alert with themed centered popup.
window.alert = function (message) {
    window.appAlert(message);
};
