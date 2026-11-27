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
          DEFAULT: "#FAF8F5",
          elevated: "#FFFFFF",
          subtle: "#F3EFE8",
          wash: "#ECE6DC",
        },
        ink: {
          DEFAULT: "#171614",
          secondary: "#5A554E",
          muted: "#8C857B",
          faint: "#C4BCB0",
        },
        rule: {
          DEFAULT: "#E5DFD5",
          strong: "#D4CCC0",
        },
        vermilion: {
          DEFAULT: "#D95D39",
          hover: "#C24B29",
          soft: "#FCEEE9",
          ring: "rgba(217, 93, 57, 0.22)",
        },
        sage: {
          DEFAULT: "#1E6B52",
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
        slip: "0 1px 2px rgba(23, 22, 20, 0.04), 0 6px 20px rgba(23, 22, 20, 0.04)",
        dock: "0 8px 32px rgba(23, 22, 20, 0.08), 0 1px 3px rgba(23, 22, 20, 0.06)",
        orb: "0 6px 22px rgba(217, 93, 57, 0.34)",
      },
      keyframes: {
        "voice-breathe": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.55" },
          "50%": { transform: "scale(1.16)", opacity: "0.2" },
        },
        "slip-in": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "voice-breathe": "voice-breathe 3s ease-in-out infinite",
        "slip-in": "slip-in 0.24s cubic-bezier(0.22, 1, 0.36, 1) forwards",
      },
    },
  },
  plugins: [],
};

export default config;
