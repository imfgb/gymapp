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
    },
  },
  plugins: [require("@tailwindcss/forms")],
};
