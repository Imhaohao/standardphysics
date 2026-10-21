import { readFileSync } from "node:fs";
import { compileFromFile } from "json-schema-to-typescript";
import openapiTS, { astToString } from "openapi-typescript";
import { describe, expect, it } from "vitest";

const SPEC = new URL("../../../../server/openapi.json", import.meta.url);
const GENERATED = new URL("./openapi.gen.ts", import.meta.url);

describe("API contract", () => {
  it("openapi.gen.ts matches server/openapi.json (run pnpm api:types if not)", async () => {
    const expected = astToString(await openapiTS(SPEC));
    expect(readFileSync(GENERATED, "utf8").endsWith(expected)).toBe(true);
  });

  it("scene.gen.ts matches core/schema/scene.schema.json (run pnpm scene:types if not)", async () => {
    const schema = new URL("../../../../core/schema/scene.schema.json", import.meta.url);
    const generated = readFileSync(new URL("../scene/scene.gen.ts", import.meta.url), "utf8");
    const banner = generated.split("\n")[0]!;
    const expected = await compileFromFile(schema.pathname.replaceAll("%20", " "), { additionalProperties: false, bannerComment: banner });
    expect(generated).toBe(expected);
  });

  it("covers every route the client calls", () => {
    const paths = Object.keys((JSON.parse(readFileSync(SPEC, "utf8")) as { paths: Record<string, unknown> }).paths);
    for (const route of ["/v1/auth/login", "/v1/auth/logout", "/v1/scans", "/v1/scans/{scan_id}", "/v1/scans/{scan_id}/scene", "/v1/scans/{scan_id}/assessment", "/v1/scans/{scan_id}/live", "/v1/scans/{scan_id}/live-ticket", "/v1/auth/register", "/v1/me", "/v1/scans/{scan_id}/answers", "/v1/scans/{scan_id}/shares", "/v1/scans/{scan_id}/shares/{token}", "/v1/shared/{token}"]) {
      expect(paths).toContain(route);
    }
  });
});
