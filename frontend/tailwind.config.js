/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fintech: {
          bg: '#F5F7FA',
          surface: '#FFFFFF',
          'surface-subtle': '#F8FAFC',
          sidebar: '#111827',
          'sidebar-hover': '#1F2937',
          'sidebar-active': '#1E293B',
          border: '#E2E8F0',
          'border-strong': '#CBD5E1',
          'text-primary': '#0F172A',
          'text-secondary': '#64748B',
          'text-muted': '#94A3B8',
          primary: '#10B981',
          'primary-hover': '#059669',
          'primary-soft': '#ECFDF5',
          success: '#10B981',
          'success-soft': '#ECFDF5',
          warning: '#F59E0B',
          'warning-soft': '#FEF3C7',
          danger: '#EF4444',
          'danger-soft': '#FEE2E2',
          info: '#3B82F6',
          'info-soft': '#EFF6FF',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
      borderRadius: {
        'fintech': '8px',
        'fintech-lg': '10px',
        'fintech-sm': '6px',
      },
      boxShadow: {
        'fintech-card': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'fintech-dropdown': '0 4px 6px -1px rgba(0, 0, 0, 0.07), 0 2px 4px -1px rgba(0, 0, 0, 0.04)',
      },
    },
  },
  plugins: [],
}


