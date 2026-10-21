# web

The Standard Physics website: Next.js 16, React 19, Tailwind 4 and react-three-fiber.

## Running it

```sh
pnpm install
pnpm dev             # talks to sp-server
pnpm dev:fixtures    # renders the bundled sample shop and never calls the API
```

| Variable | Meaning |
| --- | --- |
| `NEXT_PUBLIC_SP_FIXTURES` | `1` serves the sample shop captured from `fixtures/roomplan/apple_livingroom.room.json` |
| `NEXT_PUBLIC_SP_API_URL` | sp-server's origin, default `http://localhost:8080` |

## Pages

- `/` is the home sheet. Signed out, it shows the sample shop and a sign-in link.
- `/sign-in` signs in or creates an account, and stores the server's token in an httpOnly `sp_session` cookie.
- `/shops` lists the owner's scans.
- `/shops/{id}` shows the 3D model and the inked plan with findings pinned in both, with Rename and Delete scan.
- `/shops/{id}/report` is the printable report, grouped by element, with ADA and CBC 11B side by side. Owners answer its questions there (`PUT /v1/scans/{id}/answers`), make read-only links, and see what the rulepack covers, read from `rules/coverage.json` at build time.
- `/r/{token}` is a read-only report for anyone with the link, from `GET /v1/shared/{token}`.
- `/privacy` is the privacy policy, linked under every sheet.

`next.config.ts` sets the Turbopack root to the repo root so `rules/coverage.json` can be imported. In fixture mode, edits, answers and share links live in the server's memory until it restarts.
- `/shops/{id}/live` follows `/v1/scans/{id}/live` and inks walls and doors as they arrive.

All server calls go through `src/lib/api/client.ts`. Wire types are generated, never written by hand:

- `pnpm api:types` regenerates `src/lib/api/openapi.gen.ts` from `server/openapi.json`.
- `pnpm scene:types` regenerates `src/lib/scene/scene.gen.ts` from `core/schema/scene.schema.json`.

A unit test fails when either generated file is stale.

The live view follows the socket's `hello`, `room`, `scene`, `findings` and `report` frames. Before each connect or reconnect, the browser calls this app's `POST /api/scans/{id}/live-ticket`. That route reads the httpOnly session cookie and asks sp-server for a single-use ticket, then returns the `?ticket=` socket URL. The session token never reaches browser JavaScript. A finished scan is replayed from its saved scene and report instead.

## Sample shop

`src/fixtures/sample-scene.json` and `sample-report.json` are real sp-server output. To regenerate them, start sp-server and run `pnpm fixture:capture --api http://localhost:8080`. The script signs up a sample owner, streams the RoomPlan room over the live socket, finishes the scan and saves the scene and assessment.

## Ink

`src/lib/brush` is a clean rewrite of the old site's paintbrush (MIT, see `src/lib/brush/LICENSE`). `src/lib/ink` drives it: the frame loop runs only while strokes are drawing, sleeps until the next scheduled stroke, pauses while the tab is hidden and draws instantly under `prefers-reduced-motion`.

## Checks

```sh
pnpm typecheck && pnpm lint && pnpm test
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm e2e   # builds and serves in fixture mode on :3107
SP_E2E_API=http://localhost:8088 PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm e2e:server   # against a running sp-server
```
