import type { Metadata } from "next";
import Footer from "@/components/Footer.tsx";
import { VIEWS } from "@/lib/state.ts";
import { SITE_NAME, TEXTS } from "@/lib/texts.ts";

const BASE = process.env.NEXT_PUBLIC_SITE_BASE ?? "";

export const metadata: Metadata = { title: `Page not found · WHATWG ${SITE_NAME}` };

export default function NotFound() {
  return (
    <>
      <header className="head">
        <h1>Page not found</h1>
        <p className="subtitle">WHATWG {SITE_NAME}</p>
        <a className="logo" href={`${BASE}/`} aria-label="Living Statistics home">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={`${BASE}/favicon.svg`} alt="" width={72} height={72} />
        </a>
      </header>
      <main>
        <p>There’s no page at this address. The views are:</p>
        <ul>
          {VIEWS.map((v) => (
            <li key={v}>
              <a href={`${BASE}/${v}/`}>{TEXTS[v].tab}</a>: {TEXTS[v].question}
            </li>
          ))}
        </ul>
      </main>
      <Footer />
    </>
  );
}
