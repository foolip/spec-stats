import type { Metadata } from "next";
import ViewPage, { title } from "@/server/page.tsx";
import { DEFAULT_VIEW } from "@/lib/state.ts";

// The site's root is the default view; the page rewrites its URL to the view's.
export const metadata: Metadata = { title: title(DEFAULT_VIEW, null) };

export default function Home() {
  return <ViewPage view={DEFAULT_VIEW} spec={null} />;
}
