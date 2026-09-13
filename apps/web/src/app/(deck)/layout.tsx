import type { Metadata } from "next";
import type { ReactNode } from "react";
import { Atkinson_Hyperlegible_Next, Bricolage_Grotesque } from "next/font/google";
import "./globals.css";

const bricolageGrotesque = Bricolage_Grotesque({
  variable: "--font-bricolage-grotesque",
  subsets: ["latin"],
  axes: ["opsz", "wdth"],
});

const atkinsonHyperlegibleNext = Atkinson_Hyperlegible_Next({
  variable: "--font-atkinson-hyperlegible-next",
  subsets: ["latin"],
  style: ["normal", "italic"],
});

export const metadata: Metadata = {
  title: "Standard Physics",
  description: "Scan your shop with an iPhone and see what to fix for the ADA.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html
      lang="en"
      className={`${bricolageGrotesque.variable} ${atkinsonHyperlegibleNext.variable} h-full`}
    >
      <body className="min-h-full">{children}</body>
    </html>
  );
}
