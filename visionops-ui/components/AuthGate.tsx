"use client";

import { useEffect } from "react";
import { usePathname, useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth";

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { ready, requiresLogin } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLogin = pathname === "/login";

  useEffect(() => {
    if (!ready) return;
    if (requiresLogin && !isLogin) {
      router.replace(`/login?next=${encodeURIComponent(pathname || "/")}`);
    }
    if (!requiresLogin && isLogin) {
      router.replace("/");
    }
  }, [ready, requiresLogin, isLogin, pathname, router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink text-sm text-muted">
        Loading authentication…
      </div>
    );
  }

  if (requiresLogin && !isLogin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink text-sm text-muted">
        Redirecting to login…
      </div>
    );
  }

  return <>{children}</>;
}
