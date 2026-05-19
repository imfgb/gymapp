/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./gymapp/**/templates/**/*.html",
    "./gymapp/**/*.py",
    "./static/src/js/**/*.js",
  ],
  theme: {
    extend: {},
  },
  plugins: [require("@tailwindcss/forms")],
};
