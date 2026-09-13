"use client";

import { Books, Briefcase, Moon, Sun } from "@phosphor-icons/react";
import { AnimatePresence, animate, motion, useMotionValue, useTransform, type MotionValue, type Variants } from "motion/react";
import { useEffect, type ReactNode } from "react";
import { easeDrawn, exitTransition } from "@/lib/motion";
import type { SlideProps } from "../slides";

const CLOCK = { r: 150, turnSeconds: 1.1 };
const DAY_SECONDS = CLOCK.turnSeconds * 2;

function appears(delay: number): Variants {
  return {
    enter: { opacity: 0, scale: 0.8 },
    present: { opacity: 1, scale: 1, transition: { duration: 0.5, ease: easeDrawn, delay } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

function SaraAtHerDesk({ stretched }: { stretched: boolean }) {
  return (
    <motion.div variants={appears(0.1)} className="flex items-end gap-deck-hairline">
      <motion.img
        src="/sara.jpg"
        alt="Sara"
        initial={false}
        animate={{ filter: stretched ? "grayscale(0.8)" : "grayscale(0)", y: stretched ? 8 : 0 }}
        transition={{ duration: 1.4 }}
        className="size-deck-portrait rounded-full object-cover shadow-lg"
      />
      <Books weight="fill" className="stretched-books text-ink" />
    </motion.div>
  );
}

function useSpinningHands() {
  const turns = useMotionValue(0);
  useEffect(() => {
    const controls = animate(turns, 1, { duration: CLOCK.turnSeconds, ease: "linear", repeat: Infinity, delay: 0.6 });
    return () => controls.stop();
  }, [turns]);
  const angle = (value: number, turnsPerLap: number) => value * turnsPerLap * 2 * Math.PI;
  const minute = {
    x: useTransform(turns, (value) => Math.sin(angle(value, 1)) * 112),
    y: useTransform(turns, (value) => -Math.cos(angle(value, 1)) * 112),
  };
  const hour = {
    x: useTransform(turns, (value) => Math.sin(angle(value, 1 / 12)) * 70),
    y: useTransform(turns, (value) => -Math.cos(angle(value, 1 / 12)) * 70),
  };
  return { minute, hour };
}

function SpinningClock() {
  const { minute, hour } = useSpinningHands();
  return (
    <svg viewBox="-170 -170 340 340" className="size-full">
      <circle r={CLOCK.r} fill="var(--color-paper-raised)" stroke="var(--color-ink)" strokeWidth={10} />
      {Array.from({ length: 12 }, (_, index) => (
        <line key={index} x1={0} y1={-CLOCK.r + 16} x2={0} y2={-CLOCK.r + (index % 3 === 0 ? 44 : 30)} stroke="var(--color-ink)" strokeWidth={index % 3 === 0 ? 8 : 4} transform={`rotate(${index * 30})`} />
      ))}
      <motion.line x1={0} y1={0} x2={hour.x} y2={hour.y} stroke="var(--color-ink)" strokeWidth={14} strokeLinecap="round" />
      <motion.line x1={0} y1={0} x2={minute.x} y2={minute.y} stroke="var(--color-tape-deep)" strokeWidth={8} strokeLinecap="round" />
      <circle r={12} fill="var(--color-ink)" />
    </svg>
  );
}

function DaysPassing() {
  const cycle = { duration: DAY_SECONDS, repeat: Infinity, ease: "easeInOut" as const, delay: 0.6 };
  return (
    <div className="relative stretched-sky">
      <motion.span className="absolute inset-0 flex justify-center text-tape-deep" animate={{ opacity: [1, 0, 1] }} transition={cycle}>
        <Sun weight="fill" className="size-full" />
      </motion.span>
      <motion.span className="absolute inset-0 flex justify-center text-ink" animate={{ opacity: [0, 1, 0] }} transition={cycle}>
        <Moon weight="fill" className="size-full" />
      </motion.span>
    </div>
  );
}

function NoTime() {
  return (
    <motion.div key="time" initial="enter" animate="present" exit="exit" variants={appears(0.2)} className="flex flex-col items-center gap-deck-hairline">
      <DaysPassing />
      <div className="stretched-clock">
        <SpinningClock />
      </div>
    </motion.div>
  );
}

const SCALE = { pivotX: 400, pivotY: 170, arm: 250, rope: 150, tiltDegrees: 16, tiltDelay: 1.6 };

function useTilt(active: boolean) {
  const tilt = useMotionValue(0);
  useEffect(() => {
    if (!active) {
      tilt.jump(0);
      return;
    }
    const controls = animate(tilt, SCALE.tiltDegrees, { type: "spring", stiffness: 60, damping: 7, delay: SCALE.tiltDelay });
    return () => controls.stop();
  }, [active, tilt]);
  return tilt;
}

function useArmEnd(tilt: MotionValue<number>, side: 1 | -1) {
  const x = useTransform(tilt, (degrees) => SCALE.pivotX + side * Math.cos((degrees * Math.PI) / 180) * SCALE.arm);
  const y = useTransform(tilt, (degrees) => SCALE.pivotY + side * Math.sin((degrees * Math.PI) / 180) * SCALE.arm);
  const panY = useTransform(y, (value) => value + SCALE.rope);
  return { x, y, panY };
}

function Pan({ end, children }: { end: ReturnType<typeof useArmEnd>; children: ReactNode }) {
  const panX = useTransform(end.x, (value) => value - 110);
  const leftRope = useTransform(end.x, (value) => value - 100);
  const rightRope = useTransform(end.x, (value) => value + 100);
  return (
    <>
      <motion.line x1={end.x} y1={end.y} x2={leftRope} y2={end.panY} stroke="var(--color-ink)" strokeWidth={4} />
      <motion.line x1={end.x} y1={end.y} x2={rightRope} y2={end.panY} stroke="var(--color-ink)" strokeWidth={4} />
      <motion.path style={{ x: panX, y: end.panY }} d="M 0 0 L 220 0 Q 200 44 110 44 Q 20 44 0 0 Z" fill="var(--color-ink)" />
      <motion.g style={{ x: end.x, y: end.panY }}>{children}</motion.g>
    </>
  );
}

function coinDrops(index: number): Variants {
  return {
    enter: { y: -260, opacity: 0 },
    present: { y: 0, opacity: 1, transition: { type: "spring", stiffness: 300, damping: 18, delay: 0.5 + index * 0.25 } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

function SarasCoins() {
  return (
    <>
      {[-30, 30].map((offset, index) => (
        <motion.g key={offset} variants={coinDrops(index)}>
          <circle cx={offset} cy={-26} r={26} fill="var(--color-tape)" stroke="var(--color-tape-deep)" strokeWidth={4} />
          <text x={offset} y={-16} textAnchor="middle" fill="var(--color-ink)" className="font-display text-3xl font-extrabold">$</text>
        </motion.g>
      ))}
    </>
  );
}

const billStack = Array.from({ length: 7 }, (_, index) => index);

function ConsultantsFee() {
  return (
    <motion.g variants={coinDrops(2)}>
      {billStack.map((index) => (
        <g key={index} transform={`translate(${((index * 37) % 11) - 5} ${-18 - index * 22})`}>
          <rect x={-80} y={-14} width={160} height={30} rx={3} fill="var(--color-paper-raised)" stroke="var(--color-ink)" strokeWidth={4} />
          <text x={0} y={10} textAnchor="middle" fill="var(--color-ink)" className="font-display text-2xl font-extrabold">$</text>
        </g>
      ))}
    </motion.g>
  );
}

function BalanceScale({ active }: { active: boolean }) {
  const tilt = useTilt(active);
  const sarasSide = useArmEnd(tilt, -1);
  const feeSide = useArmEnd(tilt, 1);
  return (
    <svg viewBox="80 20 640 560" className="size-full overflow-visible">
      <path d={`M ${SCALE.pivotX} ${SCALE.pivotY} L ${SCALE.pivotX} 520`} stroke="var(--color-ink)" strokeWidth={12} />
      <rect x={SCALE.pivotX - 110} y={510} width={220} height={24} rx={6} fill="var(--color-ink)" />
      <motion.line x1={sarasSide.x} y1={sarasSide.y} x2={feeSide.x} y2={feeSide.y} stroke="var(--color-ink)" strokeWidth={12} strokeLinecap="round" />
      <circle cx={SCALE.pivotX} cy={SCALE.pivotY} r={16} fill="var(--color-tape)" stroke="var(--color-ink)" strokeWidth={6} />
      <Pan end={sarasSide}>
        <SarasCoins />
      </Pan>
      <Pan end={feeSide}>
        <ConsultantsFee />
      </Pan>
    </svg>
  );
}

function NoMoney() {
  return (
    <motion.div key="money" initial="enter" animate="present" exit="exit" className="flex items-end gap-deck-gap">
      <div className="stretched-scale">
        <BalanceScale active />
      </div>
      <motion.span variants={appears(0.9)} className="text-ink">
        <Briefcase weight="fill" className="stretched-briefcase" />
      </motion.span>
    </motion.div>
  );
}

export function StretchedSlide({ step }: SlideProps) {
  const needsMoney = step > 0;
  return (
    <div
      role="img"
      aria-label={needsMoney ? "Sara can pay only a small part of a consultant's fee" : "Days pass on a spinning clock while Sara sits with the stack of standards"}
      className="deck-gutter flex h-full items-center justify-center gap-deck-gap"
    >
      <SaraAtHerDesk stretched={needsMoney} />
      <AnimatePresence mode="wait" initial={false}>
        {needsMoney ? <NoMoney /> : <NoTime />}
      </AnimatePresence>
    </div>
  );
}
