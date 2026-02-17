// Main JavaScript file for AI Email Dashboard
document.addEventListener('DOMContentLoaded', function() {
    // ===== THEME SWITCHING =====
    const currentTheme = localStorage.getItem('theme') || 'light';
    if (currentTheme === 'dark') document.documentElement.classList.add('dark');

    const themeToggle = document.getElementById('themeToggle');
    if (themeToggle) {
        themeToggle.addEventListener('click', function() {
            document.documentElement.classList.toggle('dark');
            const theme = document.documentElement.classList.contains('dark') ? 'dark' : 'light';
            localStorage.setItem('theme', theme);
        });
    }

    // ===== SIDEBAR TOGGLE =====
    const sidebarToggle = document.getElementById('sidebarToggle');
    const sidebar = document.getElementById('sidebar');
    if (sidebarToggle && sidebar) {
        sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('-translate-x-full'));
        document.addEventListener('click', e => {
            if (window.innerWidth < 768 &&
                !sidebar.contains(e.target) &&
                !sidebarToggle.contains(e.target) &&
                !sidebar.classList.contains('-translate-x-full')) {
                sidebar.classList.add('-translate-x-full');
            }
        });
    }

    // ===== USER MENU DROPDOWN =====
    const userMenuButton = document.getElementById('userMenuButton');
    const userMenu = document.getElementById('userMenu');
    if (userMenuButton && userMenu) {
        userMenuButton.addEventListener('click', e => {
            e.stopPropagation();
            userMenu.classList.toggle('hidden');
        });
        document.addEventListener('click', e => {
            if (!userMenuButton.contains(e.target) && !userMenu.contains(e.target)) {
                userMenu.classList.add('hidden');
            }
        });
    }

    // ===== DASHBOARD / SIDEBAR NAVIGATION =====
    const sidebarButtons = document.querySelectorAll('#sidebar button[data-url]');
    sidebarButtons.forEach(button => {
        button.addEventListener('click', e => {
            const url = button.getAttribute('data-url');
            if (!url || url === '#') return; // do nothing for placeholders

            if (url.includes('/dashboard')) {
                e.preventDefault();
                loadDashboardContent(url);
            } else {
                window.location.href = url;
            }
        });
    });

    // ===== DASHBOARD AJAX LOAD =====
    function loadDashboardContent(url) {
        fetch(url)
            .then(res => res.ok ? res.text() : Promise.reject('Failed to load'))
            .then(html => {
                const appContent = document.getElementById('app-content');
                if (!appContent) return;

                // Clear previous content to prevent duplicates
                appContent.innerHTML = '';

                // Insert new dashboard content
                appContent.innerHTML = html;

                // Scroll to top
                window.scrollTo(0, 0);

                // Re-initialize any dashboard-specific scripts
                if (window.initDashboardComponents) window.initDashboardComponents();
            })
            .catch(err => console.error(err));
    }

    // ===== INITIALIZE OTHER FUNCTIONS =====
    initializeTooltips();
    initializeModals();
    initializeFormValidations();
    initializeSearch();
    initializeKeyboardShortcuts();
});

// ===== TOAST SYSTEM =====
function showToast(message, type = 'info', duration = 5000) {
    const toastContainer = document.getElementById('toastContainer');
    const toastTemplate = document.getElementById('toastTemplate');
    
    if (!toastContainer || !toastTemplate) return console.error('Toast container or template not found');
    
    const toast = toastTemplate.content.cloneNode(true).firstElementChild;
    const icon = toast.querySelector('.toast-icon');
    const messageEl = toast.querySelector('.toast-message');

    toast.className = 'toast flex items-center p-4 rounded-lg shadow-lg transform transition-all duration-300 translate-x-full';
    switch(type) {
        case 'success':
            icon.className = 'fas fa-check-circle text-green-500 toast-icon';
            toast.classList.add('bg-green-50', 'dark:bg-green-900', 'text-green-800', 'dark:text-green-200');
            break;
        case 'error':
            icon.className = 'fas fa-exclamation-circle text-red-500 toast-icon';
            toast.classList.add('bg-red-50', 'dark:bg-red-900', 'text-red-800', 'dark:text-red-200');
            break;
        case 'warning':
            icon.className = 'fas fa-exclamation-triangle text-yellow-500 toast-icon';
            toast.classList.add('bg-yellow-50', 'dark:bg-yellow-900', 'text-yellow-800', 'dark:text-yellow-200');
            break;
        default:
            icon.className = 'fas fa-info-circle text-blue-500 toast-icon';
            toast.classList.add('bg-blue-50', 'dark:bg-blue-900', 'text-blue-800', 'dark:text-blue-200');
    }

    messageEl.textContent = message;

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', function() {
        removeToast(toast);
    });

    toastContainer.appendChild(toast);
    setTimeout(() => { toast.classList.remove('translate-x-full'); toast.classList.add('translate-x-0'); }, 10);
    setTimeout(() => removeToast(toast), duration);
}

function removeToast(toast) {
    if (!toast || !toast.parentNode) return;
    toast.classList.add('translate-x-full');
    setTimeout(() => { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 300);
}

// ===== REMAINING FUNCTIONS (Tooltips, Modals, Form Validations, Search, Keyboard, Utilities) =====
// Keep all of your previous functions here as they are
// initializeTooltips(), initializeModals(), initializeFormValidations(), initializeSearch(), initializeKeyboardShortcuts()
// formatDate(), formatTime(), formatRelativeTime(), debounce(), throttle(), isInViewport(), scrollToElement(), copyToClipboard()
// showLoading(), hideLoading(), handleApiError(), validateField(), isValidEmail()

// Export utilities
window.AppUtils = {
    showToast,
    openModal,
    closeModal,
    formatDate,
    formatTime,
    formatRelativeTime,
    debounce,
    throttle,
    isInViewport,
    scrollToElement,
    copyToClipboard,
    showLoading,
    hideLoading,
    handleApiError,
    validateField,
    isValidEmail
};
