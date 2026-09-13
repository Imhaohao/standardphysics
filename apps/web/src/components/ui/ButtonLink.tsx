import Link from "next/link";
import type { ComponentProps } from "react";

type ButtonVariant = "primary" | "quiet";

const variantClassName: Record<ButtonVariant, string> = {
  primary: "bg-ink text-paper hover:bg-ink/85",
  quiet: "bg-paper-raised text-ink shadow-sm hover:bg-paper-sunken",
};

type ButtonLinkProps = ComponentProps<typeof Link> & { variant?: ButtonVariant };

export function ButtonLink({ variant = "primary", className = "", ...props }: ButtonLinkProps) {
  return (
    <Link
      className={`inline-flex h-12 items-center gap-2 rounded-full px-6 text-base font-bold transition-colors ${variantClassName[variant]} ${className}`}
      {...props}
    />
  );
}
