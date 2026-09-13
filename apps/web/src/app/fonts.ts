import { Atkinson_Hyperlegible_Mono, Karla, Libre_Franklin } from "next/font/google";

const karla = Karla({ subsets: ["latin"], variable: "--font-karla" });
const libreFranklin = Libre_Franklin({ subsets: ["latin"], variable: "--font-libre-franklin" });
const atkinsonMono = Atkinson_Hyperlegible_Mono({ subsets: ["latin"], variable: "--font-atkinson-mono" });

export const appFontVariables = `${karla.variable} ${libreFranklin.variable} ${atkinsonMono.variable}`;
