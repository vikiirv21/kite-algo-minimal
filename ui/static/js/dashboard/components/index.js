/**
 * Components - Reusable UI component builders
 */

/**
 * Create a card element
 */
export function createCard(title, subtitle = null, content = null) {
  const card = document.createElement('div');
  card.className = 'card';
  
  const header = document.createElement('div');
  header.className = 'card-header';
  
  const titleEl = document.createElement('h2');
  titleEl.className = 'card-title';
  titleEl.textContent = title;
  header.appendChild(titleEl);
  
  if (subtitle) {
    const subtitleEl = document.createElement('span');
    subtitleEl.className = 'badge badge-muted';
    subtitleEl.textContent = subtitle;
    header.appendChild(subtitleEl);
  }
  
  card.appendChild(header);
  
  if (content) {
    const body = document.createElement('div');
    body.className = 'card-body';
    if (typeof content === 'string') {
      body.innerHTML = content;
    } else {
      body.appendChild(content);
    }
    card.appendChild(body);
  }
  
  return card;
}

/**
 * Create a table element
 */
export function createTable(headers, rows) {
  const table = document.createElement('table');
  
  const thead = document.createElement('thead');
  const headerRow = document.createElement('tr');
  headers.forEach(header => {
    const th = document.createElement('th');
    th.textContent = header;
    headerRow.appendChild(th);
  });
  thead.appendChild(headerRow);
  table.appendChild(thead);
  
  const tbody = document.createElement('tbody');
  if (rows.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = headers.length;
    td.className = 'text-center text-muted text-sm';
    td.textContent = 'No data available';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach(row => {
      const tr = document.createElement('tr');
      row.forEach(cell => {
        const td = document.createElement('td');
        if (typeof cell === 'object' && cell.html) {
          td.innerHTML = cell.html;
        } else {
          td.textContent = cell;
        }
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
  }
  table.appendChild(tbody);
  
  return table;
}

/**
 * Create a badge element
 */
export function createBadge(label, variant = 'muted') {
  const badge = document.createElement('span');
  badge.className = `badge badge-${variant}`;
  badge.textContent = label;
  return badge;
}

/**
 * Create skeleton loading lines
 */
export function createSkeletonLines(count) {
  const container = document.createElement('div');
  for (let i = 0; i < count; i++) {
    const line = document.createElement('div');
    line.className = 'skeleton skeleton-line';
    container.appendChild(line);
  }
  return container;
}

/**
 * Create a metric row
 */
export function createMetricRow(label, value) {
  const row = document.createElement('div');
  row.className = 'metric-row';
  
  const labelEl = document.createElement('span');
  labelEl.className = 'metric-label';
  labelEl.textContent = label;
  
  const valueEl = document.createElement('span');
  valueEl.className = 'metric-value';
  valueEl.textContent = value;
  
  row.appendChild(labelEl);
  row.appendChild(valueEl);
  
  return row;
}

/**
 * Format currency (INR)
 */
export function formatCurrency(value, decimals = 2) {
  if (value === null || value === undefined || isNaN(value)) return '—';
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

/**
 * Format number
 */
export function formatNumber(value, decimals = 2) {
  if (value === null || value === undefined || isNaN(value)) return '—';
  return Number(value).toFixed(decimals);
}

/**
 * Format percentage
 */
export function formatPercent(value, decimals = 2) {
  if (value === null || value === undefined || isNaN(value)) return '—';
  return formatNumber(value, decimals) + '%';
}

/**
 * Format time (HH:MM:SS)
 */
export function formatTime(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-IN', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit',
      timeZone: 'Asia/Kolkata'
    });
  } catch (error) {
    return '—';
  }
}

/**
 * Format short time (HH:MM)
 */
export function formatShortTime(isoString) {
  if (!isoString) return '—';
  try {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-IN', { 
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: 'Asia/Kolkata'
    });
  } catch (error) {
    return '—';
  }
}
