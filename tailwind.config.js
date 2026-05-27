/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./gymapp/**/templates/**/*.html",
    "./gymapp/**/*.py",
    "./static/src/js/**/*.js",
  ],
  theme: {
    extend: {
      colors: {
        // Smart Fit brand: vivid yellow on near-black.
        brand: { DEFAULT: "#F5E000", dark: "#D8C400" },
        ink: "#0B0B0B",
      },
      keyframes: {
        // Subtle fade+rise — page content + cards entrance.
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        // Brand-color pulse halo around the daily-advice card.
        "pulse-brand": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(245, 224, 0, 0.45)" },
          "50%": { boxShadow: "0 0 0 10px rgba(245, 224, 0, 0)" },
        },
        // Used for the rest timer banner sliding in.
        "slide-down": {
          "0%": { opacity: "0", transform: "translateY(-10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.35s ease-out both",
        "pulse-brand": "pulse-brand 2.2s ease-in-out infinite",
        "slide-down": "slide-down 0.25s ease-out both",
      },
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
