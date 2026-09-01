import type { Config } from "tailwindcss";

/**
 * Palette and type from the GODGOD brand charter.
 *
 * The five charter colours are `bone`, `grey`, `carbon`, `magenta`, `amber`.
 * Everything else here is derived: the page and surface blacks, and the hairline
 * that separates rows. `magenta` and `amber` are accents — they mark state and
 * emphasis, and they are never used for body text on black, where neither
 * clears a readable contrast ratio.
 */
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        void: "#050506",
        surface: "#111112",
        line: "#232326",
        carbon: "#1a1a1a",
        bone: "#f2f2f2",
        grey: "#a0a0a0",
        muted: "#6e6e73",
        magenta: "#ff2cf0",
        amber: "#ff6a00",
        // A sixth colour, outside the charter, added for one job: the core of
        // the market field is green while the collector is actually working
        // and bone when it is not. It is a state, not a decoration — the one
        // place on the site where "alive" has to be readable at a glance.
        live: "#00ff9d",
      },
      fontFamily: {
        // Orbitron for identity and headings, Exo 2 for prose, monospace for
        // anything a reader might need to compare digit by digit.
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        sans: ["var(--font-body)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      letterSpacing: {
        widest: "0.22em",
      },
    },
  },
  plugins: [],
};

export default config;
