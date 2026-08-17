/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ['class', '[data-theme="dark"]'],
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Katta monitor va televizor uchun qo'shimcha nuqtalar
      screens: {
        '3xl': '1920px',
        '4xl': '2560px',
      },
      colors: {
        bg: 'hsl(var(--bg))',
        surface: 'hsl(var(--surface))',
        'surface-2': 'hsl(var(--surface-2))',
        border: 'hsl(var(--border))',
        text: 'hsl(var(--text))',
        muted: 'hsl(var(--muted))',
        accent: 'hsl(var(--accent))',
        'accent-soft': 'hsl(var(--accent-soft))',
        good: 'hsl(var(--good))',
        warn: 'hsl(var(--warn))',
        bad: 'hsl(var(--bad))',
      },
      fontFamily: {
        sans: [
          '-apple-system',
          'BlinkMacSystemFont',
          'SF Pro Text',
          'SF Pro Display',
          'Inter var',
          'Inter',
          'system-ui',
          'sans-serif',
        ],
        mono: ['SF Mono', 'JetBrains Mono', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem', letterSpacing: '0.01em' }],
      },
      // iOS — yirikroq radiuslar
      borderRadius: {
        sm: '0.5rem',
        md: '0.75rem',
        lg: '1rem',
        xl: '1.25rem',
        '2xl': '1.5rem',
      },
      // Yumshoq, ko'p qatlamli soyalar (chegaraning o'rniga)
      boxShadow: {
        xs: '0 1px 2px hsl(var(--shadow) / 0.04)',
        soft: '0 1px 2px hsl(var(--shadow) / 0.04), 0 2px 8px hsl(var(--shadow) / 0.04)',
        lift: '0 2px 4px hsl(var(--shadow) / 0.04), 0 8px 24px hsl(var(--shadow) / 0.07)',
        pop: '0 4px 8px hsl(var(--shadow) / 0.05), 0 16px 40px hsl(var(--shadow) / 0.1)',
        inner: 'inset 0 1px 2px hsl(var(--shadow) / 0.05)',
      },
      // iOS spring-ga yaqin egri chiziq
      transitionTimingFunction: {
        ios: 'cubic-bezier(0.32, 0.72, 0, 1)',
      },
      transitionDuration: {
        250: '250ms',
        400: '400ms',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scale-in': {
          from: { opacity: '0', transform: 'scale(0.97)' },
          to: { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 0.4s cubic-bezier(0.32, 0.72, 0, 1) both',
        'scale-in': 'scale-in 0.25s cubic-bezier(0.32, 0.72, 0, 1) both',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
}
