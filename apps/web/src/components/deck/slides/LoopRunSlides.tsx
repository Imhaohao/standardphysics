"use client";

import { motion, type Variants } from "motion/react";
import { facts } from "@/lib/facts";
import { easeDrawn, exitTransition } from "@/lib/motion";
import { FinePrint, MaskedLines } from "../primitives";
import type { SlideProps } from "../slides";

const run = facts.loopRunOnDemoShop;
const evaluation = facts.loopEvaluation;

function PassCard({ pass, index, step }: { pass: (typeof run.passes)[number]; index: number; step: number }) {
  const reached = index <= step;
  const current = index === step;
  return (
    <motion.li
      initial={false}
      animate={{ opacity: reached ? 1 : 0.18, y: reached ? 0 : 16, scale: current ? 1 : 0.97 }}
      transition={{ duration: 0.5, ease: easeDrawn }}
      className={`flex flex-col gap-deck-hairline p-deck-hairline shadow-md ${current ? "bg-ink text-paper" : "bg-paper-raised text-ink"}`}
    >
      <p className="font-display text-caption font-bold opacity-70">
        Pass {index + 1}
      </p>
      <p className={`font-display text-lede font-extrabold ${current ? "text-tape" : ""}`}>{pass.action}</p>
      <p className="font-display text-caption font-bold">{pass.outcome}</p>
      {"shortfallBefore" in pass && (
        <p className="font-display text-caption font-bold figures-tabular opacity-80">
          Re-check passed: {pass.shortfallBefore} in short before, {pass.shortfallAfter} after
        </p>
      )}
    </motion.li>
  );
}

export function LoopRunSlide({ step }: SlideProps) {
  return (
    <div className="deck-gutter flex h-full flex-col justify-center gap-deck-rise">
      <h2 className="font-display text-figure font-extrabold">
        <MaskedLines lines={["One run of the loop on Sara’s shop"]} delay={0.1} />
      </h2>
      <ol className="grid grid-cols-4 items-start gap-deck-hairline">
        {run.passes.map((pass, index) => (
          <PassCard key={pass.action} pass={pass} index={index} step={step} />
        ))}
      </ol>
      <FinePrint delay={0.8}>{run.source}</FinePrint>
    </div>
  );
}

function barGrows(delay: number): Variants {
  return {
    enter: { scaleX: 0 },
    present: { scaleX: 1, transition: { duration: 0.9, ease: easeDrawn, delay } },
    exit: { opacity: 0, transition: exitTransition },
  };
}

const percent = (value: number) => `${Math.round(value * 100)}%`;

function ScoreRow({ scorer, index, showsPipeline }: { scorer: (typeof evaluation.scorers)[number]; index: number; showsPipeline: boolean }) {
  return (
    <div className="flex flex-col gap-deck-hairline">
      <p className="font-display text-lede font-bold">{scorer.name}</p>
      <div className="flex items-center gap-deck-gap">
        <div className="h-deck-hairline flex-1 bg-paper-sunken">
          <motion.div variants={barGrows(0.3 + index * 0.15)} style={{ width: percent(scorer.standIn) }} className="h-full origin-left bg-ink-faint" />
        </div>
        <span className="font-display text-caption font-bold text-ink-muted figures-tabular">{percent(scorer.standIn)}</span>
      </div>
      <div className="flex items-center gap-deck-gap">
        <div className="h-deck-hairline flex-1 bg-paper-sunken">
          <motion.div
            initial={false}
            animate={{ scaleX: showsPipeline ? 1 : 0 }}
            transition={{ duration: 0.9, ease: easeDrawn, delay: showsPipeline ? index * 0.15 : 0 }}
            style={{ width: percent(scorer.pipeline) }}
            className="h-full origin-left bg-tape"
          />
        </div>
        <motion.span initial={false} animate={{ opacity: showsPipeline ? 1 : 0 }} className="font-display text-caption font-extrabold figures-tabular">
          {percent(scorer.pipeline)}
        </motion.span>
      </div>
    </div>
  );
}

export function WeaveScoresSlide({ step }: SlideProps) {
  const showsPipeline = step > 0;
  const error = evaluation.measurementErrorInches;
  return (
    <div className="deck-gutter grid h-full grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)] items-center gap-deck-gap">
      <div className="flex flex-col gap-deck-rise">
        <h2 className="font-display text-figure font-extrabold">
          <MaskedLines lines={["Weave scores", "every change on", `${evaluation.cases} labeled cases.`]} delay={0.1} />
        </h2>
        <p className="font-display text-caption font-bold text-ink-muted">
          <MaskedLines
            key={showsPipeline ? "pipeline" : "stand-in"}
            lines={showsPipeline ? ["Measuring the room for real cut the", `error from ${error.standIn} inches to under 0.01.`] : ["A simplified stand-in measured", `the room ${error.standIn} inches off.`]}
            delay={0.3}
          />
        </p>
        <FinePrint delay={0.9}>{evaluation.source}</FinePrint>
      </div>
      <div className="flex flex-col gap-deck-rise">
        {evaluation.scorers.map((scorer, index) => (
          <ScoreRow key={scorer.name} scorer={scorer} index={index} showsPipeline={showsPipeline} />
        ))}
      </div>
    </div>
  );
}
