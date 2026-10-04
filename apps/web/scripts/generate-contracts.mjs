import { execFileSync } from "node:child_process";
import { existsSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { compile } from "json-schema-to-typescript";

const webRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = join(webRoot, "..", "..");
const localPython = join(repoRoot, ".venv", "bin", "python");
const python = process.env.PYTHON ?? (existsSync(localPython) ? localPython : "python3");

function runPython(module) {
  return execFileSync(python, ["-m", module], { cwd: repoRoot, encoding: "utf8" });
}

const schema = JSON.parse(runPython("standardphysics_contracts.json_schema"));

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

// The tolerances and limits a dragged piece is checked against, read from the
// Python modules that define them, so the browser never keeps its own copy.
writeFileSync(join(webRoot, "src", "types", "geometry-rules.ts"), runPython("standardphysics_agents.fix.geometry_rules"));
