import { Suspense } from "react";

import { LoginForm } from "@/components/auth/login-form";
import { WelcomeShell } from "@/components/auth/welcome-shell";
import { Loading } from "@/components/loading";

export const metadata = { title: "Sign in · fb-agent" };

/**
 * `Suspense` is not decoration: `LoginForm` reads `?next=` with
 * `useSearchParams`, and a component that does opts its whole subtree into
 * client rendering unless a boundary catches it. Without this the build fails
 * outright.
 */
export default function LoginPage() {
  return (
    <WelcomeShell>
      <Suspense fallback={<Loading className="h-72" />}>
        <LoginForm />
      </Suspense>
    </WelcomeShell>
  );
}
