"use client";

import { motion } from "motion/react";
import type { ReactNode } from "react";
import { easeSweep, exitTransition } from "@/lib/motion";

type ScanWipeProps = {
  children: ReactNode;
  delay?: number;
  duration?: number;
};

export function ScanWipe({ children, delay = 0, duration = 1.4 }: ScanWipeProps) {
  const timing = { duration, delay, ease: easeSweep };
  return (
    <span className="relative block">
      <motion.span
        className="block"
        variants={{
          enter: { clipPath: "inset(-10% 100% -10% 0%)" },
          present: { clipPath: "inset(-10% 0% -10% 0%)", transition: timing },
          exit: { opacity: 0, transition: exitTransition },
        }}
      >
        {children}
      </motion.span>
      <motion.span
        aria-hidden
        className="scan-bar"
        variants={{
          enter: { left: "0%", opacity: 0 },
          present: {
            left: "100%",
            opacity: [0, 1, 1, 0],
            transition: { ...timing, opacity: { duration, delay, times: [0, 0.08, 0.85, 1] } },
          },
          exit: { opacity: 0, transition: exitTransition },
        }}
      />
    </span>
  );
}
