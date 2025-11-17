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
        background: '#0a0e1a',
        surface: '#121825',
        'surface-light': '#1a2332',
        border: '#2a3447',
        primary: '#3b82f6',
        'primary-dark': '#2563eb',
        accent: '#8b5cf6',
        positive: '#10b981',
        negative: '#ef4444',
        warning: '#f59e0b',
        muted: '#6b7280',
        'text-primary': '#f3f4f6',
        'text-secondary': '#9ca3af',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
      },
    },
  },
  plugins: [],
}
