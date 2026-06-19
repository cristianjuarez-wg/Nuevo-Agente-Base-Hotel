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
        // Paleta Patagonia — maderas, piedra y verdes apagados (acentos editoriales)
        timber: {              // madera cálida
          50: '#f7f3ee',
          100: '#ece2d4',
          200: '#d9c3a8',
          300: '#c2a279',
          400: '#a9824f',
          500: '#8a6a3f',
          600: '#6e5332',
        },
        stone: {               // piedra / neutros cálidos para fondos
          50: '#f6f4f1',
          100: '#eceae4',
          200: '#dcd8cf',
          300: '#c3bdb0',
          400: '#a39c8c',
          500: '#827b6c',
          600: '#5f5a4e',
        },
        forest: {              // verde apagado patagónico
          50: '#eef2ef',
          100: '#d6e0d8',
          200: '#aec2b2',
          300: '#7f9d86',
          400: '#577a60',
          500: '#3d5e46',
          600: '#2e4836',
        },
        ink: '#1b2433',     // texto principal (un punto más cálido)
        slatey: '#5b6b80',  // texto secundario
        mist: '#f4f7fb',    // fondo suave (azulado)
        linen: '#f7f4ee',   // fondo suave (cálido / papel)
      },
      fontFamily: {
        // display: titulares editoriales grandes (serif fino, alto contraste)
        display: ['"Cormorant Garamond"', '"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
        serif: ['"Playfair Display"', 'Georgia', 'ui-serif', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
      },
      letterSpacing: {
        'eyebrow': '0.22em',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgb(0 0 0 / 0.06), 0 1px 2px -1px rgb(0 0 0 / 0.05)',
        'card-lg': '0 12px 30px -8px rgb(0 47 90 / 0.18), 0 4px 10px -4px rgb(0 0 0 / 0.08)',
        // sombra editorial cálida y difusa (look premium, menos "tech")
        soft: '0 18px 50px -16px rgb(46 36 22 / 0.22), 0 6px 16px -8px rgb(0 0 0 / 0.06)',
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
        // zoom lento de imágenes de fondo (efecto "Ken Burns" sutil, hero/galería)
        'slow-zoom': 'slowZoom 18s ease-out forwards',
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
        slowZoom: {
          from: { transform: 'scale(1.08)' },
          to: { transform: 'scale(1)' },
        },
      },
    },
  },
  plugins: [],
}
