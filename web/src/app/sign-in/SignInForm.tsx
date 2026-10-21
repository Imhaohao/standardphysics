"use client";

import { SignIn, UserPlus } from "@phosphor-icons/react";
import { useActionState, useState } from "react";
import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { Notice } from "@/components/ui/Notice";
import type { AuthMode } from "@/lib/authErrors";
import { signIn, type SignInState } from "./actions";

const MODES: Record<AuthMode, { heading: string; submit: string; pending: string; password: string; icon: typeof SignIn; switchPrompt: string; switchLabel: string; other: AuthMode }> = {
  "sign-in": {
    heading: "Sign in",
    submit: "Sign in",
    pending: "Signing in",
    password: "current-password",
    icon: SignIn,
    switchPrompt: "New to Standard Physics?",
    switchLabel: "Create an account",
    other: "sign-up",
  },
  "sign-up": {
    heading: "Create an account",
    submit: "Create account",
    pending: "Creating your account",
    password: "new-password",
    icon: UserPlus,
    switchPrompt: "Already have an account?",
    switchLabel: "Sign in instead",
    other: "sign-in",
  },
};

/** One form for both ways in. Switching mode keeps the email that's already typed. */
export function SignInForm() {
  const [state, action, pending] = useActionState<SignInState, FormData>(signIn, { error: null, email: "", mode: "sign-in" });
  const [chosenMode, setChosenMode] = useState<AuthMode | null>(null);
  const mode = chosenMode ?? state.mode;
  const copy = MODES[mode];
  const showError = state.error && state.mode === mode;
  return (
    <form action={action} data-ink-avoid className="flex flex-col gap-4 border border-ink bg-paper p-6">
      <h2 className="heading-display text-2xl">{copy.heading}</h2>
      <input type="hidden" name="mode" value={mode} />
      <TextField label="Email" name="email" type="email" autoComplete="email" required defaultValue={state.email} />
      <TextField
        key={mode}
        label="Password"
        hint={mode === "sign-up" ? "At least 8 characters." : undefined}
        name="password"
        type="password"
        autoComplete={copy.password}
        minLength={mode === "sign-up" ? 8 : undefined}
        required
      />
      {showError && <Notice tone="error">{state.error}</Notice>}
      <Button type="submit" variant="primary" disabled={pending} className="justify-center">
        <copy.icon size={18} aria-hidden />
        {pending ? copy.pending : copy.submit}
      </Button>
      <p className="flex flex-wrap items-center gap-x-1 text-sm text-ink-muted">
        {copy.switchPrompt}
        <button type="button" onClick={() => setChosenMode(copy.other)} className="pressable font-medium text-ink underline decoration-ink/30 underline-offset-4 hover:decoration-ink">
          {copy.switchLabel}
        </button>
      </p>
      {mode === "sign-in" && <p className="text-sm text-ink-muted text-pretty">Use the same account as the Standard Physics app on your iPhone.</p>}
    </form>
  );
}
