"use client";

import { Printer } from "@phosphor-icons/react";
import { Button } from "@/components/ui/Button";

export function PrintButton() {
  return (
    <Button variant="outline" onClick={() => window.print()}>
      <Printer size={18} aria-hidden />
      Print or save as PDF
    </Button>
  );
}
