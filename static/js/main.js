// WeatherAvatar - Main JavaScript File
// Handles common functionality and interactions

/**
 * Global application state and configuration
 */
const WeatherAvatar = {
    // Application configuration
    config: {
        apiEndpoints: {
            weather: '/api/weather/',
            avatar: '/api/avatar/'
        },
        animations: {
            duration: 300,
            easing: 'ease-in-out'
        }
    },
    
    // Application state
    state: {
        currentLocation: null,
        currentWeather: null,
        selectedAvatar: null,
        theme: 'dark'
    },
    
    // Initialize the application
    init() {
        console.log('WeatherAvatar initializing...');
        this.bindEvents();
        this.initializeTheme();
        this.setupFeatherIcons();
    },
    
    // Bind global event listeners
    bindEvents() {
        document.addEventListener('DOMContentLoaded', () => {
            console.log('DOM loaded, WeatherAvatar ready');
        });
        
        // Handle form submissions with loading states
        document.addEventListener('submit', this.handleFormSubmit.bind(this));
        
        // Handle button clicks with feedback
        document.addEventListener('click', this.handleButtonClick.bind(this));
    },
    
    // Initialize theme system
    initializeTheme() {
        const savedTheme = localStorage.getItem('weatheravatar-theme') || 'dark';
        this.setTheme(savedTheme);
    },
    
    // Set application theme
    setTheme(theme) {
        this.state.theme = theme;
        document.documentElement.setAttribute('data-bs-theme', theme);
        localStorage.setItem('weatheravatar-theme', theme);
        
        // Update theme icon
        const themeIcon = document.getElementById('theme-icon');
        if (themeIcon) {
            themeIcon.setAttribute('data-feather', theme === 'dark' ? 'sun' : 'moon');
            feather.replace();
        }
    },
    
    // Toggle between light and dark themes
    toggleTheme() {
        const newTheme = this.state.theme === 'dark' ? 'light' : 'dark';
        this.setTheme(newTheme);
    },
    
    // Setup Feather Icons
    setupFeatherIcons() {
        if (typeof feather !== 'undefined') {
            feather.replace();
        }
    },
    
    // Handle form submissions with loading states
    handleFormSubmit(event) {
        const form = event.target;
        if (form.tagName !== 'FORM') return;
        
        const submitButton = form.querySelector('button[type="submit"]');
        if (submitButton) {
            this.setButtonLoading(submitButton, true);
            
            // Reset loading state after form submission
            setTimeout(() => {
                this.setButtonLoading(submitButton, false);
            }, 2000);
        }
    },
    
    // Handle button clicks with visual feedback
    handleButtonClick(event) {
        const button = event.target.closest('button');
        if (!button) return;
        
        // Add click animation
        button.style.transform = 'scale(0.95)';
        setTimeout(() => {
            button.style.transform = '';
        }, 150);
    },
    
    // Set button loading state
    setButtonLoading(button, isLoading) {
        if (isLoading) {
            button.setAttribute('data-original-text', button.innerHTML);
            button.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status"></span>Loading...';
            button.disabled = true;
        } else {
            const originalText = button.getAttribute('data-original-text');
            if (originalText) {
                button.innerHTML = originalText;
                button.removeAttribute('data-original-text');
            }
            button.disabled = false;
        }
    },
    
    // Show notification to user
    showNotification(message, type = 'info', duration = 5000) {
        const alertContainer = document.getElementById('alert-container') || this.createAlertContainer();
        
        const alertElement = document.createElement('div');
        alertElement.className = `alert alert-${type} alert-dismissible fade show`;
        alertElement.role = 'alert';
        alertElement.innerHTML = `
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        `;
        
        alertContainer.appendChild(alertElement);
        
        // Auto-dismiss after duration
        setTimeout(() => {
            if (alertElement.parentNode) {
                alertElement.remove();
            }
        }, duration);
        
        return alertElement;
    },
    
    // Create alert container if it doesn't exist
    createAlertContainer() {
        const container = document.createElement('div');
        container.id = 'alert-container';
        container.className = 'position-fixed top-0 end-0 p-3';
        container.style.zIndex = '9999';
        document.body.appendChild(container);
        return container;
    },
    
    // Utility function to make API calls
    async apiCall(url, options = {}) {
        const defaultOptions = {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            }
        };
        
        try {
            const response = await fetch(url, { ...defaultOptions, ...options });
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            return await response.json();
        } catch (error) {
            console.error('API call failed:', error);
            this.showNotification(`Error: ${error.message}`, 'danger');
            throw error;
        }
    },
    
    // Get user's location
    async getUserLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject(new Error('Geolocation is not supported by this browser'));
                return;
            }
            
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    const location = {
                        latitude: position.coords.latitude,
                        longitude: position.coords.longitude
                    };
                    this.state.currentLocation = location;
                    resolve(location);
                },
                (error) => {
                    console.error('Geolocation error:', error);
                    reject(error);
                },
                {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000 // 5 minutes
                }
            );
        });
    },
    
    // Format date for display
    formatDate(date, options = {}) {
        const defaultOptions = {
            year: 'numeric',
            month: 'long',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        };
        
        return new Intl.DateTimeFormat('en-US', { ...defaultOptions, ...options }).format(new Date(date));
    },
    
    // Debounce function for search inputs
    debounce(func, wait) {
        let timeout;
        return function executedFunction(...args) {
            const later = () => {
                clearTimeout(timeout);
                func(...args);
            };
            clearTimeout(timeout);
            timeout = setTimeout(later, wait);
        };
    }
};

// Global theme toggle function (called from template)
function toggleTheme() {
    WeatherAvatar.toggleTheme();
}

// Initialize application when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => WeatherAvatar.init());
} else {
    WeatherAvatar.init();
}

// Make WeatherAvatar globally available for debugging and external access
window.WeatherAvatar = WeatherAvatar;
