"use client";

import { SignIn, WarningCircle } from "@phosphor-icons/react";
import { useActionState } from "react";
import { Button } from "@/components/ui/Button";
import { signIn, type SignInState } from "./actions";

const FIELD_CLASS = "w-full rounded-md border border-ink/30 bg-sheet px-3 py-2.5 text-base text-ink outline-none transition-colors focus:border-ink";

export function SignInForm() {
  const [state, action, pending] = useActionState<SignInState, FormData>(signIn, { error: null, email: "" });
  return (
    <form action={action} data-ink-avoid className="flex flex-col gap-4 border border-ink bg-paper p-6">
      <h2 className="heading-display text-2xl">Sign in</h2>
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Email</span>
        <input name="email" type="email" autoComplete="email" required defaultValue={state.email} className={FIELD_CLASS} />
      </label>
      <label className="flex flex-col gap-1.5">
        <span className="text-sm font-medium">Password</span>
        <input name="password" type="password" autoComplete="current-password" required className={FIELD_CLASS} />
      </label>
      {state.error && (
        <p role="alert" className="flex items-start gap-2 text-sm text-problem">
          <WarningCircle size={18} weight="fill" aria-hidden className="mt-px shrink-0" />
          {state.error}
        </p>
      )}
      <Button type="submit" variant="primary" disabled={pending} className="justify-center">
        <SignIn size={18} aria-hidden />
        {pending ? "Signing in" : "Sign in"}
      </Button>
      <p className="text-sm text-ink-muted text-pretty">Use the same account as the Standard Physics app on your iPhone.</p>
    </form>
  );
}
