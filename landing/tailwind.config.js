/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Marca Hampton by Hilton — azul Hilton + neutros cálidos
        hilton: {
          DEFAULT: '#005aa9', // Hilton blue
          50: '#e8f2fb',
          100: '#c5dcf5',
          200: '#9ec4ee',
          300: '#75ace6',
          400: '#4d95de',
          500: '#2d7edc',
          600: '#005aa9',
          700: '#004d90',
          800: '#003f77',
          900: '#002f5a',
        },
        // Acento cálido (madera / patagonia)
        sand: {
          DEFAULT: '#c89b6a',
          50: '#faf6f0',
          100: '#f0e4d2',
          200: '#e3cba9',
          300: '#d4b184',
          400: '#c89b6a',
          500: '#b8854f',
          600: '#9c6e3f',
        },
        ink: '#16243a',     // texto principal
        slatey: '#5b6b80',  // texto secundario
        mist: '#f4f7fb',    // fondo suave
      },
      fontFamily: {
        serif: ['"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
        'card-lg': '0 12px 30px -8px rgb(0 47 90 / 0.18), 0 4px 10px -4px rgb(0 0 0 / 0.08)',
        widget: '0 16px 40px -8px rgb(0 47 90 / 0.30)',
      },
      borderRadius: {
        xl: '0.875rem',
        '2xl': '1.25rem',
      },
      animation: {
        'fade-in': 'fadeIn 0.4s ease-out',
        'slide-up': 'slideUp 0.45s ease-out both',
        'slide-up-widget': 'slideUpWidget 0.28s ease-out',
        'pulse-dot': 'pulseDot 1.4s ease-in-out infinite',
      },
      keyframes: {
        fadeIn: {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        slideUp: {
          from: { opacity: '0', transform: 'translateY(20px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        slideUpWidget: {
          from: { opacity: '0', transform: 'translateY(16px) scale(0.98)' },
          to: { opacity: '1', transform: 'translateY(0) scale(1)' },
        },
        pulseDot: {
          '0%, 80%, 100%': { transform: 'scale(0.6)', opacity: '0.4' },
          '40%': { transform: 'scale(1)', opacity: '1' },
        },
      },
    },
  },
  plugins: [],
}
