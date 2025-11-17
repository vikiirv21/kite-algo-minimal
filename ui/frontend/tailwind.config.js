/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        // Dark theme backgrounds
        background: '#0a0e1a',
        surface: '#121825',
        'surface-light': '#1a2332',
        'surface-elevated': '#1f2937',
        border: '#2a3447',
        
        // Primary colors
        primary: '#3b82f6',
        'primary-dark': '#2563eb',
        'primary-light': '#60a5fa',
        
        // Accent & secondary
        accent: '#8b5cf6',
        'accent-light': '#a78bfa',
        secondary: '#6366f1',
        
        // Status colors
        positive: '#10b981',
        'positive-dark': '#059669',
        negative: '#ef4444',
        'negative-dark': '#dc2626',
        warning: '#f59e0b',
        'warning-dark': '#d97706',
        info: '#06b6d4',
        
        // Text colors
        'text-primary': '#f3f4f6',
        'text-secondary': '#9ca3af',
        'text-muted': '#6b7280',
        muted: '#6b7280',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Consolas', 'Monaco', 'monospace'],
      },
      boxShadow: {
        'card': '0 2px 8px rgba(0, 0, 0, 0.3)',
        'card-hover': '0 4px 12px rgba(0, 0, 0, 0.4)',
        'elevated': '0 8px 24px rgba(0, 0, 0, 0.5)',
      },
      animation: {
        'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
      },
    },
  },
  plugins: [],
}
