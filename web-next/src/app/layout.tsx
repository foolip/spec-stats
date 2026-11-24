import type { Metadata, Viewport } from "next";
import "./globals.css";

const BASE = process.env.NEXT_PUBLIC_SITE_BASE ?? "";

export const metadata: Metadata = {
  title: "WHATWG Living Statistics",
  description: "Dashboards about WHATWG spec maintenance, from public GitHub data.",
  icons: { icon: `${BASE}/favicon.svg` },
};

export const viewport: Viewport = {
  themeColor: "#3c790a",
  width: "device-width",
  initialScale: 1,
};

// Links with a query string get the same page as without; hide the sections
// that follow the state until they show the URL's.
const PENDING = `if(location.search)document.documentElement.setAttribute("data-pending","")`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en-US" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: PENDING }} />
      </head>
      <body>
        <div className="page">{children}</div>
      </body>
    </html>
  );
}
