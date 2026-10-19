import "server-only";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { getApi } from "@/lib/api/client";
import { isFixtureMode } from "@/lib/api/config";

export const SESSION_COOKIE = "sp_session";

export async function sessionToken() {
  return (await cookies()).get(SESSION_COOKIE)?.value ?? null;
}

/** The API as the signed-in owner. Without a session it sends people to sign in, except in fixture mode. */
export async function ownerApi() {
  const token = await sessionToken();
  if (!token && !isFixtureMode()) redirect("/sign-in");
  return { api: getApi(token), token };
}
