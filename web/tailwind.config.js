/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)", panel: "var(--panel)", raised: "var(--raised)", rule: "var(--rule)",
        fg: "var(--fg)", muted: "var(--muted)", model: "var(--model)", market: "var(--market)",
        pos: "var(--pos)", neg: "var(--neg)", warn: "var(--warn)",
      },
      fontFamily: { sans: ["Archivo", "system-ui", "sans-serif"] },
    },
  },
  plugins: [],
};
