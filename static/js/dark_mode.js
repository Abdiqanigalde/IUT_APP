/**
 * Dark Mode Toggle Script for IUT Appointment System
 */

class DarkModeManager {
    constructor() {
        this.darkModeKey = 'iut_dark_mode';
        this.init();
    }

    init() {
        // Load saved preference
        const savedMode = localStorage.getItem(this.darkModeKey);
        
        // Check system preference if no saved preference
        if (savedMode === null) {
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            this.setDarkMode(prefersDark);
        } else {
            this.setDarkMode(savedMode === 'true');
        }

        // Listen for system preference changes
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
            if (localStorage.getItem(this.darkModeKey) === null) {
                this.setDarkMode(e.matches);
            }
        });

        // Setup toggle button
        this.setupToggleButton();
    }

    setDarkMode(enabled) {
        const body = document.body;
        
        if (enabled) {
            body.classList.add('dark-mode');
            localStorage.setItem(this.darkModeKey, 'true');
        } else {
            body.classList.remove('dark-mode');
            localStorage.setItem(this.darkModeKey, 'false');
        }

        // Update toggle button icon
        this.updateToggleButtonIcon();
    }

    toggle() {
        const isDarkMode = document.body.classList.contains('dark-mode');
        this.setDarkMode(!isDarkMode);
        
        // Save preference to server if user is logged in
        this.saveModeToServer(!isDarkMode);
    }

    setupToggleButton() {
        let toggleButton = document.getElementById('theme-toggle-btn');
        
        if (!toggleButton) {
            // Create toggle button if it doesn't exist
            toggleButton = document.createElement('button');
            toggleButton.id = 'theme-toggle-btn';
            toggleButton.className = 'theme-toggle';
            toggleButton.setAttribute('aria-label', 'Toggle dark mode');
            toggleButton.setAttribute('title', 'Toggle dark mode');
            document.body.appendChild(toggleButton);
        }

        toggleButton.addEventListener('click', () => this.toggle());
        this.updateToggleButtonIcon();
    }

    updateToggleButtonIcon() {
        const toggleButton = document.getElementById('theme-toggle-btn');
        if (!toggleButton) return;

        const isDarkMode = document.body.classList.contains('dark-mode');
        toggleButton.innerHTML = isDarkMode ? '☀️' : '🌙';
    }

    saveModeToServer(isDarkMode) {
        // Send preference to server via AJAX
        fetch('/api/user/theme', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': this.getCsrfToken()
            },
            body: JSON.stringify({ dark_mode: isDarkMode })
        }).catch(error => console.log('Could not save theme preference:', error));
    }

    getCsrfToken() {
        // Get CSRF token from meta tag or cookie
        const token = document.querySelector('meta[name="csrf-token"]');
        if (token) {
            return token.getAttribute('content');
        }
        
        // Fallback: get from cookie
        const cookies = document.cookie.split(';');
        for (let cookie of cookies) {
            const [name, value] = cookie.split('=');
            if (name.trim() === 'csrf_token') {
                return value.trim();
            }
        }
        
        return '';
    }
}

// Initialize dark mode manager when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.darkModeManager = new DarkModeManager();
});

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = DarkModeManager;
}
