"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { ApiError, getApi } from "@/lib/api/client";
import { SESSION_COOKIE, sessionToken } from "@/lib/session";

export interface SignInState {
  error: string | null;
  email: string;
}

function signInError(error: unknown) {
  if (error instanceof ApiError && (error.status === 401 || error.status === 400)) return "That email and password don't match an account. Check them and try again.";
  return "We couldn't reach Standard Physics just now. Try again in a minute.";
}

export async function signIn(_previous: SignInState, form: FormData): Promise<SignInState> {
  const email = String(form.get("email") ?? "").trim();
  const password = String(form.get("password") ?? "");
  if (!email || !password) return { error: "Enter the email and password you use in the app.", email };
  try {
    const session = await getApi().login(email, password);
    (await cookies()).set(SESSION_COOKIE, session.token, {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      path: "/",
      expires: new Date(session.expires_at),
    });
  } catch (error) {
    return { error: signInError(error), email };
  }
  redirect("/shops");
}

export async function signOut() {
  const token = await sessionToken();
  if (token) await getApi(token).logout().catch(() => undefined);
  (await cookies()).delete(SESSION_COOKIE);
  redirect("/");
}
