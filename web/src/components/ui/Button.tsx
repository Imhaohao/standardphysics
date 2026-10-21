import type { ComponentProps } from "react";

export type ButtonVariant = "primary" | "quiet" | "outline" | "danger";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-ink text-paper hover:bg-ink/85 px-5 py-3 text-base",
  quiet: "text-ink-muted hover:text-ink hover:bg-ink/5 px-3 py-2 text-sm",
  outline: "border border-ink text-ink hover:bg-ink/5 px-4 py-2.5 text-base",
  danger: "border border-problem text-problem hover:bg-problem/5 px-4 py-2.5 text-base",
};

/** The button look on its own, for a link that should read as a button. Corners stay square, like the sheet. */
export function buttonClassName(variant: ButtonVariant = "quiet") {
  return `pressable inline-flex items-center gap-2 font-medium disabled:cursor-not-allowed disabled:opacity-40 ${VARIANTS[variant]}`;
}

export function Button({ variant = "quiet", className = "", type = "button", ...props }: ComponentProps<"button"> & { variant?: ButtonVariant }) {
  return <button type={type} className={`${buttonClassName(variant)} ${className}`} {...props} />;
}
