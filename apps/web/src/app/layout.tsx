import type { Metadata } from "next";
import { Atkinson_Hyperlegible_Mono, Atkinson_Hyperlegible_Next } from "next/font/google";
import "./globals.css";

const atkinsonNext = Atkinson_Hyperlegible_Next({ subsets: ["latin"], variable: "--font-atkinson-next" });
const atkinsonMono = Atkinson_Hyperlegible_Mono({ subsets: ["latin"], variable: "--font-atkinson-mono" });

export const metadata: Metadata = {
  title: "Standard Physics",
  description: "See what gets in the way of customers in your shop, and how to fix it.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className={`${atkinsonNext.variable} ${atkinsonMono.variable}`}>
      <body className="min-h-dvh">{children}</body>
    </html>
  );
}
