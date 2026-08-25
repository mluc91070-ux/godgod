import type { Metadata } from "next";

import Nav from "@/components/Nav";
import StatusBar from "@/components/StatusBar";
import "@/styles/globals.css";

export const metadata: Metadata = {
  title: "GODGOD",
  description:
    "An autonomous research system studying how meme narratives propagate on Solana. It publishes what it tested, including what failed.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-void text-bone antialiased">
        <Nav />
        <StatusBar />
        <main className="px-6 py-10">{children}</main>
        <footer className="border-t border-line px-6 py-6 text-[10px] uppercase tracking-widest text-muted">
          godgod — research system. no financial advice. no execution. failures are published.
        </footer>
      </body>
    </html>
  );
}
