import type { Metadata } from "next";
import type { ReactNode } from "react";
import { appFontVariables } from "../fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "Standard Physics",
  description: "Scan your shop with an iPhone and see what to fix for the ADA.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`${appFontVariables} h-full`} suppressHydrationWarning>
      <body className="min-h-full" suppressHydrationWarning>{children}</body>
    </html>
  );
}
