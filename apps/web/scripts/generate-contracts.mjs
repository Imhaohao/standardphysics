import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(webRoot, "..", "..");
const localPython = join(repoRoot, ".venv", "bin", "python");
const python = process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python3");

const schema = JSON.parse(
  execFileSync(python, ["-m", "standardphysics_contracts.json_schema"], {
    cwd: repoRoot,
    encoding: "utf8",
  }),
);

const banner = [
  "/**",
  " * Generated from packages/contracts by `npm run contracts`. Do not edit.",
  " * Change the Pydantic models instead, then regenerate.",
  " */",
].join("\n");

const typescript = await compile(schema, "StandardPhysicsContracts", {
  bannerComment: banner,
  unreachableDefinitions: true,
  additionalProperties: false,
  maxItems: -1,
});

writeFileSync(join(webRoot, "src", "types", "contracts.ts"), typescript);
