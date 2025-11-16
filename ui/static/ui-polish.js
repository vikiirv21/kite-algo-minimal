/**
 * UI Polish Module
 * Adds scroll lock, refresh animations, and other UX improvements
 */

(function() {
  'use strict';

  // Scroll lock for logs viewer
  let logsAutoscroll = true;
  const logsViewer = document.getElementById('logs-viewer');
  const logsAutoscrollCheckbox = document.getElementById('logs-autoscroll');
  
  if (logsAutoscrollCheckbox) {
    logsAutoscrollCheckbox.addEventListener('change', (e) => {
      logsAutoscroll = e.target.checked;
      if (logsAutoscroll && logsViewer) {
        scrollLogsToBottom();
      }
    });
  }

  function scrollLogsToBottom() {
    if (logsViewer && logsAutoscroll) {
      logsViewer.scrollTop = logsViewer.scrollHeight;
    }
  }

  // Logs controls
  const logsClearBtn = document.getElementById('logs-clear');
  const logsRefreshBtn = document.getElementById('logs-refresh');
  const logsStream = document.getElementById('logs-stream');

  if (logsClearBtn) {
    logsClearBtn.addEventListener('click', () => {
      if (logsStream) {
        logsStream.textContent = 'Logs cleared. Refreshing...';
      }
      // Trigger a refresh after clearing
      if (typeof window.refreshLogs === 'function') {
        setTimeout(() => window.refreshLogs(), 500);
      }
    });
  }

  if (logsRefreshBtn) {
    logsRefreshBtn.addEventListener('click', () => {
      addRefreshAnimation(logsRefreshBtn);
      if (typeof window.refreshLogs === 'function') {
        window.refreshLogs();
      }
    });
  }

  // Add refresh animation to button
  function addRefreshAnimation(button) {
    button.classList.add('refreshing');
    button.style.opacity = '0.6';
    button.style.transform = 'rotate(360deg)';
    button.style.transition = 'transform 0.5s ease, opacity 0.3s ease';
    
    setTimeout(() => {
      button.classList.remove('refreshing');
      button.style.opacity = '1';
      button.style.transform = 'rotate(0deg)';
    }, 500);
  }

  // Color-coded log levels
  function applyLogLevelColors() {
    if (!logsStream) return;
    
    const logText = logsStream.textContent;
    const lines = logText.split('\n');
    const coloredLines = lines.map(line => {
      if (line.includes('[ERROR]') || line.includes('ERROR')) {
        return `<span class="log-line-error">${escapeHtml(line)}</span>`;
      } else if (line.includes('[WARN]') || line.includes('WARNING')) {
        return `<span class="log-line-warn">${escapeHtml(line)}</span>`;
      } else if (line.includes('[INFO]')) {
        return `<span class="log-line-info">${escapeHtml(line)}</span>`;
      } else if (line.includes('[DEBUG]')) {
        return `<span class="log-line-debug">${escapeHtml(line)}</span>`;
      }
      return escapeHtml(line);
    });
    
    logsStream.innerHTML = coloredLines.join('\n');
    scrollLogsToBottom();
  }

  // Watch for log updates
  if (logsStream) {
    const observer = new MutationObserver(() => {
      applyLogLevelColors();
    });
    
    observer.observe(logsStream, {
      childList: true,
      characterData: true,
      subtree: true
    });
  }

  // Escape HTML helper
  function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }

  // Smooth scroll behavior for page navigation
  document.addEventListener('click', (e) => {
    const link = e.target.closest('a[href^="#"]');
    if (link) {
      e.preventDefault();
      const targetId = link.getAttribute('href').slice(1);
      const target = document.getElementById(targetId);
      if (target) {
        target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }
  });

  // Add loading state to cards during refresh
  window.addCardLoadingState = function(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;
    
    card.style.opacity = '0.6';
    card.style.pointerEvents = 'none';
    
    setTimeout(() => {
      card.style.opacity = '1';
      card.style.pointerEvents = 'auto';
    }, 300);
  };

  // Keyboard shortcuts
  document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + R to refresh logs
    if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
      if (document.querySelector('.tab[data-tab="logs"]').classList.contains('active')) {
        e.preventDefault();
        if (logsRefreshBtn) {
          logsRefreshBtn.click();
        }
      }
    }
    
    // Escape to clear log search/filter
    if (e.key === 'Escape') {
      const activeTab = document.querySelector('.tab.active');
      if (activeTab && activeTab.dataset.tab === 'logs') {
        // Clear any active log filters
        document.querySelectorAll('.logs-tab').forEach(tab => {
          if (!tab.classList.contains('active')) {
            tab.classList.remove('active');
          }
        });
      }
    }
  });

  // Toast notification system
  window.showToast = function(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toast.style.cssText = `
      position: fixed;
      bottom: 24px;
      right: 24px;
      padding: 12px 20px;
      background: ${type === 'success' ? '#22c55e' : type === 'error' ? '#ef4444' : '#6366f1'};
      color: white;
      border-radius: 8px;
      box-shadow: 0 4px 16px rgba(0, 0, 0, 0.3);
      font-size: 14px;
      font-weight: 500;
      z-index: 10000;
      animation: slideIn 0.3s ease;
    `;
    
    document.body.appendChild(toast);
    
    setTimeout(() => {
      toast.style.animation = 'slideOut 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, 3000);
  };

  // Add CSS animations
  const style = document.createElement('style');
  style.textContent = `
    @keyframes slideIn {
      from {
        transform: translateX(400px);
        opacity: 0;
      }
      to {
        transform: translateX(0);
        opacity: 1;
      }
    }
    
    @keyframes slideOut {
      from {
        transform: translateX(0);
        opacity: 1;
      }
      to {
        transform: translateX(400px);
        opacity: 0;
      }
    }
    
    .refreshing {
      pointer-events: none;
    }
  `;
  document.head.appendChild(style);

  // Initialize on load
  window.addEventListener('load', () => {
    applyLogLevelColors();
    console.log('UI Polish module loaded');
  });

  // Export functions for use in main dashboard.js
  window.uiPolish = {
    scrollLogsToBottom,
    addRefreshAnimation,
    applyLogLevelColors,
  };

})();
