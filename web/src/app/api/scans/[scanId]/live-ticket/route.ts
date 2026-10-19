import { NextResponse } from "next/server";
import { ApiError, getApi } from "@/lib/api/client";
import { apiBaseUrl, isFixtureMode, liveSocketUrl } from "@/lib/api/config";
import { sessionToken } from "@/lib/session";

/**
 * Trades the httpOnly session cookie for a single-use live ticket and answers with the socket URL to open,
 * so the session token never reaches browser JavaScript.
 */
export async function POST(_request: Request, { params }: RouteContext<"/api/scans/[scanId]/live-ticket">) {
  const token = await sessionToken();
  if (!token || isFixtureMode()) return NextResponse.json({ error: "unauthorized", message: "Sign in to follow a scan." }, { status: 401 });
  const { scanId } = await params;
  try {
    const { ticket, expires_in_secs: expiresInSecs } = await getApi(token).createLiveTicket(scanId);
    return NextResponse.json({ url: liveSocketUrl(apiBaseUrl(), scanId, ticket), expires_in_secs: expiresInSecs }, { headers: { "Cache-Control": "no-store" } });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 502;
    return NextResponse.json({ error: "live_ticket", message: "We couldn't open the live view for this scan." }, { status });
  }
}
