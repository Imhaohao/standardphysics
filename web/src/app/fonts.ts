import { Atkinson_Hyperlegible_Mono, Karla, Libre_Franklin } from "next/font/google";

const karla = Karla({ subsets: ["latin"], variable: "--font-karla", display: "swap" });
const libreFranklin = Libre_Franklin({ subsets: ["latin"], weight: ["800"], variable: "--font-libre-franklin", display: "swap" });
/** next/font has no metrics for this family, so it gets a plain monospace fallback instead of a generated one. */
const atkinsonMono = Atkinson_Hyperlegible_Mono({
  subsets: ["latin"],
  variable: "--font-atkinson-mono",
  display: "swap",
  adjustFontFallback: false,
  fallback: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
});

export const fontVariables = `${karla.variable} ${libreFranklin.variable} ${atkinsonMono.variable}`;
