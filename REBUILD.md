# Standard Physics v2 (branch `tarun-rebuild`)

A ground-up rebuild. The old code under `apps/`, `packages/`, `services/` stays on this branch only as reference while v2 is built, and is removed before the branch is proposed for merge. **Do not import or copy-paste from it**; read it to understand behaviour, then write v2 cleanly. The one deliberate exception is the web homepage look (paper, ink brush, blueprint sheet), which must be reproduced faithfully (see `web/`).

## Goals (from Tarun)
1. Live understanding: while scanning, the user sees what the app recognises (rooms, walls, doors, objects, measurements, provisional pass/fail).
2. Scans survive interruptions (Control Center, app switcher, calls, notifications, app kill) and can be resumed.
3. Full processing + compliance verification in **under 60 s after the user taps Finish**, with no corners cut: every detected object is checked against every rule that applies to it.
4. Rules: 2010 ADA Standards + California (CBC Chapter 11B, current edition; Unruh Act noted as the enforcement hook). Federal and California results are reported separately and the stricter one governs.
5. Keep the paintbrush + blueprint homepage aesthetic.
6. Efficient everywhere: Rust where it helps, tests and benchmarks before claims.

## Layout
| Dir | What | Language |
|---|---|---|
| `rules/` | The rulepack as data: one JSON file per jurisdiction + metric catalog + precedents. Source of truth for every threshold and citation. | JSON |
| `core/` | Cargo workspace. `sp-core`: scene model, geometry, occupancy grids, routing, metric extraction, rule evaluation. `sp-ffi`: UniFFI bindings for Swift. `sp-bench`: criterion benches. | Rust |
| `server/` | `sp-server` (axum): scans, presigned multipart uploads to R2/S3, WebSocket live findings, Postgres (sqlx), jobs, vision labelling client. Deployed on Modal (`server/deploy/modal_app.py`). | Rust (+ tiny Python deploy shim) |
| `ios/` | New SwiftUI capture app, Swift 6, iOS 26+, LiDAR iPhones. Built on Tarun's Mac. | Swift |
| `web/` | New Next.js app: homepage (ink/blueprint), shop list, 3D model, findings report, live scan view. | TypeScript |

## Shared contracts
- **Scene** (`core/sp-core/src/scene.rs` is the source of truth; JSON Schema exported to `core/schema/scene.schema.json`, TS types generated for `web/`, Swift gets types via UniFFI). Units: metres, radians, right-handed, Y up, floor at y=0 per storey.
  - `Scene { version, rooms: [Room], connections: [RoomConnection], observations: [Observation] }`
  - `Room { id, name, kind (shop|restaurant|restroom|office|corridor|kitchen|storage|other), floor: Polygon2 (XZ), ceiling_height, walls: [Wall], openings: [Opening], objects: [Object] }`
  - `Opening { id, kind (door|window|opening), wall_id, center: Vec3, width, height, swing: Option<DoorSwing>, hardware: Option<String> }`
  - `Object { id, category (string from rules/metrics.json `object_categories`), center: Vec3, size: Vec3 (w,h,d), yaw, top_height, confidence, source (roomplan|detector|mesh|owner) , attributes: map }`
  - `Observation { id, subject_id, metric, value, unit, source (measured|photo|owner), confidence }` for things not derivable from boxes (e.g. sign text, Braille present, door opening force reported by owner).
- **Rule** (`rules/schema/rule.schema.json`): `{ id, jurisdiction ("ADA2010"|"CBC11B"), section, title, applies_to: [category or element], scoping: text + optional machine condition, test: one of {"measure": {metric, op (<=,>=,<,>,between,==), value|[lo,hi], unit}} | {"presence": {...}} | {"question": {prompt, pass_answer}} | {"photo": {...}}, evidence: measured|photo|owner, tolerance, source_url, notes }`.
- **Metric catalog** (`rules/metrics.json`): every metric name a rule may use, its unit, the element it is measured on, and how it is derived. `sp-core` must implement an extractor for every metric; a test fails if any rule references a metric with no extractor, or any applicable section has no rule.
- **Finding**: `{ rule_id, jurisdiction, section, subject_id, status (pass|fail|needs_info|not_applicable), measured: Option<{value, unit}>, required, message, evidence }`. Unknowns are `needs_info`, never `pass`.

## Performance budget (after Finish)
Final upload ≤10 s (data streamed during scan), merge + routes ≤5 s, full rule evaluation ≤5 s, leftover labelling ≤20 s, report ≤5 s. `sp-core` target: full evaluation of a 10-room scene in <500 ms on one core.

## Conventions
- Every module ships with tests. Rust: `cargo test`, `cargo clippy -D warnings`, `cargo fmt`. Web: `pnpm test`, `tsc --noEmit`, eslint. iOS: XCTest.
- No secrets in the repo. Config by env vars documented in each component's README.
- Commits on `tarun-rebuild` only; never push to `master`.
