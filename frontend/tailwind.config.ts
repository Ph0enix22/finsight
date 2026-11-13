import type { Config } from 'tailwindcss'

export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      fontSize: {
        hero: ['40px', { lineHeight: '1.1' }],
        h1: ['28px', { lineHeight: '1.2' }],
        h2: ['20px', { lineHeight: '1.3' }],
        body: ['16px', { lineHeight: '1.5' }],
        small: ['14px', { lineHeight: '1.4' }],
        micro: ['12px', { lineHeight: '1.3' }],
      },
      borderRadius: {
        card: '16px',
        input: '12px',
      },
    },
  },
} satisfies Config
