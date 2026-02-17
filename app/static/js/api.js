// API interaction functions for AI Email Dashboard

// Base API configuration
const API_BASE = '/api';

// Default headers
const DEFAULT_HEADERS = {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest'
};

// API request wrapper
async function apiRequest(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const config = {
        headers: { ...DEFAULT_HEADERS },
        ...options
    };
    
    try {
        const response = await fetch(url, config);
        const data = await response.json();
        
        if (!response.ok) {
            throw new Error(data.message || `HTTP error! status: ${response.status}`);
        }
        
        return data;
    } catch (error) {
        console.error('API Request Error:', error);
        throw error;
    }
}

// GET request
async function get(endpoint, params = {}) {
    const queryString = new URLSearchParams(params).toString();
    const url = queryString ? `${endpoint}?${queryString}` : endpoint;
    
    return apiRequest(url, {
        method: 'GET'
    });
}

// POST request
async function post(endpoint, data = {}) {
    return apiRequest(endpoint, {
        method: 'POST',
        body: JSON.stringify(data)
    });
}

// PUT request
async function put(endpoint, data = {}) {
    return apiRequest(endpoint, {
        method: 'PUT',
        body: JSON.stringify(data)
    });
}

// DELETE request
async function del(endpoint) {
    return apiRequest(endpoint, {
        method: 'DELETE'
    });
}

// Email API functions
const EmailAPI = {
    // Get emails
    async getEmails(params = {}) {
        return get('/emails', params);
    },
    
    // Get single email
    async getEmail(emailId) {
        return get(`/emails/${emailId}`);
    },
    
    // Generate email with AI
    async generateEmail(data) {
        return post('/emails/generate', data);
    },
    
    // Classify email
    async classifyEmail(emailId) {
        return post(`/emails/${emailId}/classify`);
    },
    
    // Schedule follow-up
    async scheduleFollowUp(emailId, data) {
        return post(`/emails/${emailId}/follow-up`, data);
    },
    
    // Send email
    async sendEmail(data) {
        const form = new FormData();
        Object.keys(data).forEach(key => {
            form.append(key, data[key]);
        });
        
        return fetch('/email/send', {
            method: 'POST',
            body: form
        });
    },
    
    // Save draft
    async saveDraft(data) {
        const form = new FormData();
        Object.keys(data).forEach(key => {
            form.append(key, data[key]);
        });
        
        return fetch('/email/draft', {
            method: 'POST',
            body: form
        });
    },
    
    // Mark as read
    async markAsRead(emailId) {
        return put(`/emails/${emailId}`, { is_read: true });
    },
    
    // Toggle star
    async toggleStar(emailId) {
        return put(`/emails/${emailId}`, { toggle_star: true });
    },
    
    // Delete email
    async deleteEmail(emailId) {
        return del(`/emails/${emailId}`);
    }
};

// Automation API functions
const AutomationAPI = {
    // Get automation rules
    async getRules() {
        return get('/automation/rules');
    },
    
    // Create automation rule
    async createRule(data) {
        return post('/automation/rules', data);
    },
    
    // Update automation rule
    async updateRule(ruleId, data) {
        return put(`/automation/rules/${ruleId}`, data);
    },
    
    // Delete automation rule
    async deleteRule(ruleId) {
        return del(`/automation/rules/${ruleId}`);
    },
    
    // Toggle rule active status
    async toggleRule(ruleId) {
        return post(`/automation/rules/${ruleId}/toggle`);
    },
    
    // Get follow-ups
    async getFollowUps() {
        return get('/follow-ups');
    },
    
    // Create follow-up
    async createFollowUp(data) {
        return post('/follow-ups', data);
    },
    
    // Cancel follow-up
    async cancelFollowUp(followUpId) {
        return del(`/follow-ups/${followUpId}`);
    }
};

// Gmail API functions
const GmailAPI = {
    // Get authorization URL
    async getAuthUrl() {
        return get('/gmail/auth-url');
    },
    
    // Handle OAuth callback
    async handleCallback(code, state) {
        return post('/gmail/callback', { code, state });
    },
    
    // Disconnect Gmail
    async disconnect() {
        return post('/gmail/disconnect');
    },
    
    // Sync emails
    async syncEmails() {
        return post('/gmail/sync');
    },
    
    // Get labels
    async getLabels() {
        return get('/gmail/labels');
    },
    
    // Create label
    async createLabel(data) {
        return post('/gmail/labels', data);
    }
};

