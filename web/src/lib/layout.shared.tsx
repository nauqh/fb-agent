import type { BaseLayoutProps } from "fumadocs-ui/layouts/shared";
import { House } from "lucide-react";

export function baseOptions(): BaseLayoutProps {
  return {
    nav: {
      title: "Social Agent",
      url: "/docs",
    },
    links: [{ text: "Back to app", url: "/", icon: <House /> }],
    themeSwitch: {
      enabled: false,
    },
  };
}
