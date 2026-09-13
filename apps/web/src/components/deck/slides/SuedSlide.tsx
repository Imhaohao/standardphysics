"use client";

import { motion, type Variants } from "motion/react";
import { easeDrawn, exitTransition } from "@/lib/motion";
import { facts } from "@/lib/facts";
import { FinePrint, MaskedLines } from "../primitives";

const CUP_OUTLINE = "M85.2 225 L122 566 Q124 584 142 584 L258 584 Q276 584 278 566 L314.8 225";
const LID_DOME = "M92 204 C96 118 304 118 308 204";
const TEA_FILL = "M92 300 L122 566 Q124 584 142 584 L258 584 Q276 584 278 566 L308 300 Z";

const pearlRows = [
  { y: 556, xs: [150, 186, 222, 258] },
  { y: 522, xs: [138, 172, 206, 240, 272] },
  { y: 490, xs: [152, 188, 224, 260] },
];

const pearls = pearlRows.flatMap((row, rowIndex) =>
  row.xs.map((x, column) => ({ x, y: row.y + ((column * 7) % 5), order: rowIndex * 5 + ((column * 3) % 5) })),
);

const stroke = { stroke: "var(--color-ink)", strokeWidth: 7, strokeLinecap: "round", strokeLinejoin: "round", fill: "none" } as const;

function drawn(delay: number, duration = 0.9): Variants {
  return {
    enter: { pathLength: 0, opacity: 0 },
    present: { pathLength: 1, opacity: 1, transition: { pathLength: { duration, ease: easeDrawn, delay }, opacity: { duration: 0.01, delay } } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

function pearlDrop(order: number): Variants {
  return {
    enter: { y: -520, opacity: 0 },
    present: {
      y: 0,
      opacity: 1,
      transition: { y: { type: "spring", stiffness: 260, damping: 15, delay: 1.35 + order * 0.045 }, opacity: { duration: 0.01, delay: 1.35 + order * 0.045 } },
    },
    exit: { opacity: 0, transition: exitTransition },
  };
}

const teaRise: Variants = {
  enter: { scaleY: 0 },
  present: { scaleY: 1, transition: { duration: 1.1, ease: easeDrawn, delay: 0.95 } },
  exit: { opacity: 0, transition: exitTransition },
};

const lidDrop: Variants = {
  enter: { y: -140, opacity: 0 },
  present: { y: 0, opacity: 1, transition: { type: "spring", stiffness: 300, damping: 18, delay: 2.35 } },
  exit: { opacity: 0, transition: exitTransition },
};

const strawStab: Variants = {
  enter: { y: -260, opacity: 0 },
  present: { y: 0, opacity: 1, transition: { type: "spring", stiffness: 240, damping: 20, delay: 2.75 } },
  exit: { opacity: 0, transition: exitTransition },
};

function BobaCup() {
  return (
    <svg viewBox="0 0 400 620" className="h-full max-h-full w-auto overflow-visible" role="img" aria-label="A boba tea cup filling with tapioca pearls">
      <defs>
        <clipPath id="cup-inside">
          <path d={TEA_FILL} />
        </clipPath>
      </defs>
      <motion.path d={TEA_FILL} fill="var(--color-paper-sunken)" style={{ transformOrigin: "200px 584px" }} variants={teaRise} />
      <g clipPath="url(#cup-inside)">
        {pearls.map((pearl) => (
          <motion.circle key={`${pearl.x}-${pearl.y}`} cx={pearl.x} cy={pearl.y} r={17} fill="var(--color-ink)" variants={pearlDrop(pearl.order)} />
        ))}
      </g>
      <motion.g variants={strawStab}>
        <path d="M214 36 L246 36 L222 540 L196 540 Z" {...stroke} fill="var(--color-paper-raised)" />
      </motion.g>
      <motion.path d={CUP_OUTLINE} {...stroke} variants={drawn(0.25)} />
      <motion.g variants={lidDrop}>
        <path d={LID_DOME} {...stroke} fill="var(--color-paper-raised)" fillOpacity={0.55} />
        <rect x={70} y={200} width={260} height={22} rx={11} {...stroke} fill="var(--color-paper-raised)" />
      </motion.g>
    </svg>
  );
}

export function SuedSlide() {
  return (
    <div className="deck-gutter grid h-full grid-cols-[1.7fr_1fr] items-center gap-deck-gap">
      <div>
        <h2 className="font-display text-headline font-extrabold">
          <MaskedLines lines={["Our family", "friend’s boba", "shop got sued."]} delay={0.1} />
        </h2>
        <div className="mt-deck-rise">
          <FinePrint delay={1.2}>{facts.lawsuit.caption}</FinePrint>
        </div>
      </div>
      <div className="flex h-deck-art justify-center">
        <BobaCup />
      </div>
    </div>
  );
}
