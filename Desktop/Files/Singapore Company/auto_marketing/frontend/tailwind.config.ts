import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        apple: {
          text: "#1d1d1f",
          secondary: "#86868b",
          bg: "#f5f5f7",
          blue: "#0071e3",
          "blue-hover": "#0077ed",
          card: "#ffffff",
          border: "#d2d2d7",
        },
      },
      fontFamily: {
        sans: [
          "-apple-system",
          "BlinkMacSystemFont",
          '"SF Pro Display"',
          '"SF Pro Text"',
          '"Segoe UI"',
          "Roboto",
          "Helvetica",
          "Arial",
          "sans-serif",
        ],
      },
      borderRadius: {
        apple: "12px",
        "apple-sm": "8px",
      },
      boxShadow: {
        apple: "0 2px 10px rgba(0,0,0,0.04)",
        "apple-lg": "0 4px 24px rgba(0,0,0,0.08)",
      },
    },
  },
  plugins: [],
};

export default config;
