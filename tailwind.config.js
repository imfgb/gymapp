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
        // GymApp brand: indigo accent on a dark slate. `brand` backs primary
        // buttons/accents (use text-white on it); `ink` is the dark nav/bg.
        brand: { DEFAULT: "#4F46E5", dark: "#4338CA" },
        ink: "#0F172A",
      },
      keyframes: {
        // Subtle fade+rise — page content + cards entrance.
        "fade-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        // Brand-color pulse halo around the daily-advice card.
        "pulse-brand": {
          "0%, 100%": { boxShadow: "0 0 0 0 rgba(79, 70, 229, 0.45)" },
          "50%": { boxShadow: "0 0 0 10px rgba(79, 70, 229, 0)" },
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
