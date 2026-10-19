import "server-only";
import { notFound } from "next/navigation";
import { ownerApi } from "@/lib/session";
import { loadShopSheet } from "@/lib/shopSheet";

/** The shop sheet for a scan the signed-in owner can see, or the 404 page. */
export async function loadOwnedShop(scanId: string) {
  const { api, token } = await ownerApi();
  const scan = await api.getScan(scanId);
  if (!scan) notFound();
  return { sheet: await loadShopSheet(api, scan), token };
}
