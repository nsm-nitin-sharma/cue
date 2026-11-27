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
          DEFAULT: "#F7F8FA",
          elevated: "#FFFFFF",
          subtle: "#F1F3F6",
          wash: "#E4E7EC",
        },
        ink: {
          DEFAULT: "#0F172A",
          secondary: "#475467",
          muted: "#667085",
          faint: "#98A2B3",
        },
        rule: {
          DEFAULT: "#E4E7EC",
          strong: "#D0D5DD",
        },
        // Enterprise Precision Cobalt Accent (replaces playful orange while preserving token compatibility)
        vermilion: {
          DEFAULT: "#1D4ED8",
          hover: "#1E40AF",
          soft: "#EFF6FF",
          ring: "rgba(37, 99, 235, 0.22)",
        },
        sage: {
          DEFAULT: "#15803D",
          soft: "#ECFDF3",
        },
        ochre: {
          DEFAULT: "#B45309",
          soft: "#FFFAEB",
        },
        crimson: {
          DEFAULT: "#B91C1C",
          soft: "#FEF2F2",
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
        slip: "0 1px 2px rgba(16, 24, 40, 0.04), 0 4px 12px rgba(16, 24, 40, 0.03)",
        dock: "0 10px 30px rgba(16, 24, 40, 0.08), 0 1px 3px rgba(16, 24, 40, 0.05)",
        orb: "0 8px 24px rgba(15, 23, 42, 0.22)",
      },
      keyframes: {
        "halo-idle": {
          "0%, 100%": { transform: "scale(1)", opacity: "0.38" },
          "50%": { transform: "scale(1.14)", opacity: "0.12" },
        },
        "halo-outer": {
          "0%, 100%": { transform: "scale(1.04)", opacity: "0.22" },
          "50%": { transform: "scale(1.26)", opacity: "0.05" },
        },
        "slip-in": {
          "0%": { opacity: "0", transform: "translateY(6px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
      animation: {
        "halo-idle": "halo-idle 4s ease-in-out infinite",
        "halo-outer": "halo-outer 5.2s ease-in-out infinite",
        "slip-in": "slip-in 0.22s cubic-bezier(0.22, 1, 0.36, 1) forwards",
      },
    },
  },
  plugins: [],
};

export default config;
