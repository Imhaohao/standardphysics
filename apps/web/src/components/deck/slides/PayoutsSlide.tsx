"use client";

import { Money, Wrench } from "@phosphor-icons/react";
import { motion, type Variants } from "motion/react";
import type { ComponentType } from "react";
import { facts } from "@/lib/facts";
import { easeDrawn, exitTransition } from "@/lib/motion";
import { CountFromProgress, FinePrint, MaskedLines, fadeReveal, useProgress } from "../primitives";

const GRID_SIZE = 10;
const wholeNumber = new Intl.NumberFormat("en-US");
const DOT_STAGGER = 0.012;

type Stat = {
  Icon: ComponentType<{ weight: "duotone"; className: string }>;
  percent: number;
  caption: string[];
  delay: number;
};

const stats: Stat[] = [
  { Icon: Money, percent: facts.casesWithMoneyPercent.value, caption: ["ended with money", "for the plaintiff"], delay: 0.2 },
  { Icon: Wrench, percent: facts.casesWithFixOrderedPercent.value, caption: ["ended with an order", "to fix the barrier"], delay: 0.9 },
];

function dotFill(index: number, filled: boolean, startDelay: number): Variants {
  return {
    enter: { scale: 0, opacity: 0 },
    present: {
      scale: 1,
      opacity: filled ? 1 : 0.35,
      transition: { duration: 0.35, ease: easeDrawn, delay: startDelay + index * DOT_STAGGER },
    },
    exit: { opacity: 0, transition: exitTransition },
  };
}

function PercentGrid({ percent, delay }: { percent: number; delay: number }) {
  const cells = Array.from({ length: GRID_SIZE * GRID_SIZE }, (_, index) => index);
  return (
    <svg viewBox="0 0 100 100" className="w-full max-w-72" role="img" aria-label={`${percent} of 100 dots filled`}>
      {cells.map((index) => (
        <motion.circle
          key={index}
          cx={(index % GRID_SIZE) * 10 + 5}
          cy={Math.floor(index / GRID_SIZE) * 10 + 5}
          r={3.6}
          fill={index < percent ? "var(--color-ink)" : "var(--color-rule)"}
          variants={dotFill(index, index < percent, delay)}
        />
      ))}
    </svg>
  );
}

function StatColumn({ stat }: { stat: Stat }) {
  const progress = useProgress(1.3, stat.delay);
  return (
    <div className="flex flex-col items-start gap-deck-hairline">
      <motion.span variants={fadeReveal(stat.delay, 20)} className="text-lede text-ink-muted">
        <stat.Icon weight="duotone" className="icon-em" />
      </motion.span>
      <div className="flex items-end gap-deck-gap">
        <p className="font-display text-display font-extrabold figures-tabular">
          <CountFromProgress progress={progress} total={stat.percent} format={(value) => `${value}%`} />
        </p>
        <PercentGrid percent={stat.percent} delay={stat.delay + 0.2} />
      </div>
      <p className="font-display text-lede font-bold">
        <MaskedLines lines={stat.caption} delay={stat.delay + 0.3} />
      </p>
    </div>
  );
}

export function PayoutsSlide() {
  return (
    <div className="deck-gutter flex h-full flex-col justify-center gap-deck-rise">
      <div className="grid grid-cols-2 gap-deck-gap">
        {stats.map((stat) => (
          <StatColumn key={stat.caption.join(" ")} stat={stat} />
        ))}
      </div>
      <FinePrint delay={1.6}>{`${facts.casesWithMoneyPercent.source}, ${wholeNumber.format(facts.casesWithMoneyPercent.caseReports)} California case reports`}</FinePrint>
    </div>
  );
}
