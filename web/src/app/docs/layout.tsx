import { RootProvider } from "fumadocs-ui/provider/next";
import type { ReactNode } from "react";

import { DocsLayout } from "fumadocs-ui/layouts/docs";
import { baseOptions } from "@/lib/layout.shared";
import { source } from "@/lib/source";

export default function DocumentationLayout({ children }: { children: ReactNode }) {
  return (
    <RootProvider
      search={{
        options: {
          api: "/docs/api/search",
        },
      }}
      theme={{
        enabled: false,
      }}
    >
      <DocsLayout
        {...baseOptions()}
        tree={source.getPageTree()}
        containerProps={{
          className: "lg:h-screen lg:min-h-0 lg:flex-1 lg:min-w-0 lg:overflow-y-auto",
        }}
      >
        {children}
      </DocsLayout>
    </RootProvider>
  );
}
