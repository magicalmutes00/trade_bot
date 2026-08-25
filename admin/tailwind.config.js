/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Match the Android app's dark financial palette.
        bof: {
          black: '#0B0F14',
          surface: '#121821',
          high: '#1A2230',
          border: '#232D3D',
          accent: '#4E9CFF',
          green: '#16C784',
          red: '#EA3943',
          text: '#EAF0F6',
          muted: '#8A97A8',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'monospace'],
      },
    },
  },
  plugins: [],
}
