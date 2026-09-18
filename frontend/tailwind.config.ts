import type { Config } from "tailwindcss";
import tailwindcssAnimate from "tailwindcss-animate";

const config: Config = {
  darkMode: ["class"],
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: { ink: "#202126", paper: "#f7f7f5", brandred: "#e30613", brandblue: "#0b469d" },
      fontFamily: {
        display: ["var(--font-brand)"],
        sans: ["var(--font-sans)"],
      },
    },
  },
  plugins: [tailwindcssAnimate],
};
export default config;
