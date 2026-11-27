import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/features/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        paper: {
          DEFAULT: "#F8F6F1",
          elevated: "#FFFFFF",
          subtle: "#F1EDE5",
          wash: "#E8E2D7",
        },
        ink: {
          DEFAULT: "#141311",
          secondary: "#57524B",
          muted: "#8C857B",
          faint: "#C8C0B4",
        },
        rule: {
          DEFAULT: "#E8E2D7",
          strong: "#D5CEC0",
        },
        vermilion: {
          DEFAULT: "#D95D39",
          hover: "#C34C2A",
          soft: "#FCEEE9",
          ring: "rgba(217, 93, 57, 0.20)",
        },
        sage: {
          DEFAULT: "#1B6B50",
          soft: "#E7F3EE",
        },
        ochre: {
          DEFAULT: "#B46914",
          soft: "#FDF4E6",
        },
        crimson: {
          DEFAULT: "#B83232",
          soft: "#FBECEC",
        },
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "var(--font-devanagari)",
          "system-ui",
          "sans-serif",
        ],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      boxShadow: {
        slip: "0 1px 2px rgba(20, 19, 17, 0.03), 0 8px 24px rgba(20, 19, 17, 0.04)",
        dock: "0 12px 36px rgba(20, 19, 17, 0.08), 0 1px 3px rgba(20, 19, 17, 0.05)",
        orb: "0 10px 30px rgba(217, 93, 57, 0.28)",
      },
      keyframes: {
        "halo-idle": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.45" },
          "50%": { transform: "scale(1.18)", opacity: "0.14" },
        },
        "halo-outer": {
          "0%, 100%": { transform: "scale(1.06)", opacity: "0.24" },
          "50%": { transform: "scale(1.32)", opacity: "0.06" },
        },
        "slip-in": {
          "0%": { opacity: "0", transform: "translateY(10px) scale(0.99)" },
          "100%": { opacity: "1", transform: "translateY(0) scale(1)" },
        },
      },
      animation: {
        "halo-idle": "halo-idle 3.6s ease-in-out infinite",
        "halo-outer": "halo-outer 4.8s ease-in-out infinite",
        "slip-in": "slip-in 0.28s cubic-bezier(0.22, 1, 0.36, 1) forwards",
      },
    },
  },
  plugins: [],
};

export default config;
