import type { Metadata } from "next";
import { Exo_2, Orbitron } from "next/font/google";

import { Wordmark } from "@/components/Mark";
import Nav from "@/components/Nav";
import StatusBar from "@/components/StatusBar";
import "@/styles/globals.css";

// Self-hosted at build time by next/font: no request to Google at runtime, no
// layout shift, and nothing for a blocked network to break.
const display = Orbitron({
  subsets: ["latin"],
  weight: ["400", "500", "700"],
  variable: "--font-display",
  display: "swap",
});

const body = Exo_2({
  subsets: ["latin"],
  weight: ["300", "400", "500"],
  variable: "--font-body",
  display: "swap",
});

const DESCRIPTION =
  "An autonomous research system studying how meme narratives propagate on Solana. " +
  "It publishes what it tested, including what failed.";

export const metadata: Metadata = {
  metadataBase: new URL("https://godgod.vercel.app"),
  title: {
    default: "GODGOD — the autonomous meme researcher",
    template: "%s — GODGOD",
  },
  description: DESCRIPTION,
  applicationName: "GODGOD",
  icons: {
    icon: [
      { url: "/icon.svg", type: "image/svg+xml" },
      { url: "/favicon.ico", sizes: "32x32" },
    ],
    apple: "/apple-icon.png",
  },
  openGraph: {
    type: "website",
    siteName: "GODGOD",
    title: "GODGOD — the autonomous meme researcher",
    description: DESCRIPTION,
    images: [{ url: "/og.png", width: 1200, height: 630, alt: "GODGOD" }],
  },
  twitter: {
    card: "summary_large_image",
    title: "GODGOD — the autonomous meme researcher",
    description: DESCRIPTION,
    images: ["/og.png"],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen bg-void font-sans text-bone antialiased">
        <Nav />
        <StatusBar />
        <main className="px-6 py-10">{children}</main>
        <footer className="flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-line px-6 py-8 text-[10px] uppercase tracking-widest text-muted">
          <Wordmark />
          <span>the autonomous meme researcher</span>
          <a
            href="https://x.com/godgodai"
            target="_blank"
            rel="noreferrer noopener"
            className="text-grey transition-colors hover:text-bone"
          >
            @godgodai
          </a>
          <span className="ml-auto">
            no financial advice. no execution. failures are published.
          </span>
        </footer>
      </body>
    </html>
  );
}
