import { notFound } from "next/navigation";
import {
  DocsBody,
  DocsDescription,
  DocsPage,
  DocsTitle,
} from "fumadocs-ui/layouts/docs/page";

import { getMDXComponents } from "@/mdx-components";
import { source } from "@/lib/source";

export function generateStaticParams() {
  return source.generateParams();
}

async function getDocumentationPage(params: Promise<{ slug?: string[] }>) {
  const { slug } = await params;
  const page = source.getPage(slug);
  if (!page) notFound();
  return page;
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const page = await getDocumentationPage(params);
  return {
    title: `${page.data.title} | Social Agent`,
    description: page.data.description,
  };
}

export default async function DocumentationPage({
  params,
}: {
  params: Promise<{ slug?: string[] }>;
}) {
  const page = await getDocumentationPage(params);
  const MDXContent = page.data.body;

  return (
    // No previous/next footer: every doc stands on its own, not as a sequence.
    <DocsPage toc={page.data.toc} footer={{ enabled: false }}>
      <DocsTitle>{page.data.title}</DocsTitle>
      <DocsDescription>{page.data.description}</DocsDescription>
      <DocsBody>
        <MDXContent components={getMDXComponents()} />
      </DocsBody>
    </DocsPage>
  );
}
