/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          base: "#0F1419",
          surface: "#1A2332",
          raised: "#222E40",
          hover: "#2A3849",
        },
        text: {
          primary: "#E8EDF2",
          secondary: "#8B98A9",
          tertiary: "#5A6678",
        },
        signal: {
          mint: "#3DDC97",
          mintDim: "#2A9D6F",
          amber: "#F2A33C",
          red: "#E0556F",
          blue: "#5B9BD5",
        },
        border: {
          subtle: "#263244",
          DEFAULT: "#324158",
        },
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["IBM Plex Mono", "ui-monospace", "monospace"],
      },
      borderRadius: {
        sm: "4px",
        DEFAULT: "6px",
        lg: "10px",
      },
    },
  },
  plugins: [],
};
