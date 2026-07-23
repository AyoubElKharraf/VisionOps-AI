import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "VisionOps AI",
  description: "Real-time computer vision & video surveillance platform",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
