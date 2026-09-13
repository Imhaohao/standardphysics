"use client";

import dynamic from "next/dynamic";

export const DeckLoader = dynamic(() => import("./Deck").then((module) => module.Deck), { ssr: false });
