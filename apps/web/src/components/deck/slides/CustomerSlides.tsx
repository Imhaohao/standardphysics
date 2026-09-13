"use client";

import { PersonSimple, PersonSimpleWalk, Wheelchair } from "@phosphor-icons/react";
import { Storefront } from "./SaraSlide";
import { AnimatePresence, motion, useTransform, type MotionValue, type Variants } from "motion/react";
import { useState } from "react";
import type { SlideProps } from "../slides";
import { facts } from "@/lib/facts";
import { easeDrawn, exitTransition } from "@/lib/motion";
import { CountFromProgress, FinePrint, MaskedLines, useProgress } from "../primitives";
import { MoonStacks, moonTrips } from "../MoonStacks";

const boomers = facts.boomersAllOver65By;
const disability = facts.olderAdultsWithDisability;
const wealth = facts.boomerNetWorthTrillions;

const arrivingCustomers = [
  { Icon: PersonSimpleWalk, delay: 0.9 },
  { Icon: Wheelchair, delay: 1.25 },
  { Icon: PersonSimpleWalk, delay: 1.6 },
];

function customerArrives(delay: number): Variants {
  return {
    enter: { x: "-160%", opacity: 0 },
    present: { x: "0%", opacity: 1, transition: { x: { duration: 1.1, ease: easeDrawn, delay }, opacity: { duration: 0.3, delay } } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

const shopReopens: Variants = {
  enter: { opacity: 0, scaleY: 0.3, scaleX: 1.12 },
  present: { opacity: 1, scaleY: 1, scaleX: 1, transition: { opacity: { duration: 0.2 }, scaleY: { type: "spring", stiffness: 260, damping: 16, delay: 0.1 }, scaleX: { type: "spring", stiffness: 260, damping: 16, delay: 0.1 } } },
  exit: { opacity: 0, transition: exitTransition },
};

function HappyLemonWelcomes() {
  return (
    <div className="relative flex h-deck-art items-end justify-center">
      <motion.div variants={shopReopens} style={{ originY: 1 }} className="flex h-full justify-center">
        <Storefront />
      </motion.div>
      <div role="img" aria-label="Customers, including a wheelchair user, heading into Sara’s shop" className="absolute bottom-0 right-full flex items-end text-headline leading-none">
        {arrivingCustomers.map((customer, index) => (
          <motion.span key={index} variants={customerArrives(customer.delay)} className={index === 1 ? "text-ink" : "text-ink-muted"}>
            <customer.Icon weight="fill" className="icon-em block" />
          </motion.span>
        ))}
      </div>
    </div>
  );
}

export function PivotSlide() {
  return (
    <div className="deck-gutter grid h-full grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)] items-center gap-deck-gap">
      <div>
        <h2 className="font-display text-figure font-extrabold">
          <MaskedLines lines={["Accessibility", "couldn’t be more", "important for", "small businesses."]} delay={0.1} />
        </h2>
        <p className="mt-deck-rise font-display text-caption font-bold text-ink-muted">
          <MaskedLines lines={["The customers who need accessible", "spaces have the most money to spend."]} delay={0.7} />
        </p>
      </div>
      <HappyLemonWelcomes />
    </div>
  );
}

type BoomerPhase = "aging" | "disability" | "wealth";
const boomerPhases: BoomerPhase[] = ["aging", "disability", "wealth"];

const CROWD = { columns: 10, rows: 5 };
const crowdSize = CROWD.columns * CROWD.rows;
const RETIREMENT_AGE = 65;
const FIRST_BOOMER_RETIRES = boomers.bornFrom + RETIREMENT_AGE;
const AGING_SECONDS = 3.2;

type CrowdColors = { faint: string; ink: string; tape: string };

function readCrowdColors(): CrowdColors {
  const styles = getComputedStyle(document.documentElement);
  const token = (name: string) => styles.getPropertyValue(name).trim();
  return { faint: token("--color-rule"), ink: token("--color-ink"), tape: token("--color-tape-deep") };
}

function birthYear(index: number) {
  return boomers.bornFrom + (index / (crowdSize - 1)) * (boomers.bornThrough - boomers.bornFrom);
}

function hasDisability(index: number) {
  return index % disability.outOf < disability.count;
}

function settledColor(index: number, phase: BoomerPhase, colors: CrowdColors) {
  if (phase === "aging") return colors.ink;
  if (hasDisability(index)) return colors.tape;
  return phase === "disability" ? colors.faint : colors.ink;
}

function CrowdMember({ index, phase, year, colors }: { index: number; phase: BoomerPhase; year: MotionValue<number>; colors: CrowdColors }) {
  const agingColor = useTransform(year, (value) => (value >= birthYear(index) + RETIREMENT_AGE ? colors.ink : colors.faint));
  const arrival = { duration: 0.6, ease: easeDrawn, delay: 0.15 + (index % CROWD.columns) * 0.03 + Math.floor(index / CROWD.columns) * 0.05 };
  return (
    <motion.span
      initial={{ opacity: 0, x: "-60%" }}
      animate={{ opacity: 1, x: "0%", ...(phase === "aging" ? {} : { color: settledColor(index, phase, colors) }) }}
      transition={{ opacity: arrival, x: arrival, color: { duration: 0.5, delay: (index % disability.outOf) * 0.04 } }}
      style={phase === "aging" ? { color: agingColor } : undefined}
    >
      <PersonSimple weight="fill" className="icon-em block" />
    </motion.span>
  );
}

function BoomerCrowd({ phase, year }: { phase: BoomerPhase; year: MotionValue<number> }) {
  const [colors] = useState(readCrowdColors);
  return (
    <motion.div
      layout
      transition={{ layout: { duration: 0.8, ease: easeDrawn } }}
      role="img"
      aria-label={`A crowd of baby boomers where ${disability.count} in every ${disability.outOf} are highlighted`}
      className="grid w-fit grid-cols-10 text-figure leading-none"
    >
      {Array.from({ length: crowdSize }, (_, index) => (
        <CrowdMember key={index} index={index} phase={phase} year={year} colors={colors} />
      ))}
    </motion.div>
  );
}

function AgingCopy({ year }: { year: MotionValue<number> }) {
  return (
    <>
      <p className="font-display text-display font-extrabold figures-tabular">
        <CountFromProgress progress={year} total={1} format={(value) => String(value)} />
      </p>
      <h2 className="font-display text-lede font-bold">
        <MaskedLines lines={[`By ${boomers.value}, every baby boomer will be 65 or older.`]} delay={0.1} />
      </h2>
      <div className="mt-deck-hairline">
        <FinePrint delay={1.2}>{boomers.source}</FinePrint>
      </div>
    </>
  );
}

function DisabilityCopy() {
  return (
    <>
      <h2 className="font-display text-headline font-extrabold">
        <MaskedLines lines={[`About ${disability.count} in ${disability.outOf} of them`, "live with a disability."]} delay={0.1} />
      </h2>
      <div className="mt-deck-hairline">
        <FinePrint delay={0.9}>{disability.source}</FinePrint>
      </div>
    </>
  );
}

function WealthCopy() {
  return (
    <>
      <h2 className="font-display text-headline font-extrabold figures-tabular">
        <MaskedLines lines={[`They hold $${wealth.value} trillion.`]} delay={0.1} />
      </h2>
      <p className="font-display text-lede font-bold text-ink-muted">
        <MaskedLines lines={[`Stacked in $1 bills, that reaches the Moon ${Math.floor(moonTrips)} times.`]} delay={2.4} />
      </p>
      <div className="mt-deck-hairline">
        <FinePrint delay={3}>{`${wealth.source}; bill thickness ${facts.dollarBillThicknessInches.value} in, ${facts.dollarBillThicknessInches.source}; ${facts.moonDistanceMiles.source}`}</FinePrint>
      </div>
    </>
  );
}

function BoomerCopy({ phase, year }: { phase: BoomerPhase; year: MotionValue<number> }) {
  if (phase === "aging") return <AgingCopy year={year} />;
  if (phase === "disability") return <DisabilityCopy />;
  return <WealthCopy />;
}

function useBoomerYear() {
  const progress = useProgress(AGING_SECONDS, 0.9);
  return useTransform(progress, (value) => FIRST_BOOMER_RETIRES + value * (boomers.value - FIRST_BOOMER_RETIRES));
}

export function BoomersSlide({ step }: SlideProps) {
  const phase = boomerPhases[Math.min(step, boomerPhases.length - 1)];
  const year = useBoomerYear();
  const showsMoney = phase === "wealth";

  return (
    <div className="deck-gutter flex h-full flex-col justify-center gap-deck-rise">
      <div className="min-h-deck-copy">
        <AnimatePresence mode="wait" initial={false}>
          <motion.div key={phase} initial="enter" animate="present" exit="exit">
            <BoomerCopy phase={phase} year={year} />
          </motion.div>
        </AnimatePresence>
      </div>
      <div className="flex items-end justify-center gap-deck-gap">
        <BoomerCrowd phase={phase} year={year} />
        <AnimatePresence>
          {showsMoney && (
            <motion.div
              key="moon"
              layout
              initial="enter"
              animate="present"
              exit="exit"
              className="aspect-[8/9] h-deck-stage"
            >
              <MoonStacks />
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}
