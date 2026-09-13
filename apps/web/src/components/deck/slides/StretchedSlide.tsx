"use client";

import { Books, Briefcase, Moon, Sun } from "@phosphor-icons/react";
import { AnimatePresence, animate, motion, useMotionValue, useTransform, type Variants } from "motion/react";
import { useEffect } from "react";
import { easeDrawn, exitTransition } from "@/lib/motion";
import type { SlideProps } from "../slides";

const CLOCK = { r: 150, turnSeconds: 1.1 };
const DAY_SECONDS = CLOCK.turnSeconds * 2;
const FEE_COINS = 10;
const SARAS_COINS = 2;

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

function Coin({ filled, index }: { filled: boolean; index: number }) {
  return (
    <motion.span
      variants={{
        enter: { opacity: 0, y: -40 },
        present: { opacity: 1, y: 0, transition: { duration: 0.45, ease: easeDrawn, delay: 0.5 + index * 0.12 } },
        exit: { opacity: 0, transition: exitTransition },
      }}
      className={`stretched-coin rounded-full ${filled ? "bg-tape shadow-md" : "bg-paper-sunken"}`}
    />
  );
}

function NoMoney() {
  return (
    <motion.div key="money" initial="enter" animate="present" exit="exit" className="flex items-center gap-deck-gap">
      <div className="grid grid-cols-5 gap-deck-hairline">
        {Array.from({ length: FEE_COINS }, (_, index) => (
          <Coin key={index} index={index} filled={index < SARAS_COINS} />
        ))}
      </div>
      <motion.span variants={appears(0.2)} className="text-ink">
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
