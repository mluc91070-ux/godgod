import type { Metadata } from "next";
import { Exo_2, Orbitron } from "next/font/google";

import Footer from "@/components/Footer";
import Nav from "@/components/Nav";
import { getStatus } from "@/lib/status";
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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  // Memoised for the render, so this shares the request the strip and the
  // footer already make rather than adding a third.
  const status = await getStatus();
  const beating = status.ok ? status.data.collection.scheduler_running : false;

  return (
    <html lang="en" className={`${display.variable} ${body.variable}`}>
      <body className="min-h-screen overflow-x-hidden bg-void font-sans text-bone antialiased">
        <Nav beating={beating} />
        <StatusBar />
        <main className="px-4 py-10 sm:px-6">{children}</main>
        <Footer />
      </body>
    </html>
  );
}
