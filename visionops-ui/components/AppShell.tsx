"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Activity,
  Bell,
  Camera,
  Hexagon,
  LayoutDashboard,
  LogOut,
  Video,
} from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/lib/auth";

const links = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/cameras", label: "Cameras", icon: Video },
  { href: "/monitor", label: "Live Monitor", icon: Camera },
  { href: "/roi", label: "ROI Editor", icon: Hexagon },
  { href: "/alerts", label: "Alert Gallery", icon: Bell },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, logout, ready } = useAuth();

  if (pathname === "/login") {
    return <>{children}</>;
  }

  const signOut = () => {
    logout();
    router.replace("/login");
  };

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[240px_1fr]">
      <aside className="border-b border-white/10 bg-panel/80 px-4 py-5 lg:border-b-0 lg:border-r">
        <div className="mb-8 flex items-center gap-3 px-2">
          <Activity className="h-6 w-6 text-accent" />
          <div>
            <p className="font-display text-sm font-semibold tracking-[0.18em] uppercase text-accent">
              VisionOps
            </p>
            <p className="text-xs text-muted">Control Center</p>
          </div>
        </div>
        <nav className="flex gap-1 overflow-x-auto lg:flex-col">
          {links.map(({ href, label, icon: Icon }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={clsx(
                  "flex min-h-11 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-accent/15 text-accent"
                    : "text-muted hover:bg-white/5 hover:text-white",
                )}
              >
                <Icon className="h-4 w-4 shrink-0" />
                {label}
              </Link>
            );
          })}
        </nav>
        {ready && user && (
          <div className="mt-6 space-y-2 border-t border-white/10 px-2 pt-4">
            <p className="truncate text-xs text-muted">
              {user.full_name || user.username}
              <span className="ml-1 text-accent">({user.role})</span>
            </p>
            <button
              type="button"
              onClick={signOut}
              className="flex min-h-11 w-full items-center gap-2 rounded-md px-2 text-sm text-muted hover:bg-white/5 hover:text-white"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        )}
      </aside>
      <div className="min-w-0">
        <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
          <p className="text-sm text-muted">
            Real-time CV · ONNX · ROI · Alerts
          </p>
          <span className="rounded-md border border-accent/30 bg-accent/10 px-2.5 py-1 text-xs text-accent">
            Phase 5
          </span>
        </header>
        <main className="px-6 py-6">{children}</main>
      </div>
    </div>
  );
}