// User API functions
const UserAPI = {
    // Get user profile
    async getProfile() {
        return get('/user/profile');
    },
    
    // Update profile
    async updateProfile(data) {
        return put('/user/profile', data);
    },
    
    // Update preferences
    async updatePreferences(data) {
        return put('/user/preferences', data);
    },
    
    // Change password
    async changePassword(data) {
        return post('/user/change-password', data);
    },
    
    // Delete account
    async deleteAccount() {
        return del('/user/account');
    }
};

// Analytics API functions
const AnalyticsAPI = {
    // Get email statistics
    async getEmailStats(params = {}) {
        return get('/analytics/emails', params);
    },
    
    // Get automation stats
    async getAutomationStats(params = {}) {
        return get('/analytics/automation', params);
    },
    
    // Get usage metrics
    async getUsageMetrics(params = {}) {
        return get('/analytics/usage', params);
    }
};

// Utility functions for API interactions
const APIUtils = {
    // Handle API responses with loading states
    async withLoading(element, apiCall, loadingText = 'Loading...') {
        const originalContent = element.innerHTML;
        AppUtils.showLoading(element, loadingText);
        
        try {
            const result = await apiCall();
            AppUtils.hideLoading(element);
            return result;
        } catch (error) {
            AppUtils.hideLoading(element);
            AppUtils.handleApiError(error);
            throw error;
        }
    },
    
    // Batch API requests
    async batch(requests) {
        try {
            const results = await Promise.allSettled(requests);
            return results.map(result => 
                result.status === 'fulfilled' ? result.value : null
            );
        } catch (error) {
            console.error('Batch request error:', error);
            throw error;
        }
    },
    
    // Paginated request helper
    async paginated(endpoint, params = {}, accumulator = []) {
        const response = await get(endpoint, { ...params, page: 1 });
        accumulator.push(...response.data);
        
        if (response.next_page) {
            return this.paginated(endpoint, { ...params, page: response.next_page }, accumulator);
        }
        
        return accumulator;
    },
    
    // Retry mechanism
    async retry(apiCall, maxRetries = 3, delay = 1000) {
        let lastError;
        
        for (let i = 0; i < maxRetries; i++) {
            try {
                return await apiCall();
            } catch (error) {
                lastError = error;
                
                if (i < maxRetries - 1) {
                    await new Promise(resolve => setTimeout(resolve, delay * Math.pow(2, i)));
                }
            }
        }
        
        throw lastError;
    },
    
    // Cache API responses
    cache: new Map(),
    
    async cached(key, apiCall, ttl = 300000) { // 5 minutes default TTL
        const cached = this.cache.get(key);
        
        if (cached && Date.now() - cached.timestamp < ttl) {
            return cached.data;
        }
        
        try {
            const data = await apiCall();
            this.cache.set(key, {
                data,
                timestamp: Date.now()
            });
            return data;
        } catch (error) {
            if (cached) {
                return cached.data; // Return stale data if available
            }
            throw error;
        }
    },
    
    // Clear cache
    clearCache(pattern = null) {
        if (pattern) {
            for (const key of this.cache.keys()) {
                if (key.includes(pattern)) {
                    this.cache.delete(key);
                }
            }
        } else {
            this.cache.clear();
        }
    }
};

// Export API modules
window.API = {
    Email: EmailAPI,
    Automation: AutomationAPI,
    Gmail: GmailAPI,
    User: UserAPI,
    Analytics: AnalyticsAPI,
    Utils: APIUtils,
    get,
    post,
    put,
    del
};

// Initialize API interceptors
document.addEventListener('DOMContentLoaded', function() {
    // Add CSRF token to all requests if available
    const csrfToken = document.querySelector('meta[name="csrf-token"]');
    if (csrfToken) {
        DEFAULT_HEADERS['X-CSRF-Token'] = csrfToken.getAttribute('content');
    }
    
    // Add request interceptor for logging
    const originalFetch = window.fetch;
    window.fetch = async function(...args) {
        const [url, options] = args;
        
        // Log API requests in development
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.log('API Request:', url, options);
        }
        
        const response = await originalFetch.apply(this, args);
        
        // Log responses in development
        if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
            console.log('API Response:', response.status, response);
        }
        
        return response;
    };
});