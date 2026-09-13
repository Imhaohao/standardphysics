"use client";

import { AnimatePresence, motion, type Variants } from "motion/react";
import { facts } from "@/lib/facts";
import { easeDrawn, exitTransition } from "@/lib/motion";
import { CountFromProgress, FinePrint, MaskedLines, useProgress } from "../primitives";
import type { SlideProps } from "../slides";

const wholeNumber = new Intl.NumberFormat("en-US");
const paidPercent = facts.casesWithMoneyPercent.value;
const fixOrderedPercent = facts.casesWithFixOrderedPercent.value;

const GRID = { size: 10, pitch: 90, radius: 30, top: 60, left: 95 };
const VIEW = { width: 1000, height: 1400 };
const BLEED = { starts: 1.3, bills: 54 };
const BILL = { width: 46, height: 22 };

function noise(seed: number) {
  const value = Math.sin(seed * 12.9898) * 43758.5453;
  return value - Math.floor(value);
}

const cases = Array.from({ length: GRID.size * GRID.size }, (_, index) => ({
  index,
  x: GRID.left + (index % GRID.size) * GRID.pitch,
  y: GRID.top + Math.floor(index / GRID.size) * GRID.pitch,
  paid: index < paidPercent,
}));

const paidCases = cases.filter((lawsuit) => lawsuit.paid);

const fixOrderedCases = new Set(
  [...paidCases]
    .sort((left, right) => noise(left.index + 0.31) - noise(right.index + 0.31))
    .slice(0, fixOrderedPercent)
    .map((lawsuit) => lawsuit.index),
);

const bills = Array.from({ length: BLEED.bills }, (_, index) => {
  const source = paidCases[Math.floor(noise(index + 0.7) * paidCases.length)];
  return {
    key: index,
    x: source.x,
    y: source.y,
    drift: (noise(index + 0.2) - 0.5) * 140,
    spin: (noise(index + 0.9) - 0.5) * 90,
    seconds: 1.8 + noise(index + 0.4) * 1.2,
    delay: BLEED.starts + noise(index + 0.6) * 2.4,
    pause: noise(index + 0.8) * 1.2,
  };
});

function caseAppears(index: number): Variants {
  return {
    enter: { scale: 0, opacity: 0 },
    present: { scale: 1, opacity: 1, transition: { duration: 0.35, ease: easeDrawn, delay: 0.2 + index * 0.008 } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

function Lawsuit({ lawsuit, showsFixOrders }: { lawsuit: (typeof cases)[number]; showsFixOrders: boolean }) {
  const fixOrdered = showsFixOrders && fixOrderedCases.has(lawsuit.index);
  return (
    <motion.g variants={caseAppears(lawsuit.index)} style={{ originX: `${lawsuit.x}px`, originY: `${lawsuit.y}px` }}>
      <circle cx={lawsuit.x} cy={lawsuit.y} r={GRID.radius} fill={lawsuit.paid ? "var(--color-ink)" : "var(--color-rule)"} />
      <motion.circle
        cx={lawsuit.x}
        cy={lawsuit.y}
        r={GRID.radius + 9}
        fill="none"
        stroke="var(--color-tape-deep)"
        strokeWidth={9}
        initial={false}
        animate={fixOrdered ? { pathLength: 1, opacity: 1 } : { pathLength: 0, opacity: 0 }}
        transition={{ duration: 0.5, ease: easeDrawn, delay: fixOrdered ? noise(lawsuit.index + 0.5) * 0.9 : 0 }}
      />
    </motion.g>
  );
}

function FallingBill({ bill }: { bill: (typeof bills)[number] }) {
  return (
    <motion.g
      initial={{ x: bill.x, y: bill.y, opacity: 0, rotate: 0 }}
      animate={{
        x: [bill.x, bill.x + bill.drift * 0.4, bill.x + bill.drift],
        y: [bill.y, bill.y + 260, VIEW.height + 80],
        rotate: [0, bill.spin, -bill.spin],
        opacity: [0, 1, 1],
      }}
      transition={{ duration: bill.seconds, delay: bill.delay, repeat: Infinity, repeatDelay: bill.pause, ease: "easeIn", times: [0, 0.25, 1] }}
    >
      <rect x={-BILL.width / 2} y={-BILL.height / 2} width={BILL.width} height={BILL.height} rx={3} fill="var(--color-paper-raised)" stroke="var(--color-ink)" strokeWidth={3} />
      <ellipse cx={0} cy={0} rx={6} ry={7} fill="none" stroke="var(--color-ink)" strokeWidth={2} />
    </motion.g>
  );
}

function BleedingLawsuits({ showsFixOrders }: { showsFixOrders: boolean }) {
  return (
    <svg
      viewBox={`0 0 ${VIEW.width} ${VIEW.height}`}
      preserveAspectRatio="xMidYMin meet"
      className="h-full w-full overflow-hidden"
      role="img"
      aria-label={`100 lawsuits: ${paidPercent} pay out and drain money, ${fixOrderedPercent} are also ordered to fix the barrier`}
    >
      {bills.map((bill) => (
        <FallingBill key={bill.key} bill={bill} />
      ))}
      {cases.map((lawsuit) => (
        <Lawsuit key={lawsuit.index} lawsuit={lawsuit} showsFixOrders={showsFixOrders} />
      ))}
    </svg>
  );
}

function Stat({ percent, caption, size, delay }: { percent: number; caption: string[]; size: "display" | "headline"; delay: number }) {
  const progress = useProgress(1.1, delay);
  return (
    <div className="flex flex-col gap-deck-hairline">
      <p className={`font-display font-extrabold figures-tabular ${size === "display" ? "text-display" : "text-headline"}`}>
        <CountFromProgress progress={progress} total={percent} format={(value) => `${value}%`} />
      </p>
      <p className="font-display text-lede font-bold">
        <MaskedLines lines={caption} delay={delay + 0.2} />
      </p>
    </div>
  );
}

export function PayoutsSlide({ step }: SlideProps) {
  const showsFixOrders = step > 0;
  return (
    <div className="deck-gutter grid h-full grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-deck-gap">
      <div className="flex flex-col justify-center gap-deck-rise">
        <Stat percent={paidPercent} caption={["of ADA cases reported in", "California ended in a payout"]} size="display" delay={0.3} />
        <AnimatePresence>
          {showsFixOrders && (
            <motion.div key="fix-order" initial="enter" animate="present" exit="exit">
              <Stat percent={fixOrderedPercent} caption={["were ordered to", "fix the barrier"]} size="headline" delay={0.1} />
            </motion.div>
          )}
        </AnimatePresence>
        <FinePrint delay={1.6}>{`${facts.casesWithMoneyPercent.source}, ${wholeNumber.format(facts.casesWithMoneyPercent.caseReports)} California case reports`}</FinePrint>
      </div>
      <div className="min-h-0">
        <BleedingLawsuits showsFixOrders={showsFixOrders} />
      </div>
    </div>
  );
}
