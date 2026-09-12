"use client";

import { Printer } from "@phosphor-icons/react";
import { Button } from "./ui/Button";

export function PrintButton() {
  return (
    <Button variant="primary" onClick={() => window.print()}>
      <Printer size={18} weight="bold" aria-hidden />
      Print this report
    </Button>
  );
}
