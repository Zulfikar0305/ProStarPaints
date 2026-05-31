/** ProStar Paints — Tailwind theme (experimental Tailwind UI overhaul).
 *  Futuristic dark navy + neon purple/green palette.
 *  Scans all Django templates + JS for class usage.
 */
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.html",
    "./**/templates/**/*.html",
    "./static/js/**/*.js",
  ],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        /* Brand */
        brand: {
          purple: {
            50:  "#f5f3ff",
            100: "#ede9fe",
            200: "#ddd6fe",
            300: "#c4b5fd",
            400: "#a78bfa",
            500: "#8b5cf6",
            600: "#7c3aed",
            700: "#6d28d9",
            800: "#5b21b6",
            900: "#4c1d95",
          },
          green: {
            50:  "#ecfdf5",
            100: "#d1fae5",
            200: "#a7f3d0",
            300: "#6ee7b7",
            400: "#34d399",
            500: "#10b981",
            600: "#059669",
            700: "#047857",
            800: "#065f46",
            900: "#064e3b",
          },
        },
        /* App shell — futuristic navy/charcoal */
        ink: {
          950: "#070a18",
          900: "#0b1024",
          850: "#0e132c",
          800: "#121939",
          700: "#1a2247",
          600: "#222c5a",
          500: "#2c3a73",
        },
        surface: {
          glass:  "rgba(18, 25, 57, 0.55)",
          panel:  "rgba(255, 255, 255, 0.04)",
          raised: "rgba(255, 255, 255, 0.07)",
          line:   "rgba(255, 255, 255, 0.08)",
        },
        accent: {
          neon:    "#a855f7",
          mint:    "#34d399",
          cyan:    "#22d3ee",
          amber:   "#fbbf24",
          rose:    "#fb7185",
        },
      },
      fontFamily: {
        sans: [
          "Inter", "ui-sans-serif", "system-ui",
          "Segoe UI", "Roboto", "Helvetica Neue", "Arial", "sans-serif",
        ],
        display: [
          "Space Grotesk", "Inter", "ui-sans-serif", "system-ui", "sans-serif",
        ],
        mono: [
          "JetBrains Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace",
        ],
      },
      boxShadow: {
        glow:        "0 0 0 1px rgba(139,92,246,.35), 0 12px 40px -8px rgba(139,92,246,.55)",
        "glow-green":"0 0 0 1px rgba(52,211,153,.35), 0 12px 40px -8px rgba(52,211,153,.55)",
        "glow-cyan": "0 0 0 1px rgba(34,211,238,.35), 0 12px 40px -8px rgba(34,211,238,.55)",
        glass:       "0 20px 60px -20px rgba(0,0,0,.6), inset 0 1px 0 rgba(255,255,255,.06)",
        "glass-lg":  "0 40px 100px -30px rgba(0,0,0,.7), inset 0 1px 0 rgba(255,255,255,.08)",
      },
      backgroundImage: {
        "grid-faint":
          "linear-gradient(rgba(139,92,246,.08) 1px, transparent 1px), linear-gradient(90deg, rgba(139,92,246,.08) 1px, transparent 1px)",
        "radial-spotlight":
          "radial-gradient(circle at top left, rgba(139,92,246,.18), transparent 55%), radial-gradient(circle at bottom right, rgba(52,211,153,.14), transparent 55%)",
        "brand-stripe":
          "linear-gradient(135deg, #7c3aed 0%, #6d28d9 50%, #059669 100%)",
        "ink-fade":
          "linear-gradient(180deg, #0b1024 0%, #070a18 60%, #050714 100%)",
      },
      backgroundSize: {
        "grid-32": "32px 32px",
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
      },
      animation: {
        "pulse-soft":  "pulseSoft 3.2s ease-in-out infinite",
        "shimmer":     "shimmer 2.4s linear infinite",
        "float":       "float 6s ease-in-out infinite",
      },
      keyframes: {
        pulseSoft: {
          "0%, 100%": { opacity: "0.75" },
          "50%":      { opacity: "1" },
        },
        shimmer: {
          "0%":   { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(100%)" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0)" },
          "50%":      { transform: "translateY(-4px)" },
        },
      },
    },
  },
  /* Long safelist: existing templates reference these via Django logic;
   * making sure they survive Tailwind's content purge. */
  safelist: [
    "psp-glass",
    "psp-glow",
    "psp-neon-ring",
    "psp-stat-card",
    "psp-cockpit-tile",
    { pattern: /^bg-(brand|ink|accent|surface)-/ },
    { pattern: /^text-(brand|accent)-/ },
    { pattern: /^shadow-(glow|glass)/ },
  ],
  corePlugins: {
    /* We disable preflight so Tailwind's CSS reset doesn't fight Bootstrap.
     * Bootstrap already supplies a normalised baseline. */
    preflight: false,
  },
  plugins: [],
};
