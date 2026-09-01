/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: { DEFAULT: 'var(--primary)', light: 'var(--primary-light)' },
        'accent-green': 'var(--accent-green)',
        'accent-purple': 'var(--accent-purple)',
        'accent-coral': 'var(--accent-coral)',
        background: 'var(--background)',
        surface: { DEFAULT: 'var(--surface)', alt: 'var(--surface-alt)' },
        text: { DEFAULT: 'var(--text)', secondary: 'var(--text-secondary)' },
        border: 'var(--border)',
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'Consolas', 'monospace'],
      },
    },
  },
  plugins: [],
}


