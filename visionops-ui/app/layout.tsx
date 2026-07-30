import type { Metadata } from "next";
import { Suspense } from "react";
import { AppShell } from "@/components/AppShell";
import { AuthGate } from "@/components/AuthGate";
import { AuthProvider } from "@/lib/auth";
import "./globals.css";

export const metadata: Metadata = {
  title: "VisionOps AI — Control Center",
  description: "Real-time computer vision monitoring, ROI editor, and alert gallery",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <AuthProvider>
          <Suspense
            fallback={
              <div className="flex min-h-screen items-center justify-center bg-ink text-sm text-muted">
                Loading…
              </div>
            }
          >
            <AuthGate>
              <AppShell>{children}</AppShell>
            </AuthGate>
          </Suspense>
        </AuthProvider>
      </body>
    </html>
  );
}
