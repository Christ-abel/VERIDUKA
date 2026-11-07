/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#14241c",
        paper: "#efe7d8",
        card: "#f7f3ea",
        line: "#ddd4c4",
        signal: "#1c7a45",
        deep: "#10281d",
        noise: "#b4332a",
        caution: "#a56b12",
      },
      fontFamily: {
        sans: ["Outfit", "system-ui", "sans-serif"],
        display: ["Fraunces", "Georgia", "serif"],
      },
      boxShadow: {
        card: "0 1px 0 rgba(20,36,28,0.05), 0 18px 40px rgba(20,36,28,0.06)",
      },
    },
  },
  plugins: [],
};
