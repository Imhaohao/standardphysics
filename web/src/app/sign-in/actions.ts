"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getApi } from "@/lib/api/client";
import { authError, type AuthMode } from "@/lib/authErrors";
import type { AuthResponse } from "@/lib/api/types";
import { SESSION_COOKIE, sessionToken } from "@/lib/session";

export interface SignInState {
  error: string | null;
  email: string;
  mode: AuthMode;
}

const MISSING_FIELDS: Record<AuthMode, string> = {
  "sign-in": "Enter the email and password you use in the app.",
  "sign-up": "Enter an email and a password for your new account.",
};

async function startSession(session: AuthResponse) {
  (await cookies()).set(SESSION_COOKIE, session.token, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    path: "/",
    expires: new Date(session.expires_at),
  });
}

/** Signs in, or creates an account and signs in to it, depending on the form's mode. */
export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const mode: AuthMode = form.get("mode") === "sign-up" ? "sign-up" : "sign-in";
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: MISSING_FIELDS[mode], email, mode };
  try {
    const api = getApi();
    await startSession(await (mode === "sign-up" ? api.register(email, password) : api.login(email, password)));
  } catch (error) {
    return { error: authError(error, mode), email, mode };
  }
  redirect("/shops");
}

/** Deletes the owner's account with every scan and file in it, then signs out. Resolves to an error if it failed. */
export async function deleteAccount() {
  const token = await sessionToken();
  if (!token) redirect("/sign-in");
  try {
    await getApi(token).deleteAccount();
  } catch {
    return "We couldn't delete your account just now. Try again in a minute.";
  }
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/");
}

export async function signOut() {
  const token = await sessionToken();
  if (token) await getApi(token).logout().catch(() => undefined);
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/");
}
