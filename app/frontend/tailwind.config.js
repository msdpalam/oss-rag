/** @type {import('tailwindcss').Config} */
import typography from '@tailwindcss/typography';

export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      typography: {
        DEFAULT: {
          css: {
            // Remove max-width — the chat bubble already constrains width
            maxWidth: 'none',
            // Tighter vertical rhythm for a chat context
            p:  { marginTop: '0.4em', marginBottom: '0.4em' },
            'ul, ol': { marginTop: '0.4em', marginBottom: '0.4em' },
            li: { marginTop: '0.15em', marginBottom: '0.15em' },
            pre: { marginTop: '0.6em', marginBottom: '0.6em', padding: 0, background: 'none' },
            'h1, h2, h3, h4': { marginTop: '0.75em', marginBottom: '0.3em' },
            // Keep inline code subtle
            'code::before': { content: '""' },
            'code::after':  { content: '""' },
          },
        },
      },
    },
  },
  plugins: [typography],
};
