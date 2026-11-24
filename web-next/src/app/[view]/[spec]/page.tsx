import type { Metadata } from "next";
import ViewPage, { specParams, title } from "@/server/page.tsx";
import type { View } from "@/lib/state.ts";

export const dynamicParams = false;
export const generateStaticParams = specParams;

export async function generateMetadata({ params }: PageProps<"/[view]/[spec]">): Promise<Metadata> {
  const { view, spec } = await params;
  return { title: title(view as View, spec) };
}

export default async function Page({ params }: PageProps<"/[view]/[spec]">) {
  const { view, spec } = await params;
  return <ViewPage view={view as View} spec={spec} />;
}
