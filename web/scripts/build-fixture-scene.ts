import { readFileSync, writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { sceneFromCapturedRoom, type CapturedRoom } from "../src/lib/scene/roomplan.ts";

const source = fileURLToPath(new URL("../fixtures/roomplan/apple_livingroom.room.json", import.meta.url));
const target = fileURLToPath(new URL("../src/fixtures/sample-scene.json", import.meta.url));

const raw = JSON.parse(readFileSync(source, "utf8")) as CapturedRoom;
const scene = sceneFromCapturedRoom(raw);
const rounded = JSON.stringify(scene, (_, value: unknown) => (typeof value === "number" ? Math.round(value * 1e4) / 1e4 : value), 2);
writeFileSync(target, `${rounded}\n`);
console.log(`Wrote ${target}`);
