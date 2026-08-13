/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Kept for backward-compatible class names in older components
        ink: {
          50: "#fafafa",
          100: "#f5f5f5",
          200: "#e5e5e5",
          300: "#d4d4d4",
          400: "#a3a3a3",
          500: "#737373",
          600: "#525252",
          700: "#404040",
          800: "#262626",
          900: "#171717",
          950: "#0a0a0a",
        },
        accent: {
          DEFAULT: "#111111",
          soft: "#333333",
          muted: "#f5f5f5",
        },
        sand: {
          DEFAULT: "#ffffff",
          dark: "#0a0a0a",
        },
      },
      fontFamily: {
        display: ['"Manrope"', "system-ui", "Segoe UI", "sans-serif"],
        sans: ['"Manrope"', "system-ui", "Segoe UI", "sans-serif"],
        mono: ["ui-monospace", "Consolas", "monospace"],
      },
      boxShadow: {
        soft: "0 10px 30px -18px rgba(0,0,0,0.35)",
      },
    },
  },
  plugins: [],
};
