import type { Metadata } from "next";
import ViewPage, { title, viewParams } from "@/server/page.tsx";
import type { View } from "@/lib/state.ts";

export const dynamicParams = false;
export const generateStaticParams = viewParams;

export async function generateMetadata({ params }: PageProps<"/[view]">): Promise<Metadata> {
  const { view } = await params;
  return { title: title(view as View, null) };
}

export default async function Page({ params }: PageProps<"/[view]">) {
  const { view } = await params;
  return <ViewPage view={view as View} spec={null} />;
}
