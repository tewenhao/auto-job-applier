import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "auto-job-applier · dashboard",
  description: "Review, steer, and approve tailored applications.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <header className="site-header">
          <div className="wrap">
            <Link href="/" className="brand">
              auto-job-applier
            </Link>
            <nav className="site-nav">
              <Link href="/">Listings</Link>
              <Link href="/applications">Applications</Link>
            </nav>
          </div>
        </header>
        <main className="wrap">{children}</main>
      </body>
    </html>
  );
}
