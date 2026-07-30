"use client";

import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Activity } from "lucide-react";
import { useAuth } from "@/lib/auth";

export default function LoginPage() {
  const { login, requiresLogin, ready } = useAuth();
  const router = useRouter();
  const search = useSearchParams();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("visionops-admin");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    try {
      setBusy(true);
      setError(null);
      await login(username.trim(), password);
      const next = search.get("next") || "/";
      router.replace(next.startsWith("/") ? next : "/");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Login failed");
    } finally {
      setBusy(false);
    }
  };

  if (ready && !requiresLogin) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-ink px-4 text-sm text-muted">
        JWT is not enabled — opening dashboard…
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink px-4">
      <form
        onSubmit={(e) => void onSubmit(e)}
        className="w-full max-w-md space-y-5 rounded-xl border border-white/10 bg-panel/80 p-6 shadow-xl"
      >
        <div className="flex items-center gap-3">
          <Activity className="h-6 w-6 text-accent" />
          <div>
            <p className="font-display text-sm font-semibold tracking-[0.18em] uppercase text-accent">
              VisionOps
            </p>
            <p className="text-xs text-muted">Sign in to Control Center</p>
          </div>
        </div>

        <label className="block text-sm">
          Username
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>
        <label className="block text-sm">
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            className="mt-1 w-full rounded-md border border-white/10 bg-ink px-3 py-2 text-white outline-none focus:border-accent"
          />
        </label>

        {error && (
          <p className="rounded-md border border-red-400/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy || !username || !password}
          className="min-h-11 w-full rounded-md bg-accent px-4 text-sm font-medium text-ink hover:opacity-90 disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>

        <p className="text-xs text-muted">
          Default local admin: <code className="text-accent">admin</code> /{" "}
          <code className="text-accent">visionops-admin</code>
        </p>
      </form>
    </div>
  );
}
