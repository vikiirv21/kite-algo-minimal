/**
 * Arthayukti Dashboard - UI Components
 * Reusable helper functions for rendering UI elements
 */

const Components = (() => {
    /**
     * Format currency in INR
     */
    function formatCurrency(value) {
        if (value === null || value === undefined) return '—';
        const num = parseFloat(value);
        if (isNaN(num)) return '—';
        return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
    }

    /**
     * Format percentage
     */
    function formatPercentage(value) {
        if (value === null || value === undefined) return '—';
        const num = parseFloat(value);
        if (isNaN(num)) return '—';
        return `${(num * 100).toFixed(2)}%`;
    }

    /**
     * Format time (HH:MM:SS)
     */
    function formatTime(isoString) {
        if (!isoString) return '—';
        try {
            const date = new Date(isoString);
            return date.toLocaleTimeString('en-IN', { hour12: false });
        } catch {
            return '—';
        }
    }

    /**
     * Format date and time
     */
    function formatDateTime(isoString) {
        if (!isoString) return '—';
        try {
            const date = new Date(isoString);
            return date.toLocaleString('en-IN', {
                hour12: false,
                year: 'numeric',
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
            });
        } catch {
            return '—';
        }
    }

    /**
     * Get CSS class for positive/negative value
     */
    function getValueClass(value) {
        if (value === null || value === undefined) return '';
        const num = parseFloat(value);
        if (isNaN(num)) return '';
        return num >= 0 ? 'positive' : 'negative';
    }

    /**
     * Create a card element
     */
    function createCard(title, subtitle = null, content = '') {
        return `
            <div class="card">
                <div class="card-header">
                    <h3 class="card-title">${title}</h3>
                    ${subtitle ? `<span class="card-subtitle">${subtitle}</span>` : ''}
                </div>
                <div class="card-body">
                    ${content}
                </div>
            </div>
        `;
    }

    /**
     * Create a stat box
     */
    function createStatBox(label, value, valueClass = '') {
        return `
            <div class="stat-box">
                <div class="stat-label">${label}</div>
                <div class="stat-value ${valueClass}">${value}</div>
            </div>
        `;
    }

    /**
     * Create a badge
     */
    function createBadge(text, variant = 'default') {
        return `<span class="badge badge-${variant}">${text}</span>`;
    }

    /**
     * Create a table
     */
    function createTable(headers, rows) {
        const headerHtml = headers.map(h => `<th>${h}</th>`).join('');
        const rowsHtml = rows.map(row => {
            const cells = row.map(cell => `<td>${cell}</td>`).join('');
            return `<tr>${cells}</tr>`;
        }).join('');

        return `
            <table class="data-table">
                <thead>
                    <tr>${headerHtml}</tr>
                </thead>
                <tbody>
                    ${rowsHtml || '<tr><td colspan="' + headers.length + '">No data</td></tr>'}
                </tbody>
            </table>
        `;
    }

    /**
     * Create empty state message
     */
    function createEmptyState(message) {
        return `<div class="empty-state">${message}</div>`;
    }

    /**
     * Create loading indicator
     */
    function createLoader(message = 'Loading...') {
        return `<div class="loader">${message}</div>`;
    }

    // Public API
    return {
        formatCurrency,
        formatPercentage,
        formatTime,
        formatDateTime,
        getValueClass,
        createCard,
        createStatBox,
        createBadge,
        createTable,
        createEmptyState,
        createLoader,
    };
})();
