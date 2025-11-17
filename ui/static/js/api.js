/**
 * Dashboard V2 - API Utility Module
 * Provides a clean wrapper for API calls with error handling and retry logic
 */

const API = (() => {
    // Configuration
    const config = {
        baseURL: '', // Relative to current origin
        maxRetries: 3,
        retryDelay: 1000, // Base delay in ms (will use exponential backoff)
        timeout: 10000, // Request timeout in ms
    };

    /**
     * Sleep utility for retry delays
     */
    const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

    /**
     * Main API call function with retry logic
     * @param {string} endpoint - API endpoint (e.g., '/api/engines/status')
     * @param {Object} options - Fetch options
     * @returns {Promise<Object>} - Parsed JSON response
     */
    async function api(endpoint, options = {}) {
        const url = `${config.baseURL}${endpoint}`;
        let lastError = null;

        for (let attempt = 1; attempt <= config.maxRetries; attempt++) {
            try {
                const controller = new AbortController();
                const timeoutId = setTimeout(() => controller.abort(), config.timeout);

                const response = await fetch(url, {
                    ...options,
                    signal: controller.signal,
                });

                clearTimeout(timeoutId);

                if (!response.ok) {
                    throw new Error(`API error: ${endpoint} returned ${response.status}`);
                }

                return await response.json();
            } catch (error) {
                lastError = error;
                
                // Don't retry on abort (timeout)
                if (error.name === 'AbortError') {
                    console.warn(`API timeout: ${endpoint}`);
                    break;
                }

                // Don't retry on client errors (4xx)
                if (error.message && error.message.includes('4')) {
                    break;
                }

                // Exponential backoff for retries
                if (attempt < config.maxRetries) {
                    const delay = config.retryDelay * Math.pow(2, attempt - 1);
                    console.warn(`API retry ${attempt}/${config.maxRetries} for ${endpoint} after ${delay}ms`);
                    await sleep(delay);
                } else {
                    console.error(`API failed after ${config.maxRetries} attempts: ${endpoint}`, error);
                }
            }
        }

        // All retries exhausted
        throw lastError || new Error(`API call failed: ${endpoint}`);
    }

    /**
     * GET request wrapper
     */
    async function get(endpoint, params = {}) {
        const queryString = new URLSearchParams(params).toString();
        const url = queryString ? `${endpoint}?${queryString}` : endpoint;
        return await api(url, { method: 'GET' });
    }

    /**
     * POST request wrapper
     */
    async function post(endpoint, data = {}) {
        return await api(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(data),
        });
    }

    /**
     * Configure API settings
     */
    function configure(newConfig) {
        Object.assign(config, newConfig);
    }

    // Public API
    return {
        get,
        post,
        configure,
        api, // Expose raw api function
    };
})();

// Export for ES6 modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = API;
}

// Make available globally
window.API = API;
