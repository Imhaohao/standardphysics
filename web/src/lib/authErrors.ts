import { ApiError } from "@/lib/api/client";

export type AuthMode = "sign-in" | "sign-up";

const UNREACHABLE = "We couldn't reach Standard Physics just now. Try again in a minute.";

const SIGN_IN_ERRORS: Record<number, string> = {
  400: "That email and password don't match an account. Check them and try again.",
  401: "That email and password don't match an account. Check them and try again.",
};

const SIGN_UP_ERRORS: Record<number, string> = {
  409: "There's already an account with that email. Sign in instead.",
};

/** sp-server answers a bad sign-up with 400 and says whether the email or the password was the problem. */
function badSignUp(error: ApiError) {
  return /password/i.test(error.message) ? "Use a password between 8 and 256 characters." : "That email address doesn't look right. Check it and try again.";
}

/** What to tell someone whose sign-in or sign-up sp-server turned down. */
export function authError(error: unknown, mode: AuthMode) {
  if (!(error instanceof ApiError)) return UNREACHABLE;
  if (mode === "sign-up" && error.status === 400) return badSignUp(error);
  return (mode === "sign-up" ? SIGN_UP_ERRORS : SIGN_IN_ERRORS)[error.status] ?? UNREACHABLE;
}
