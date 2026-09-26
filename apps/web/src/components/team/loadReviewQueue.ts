import { cookies } from "next/headers";
import { notFound } from "next/navigation";
import { API_ORIGIN } from "@/lib/api-origin";
import { SESSION_COOKIE } from "@/lib/session";
import type { ReviewQueue } from "@/types/contracts";

/** `GET /api/team/reviews`, with the browser's session forwarded by hand the way `lib/api.ts` does. */
export async function loadReviewQueue(): Promise<ReviewQueue> {
  const token = (await cookies()).get(SESSION_COOKIE)?.value;
  const response = await fetch(`${API_ORIGIN}/api/team/reviews`, {
    cache: "no-store",
    headers: token ? { cookie: `${SESSION_COOKIE}=${token}` } : {},
  });
  if (response.status === 403) notFound();
  if (!response.ok) throw new Error(`/api/team/reviews answered ${response.status}`);
  return (await response.json()) as ReviewQueue;
}
