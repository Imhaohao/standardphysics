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
| `NEXT_PUBLIC_SP_FIXTURES` | `1` serves the sample shop built from `fixtures/roomplan/apple_livingroom.room.json` |
| `NEXT_PUBLIC_SP_API_URL` | sp-server's origin, default `http://localhost:8080` |

## Pages

- `/` is the home sheet. Signed out, it shows the sample shop and a sign-in link.
- `/sign-in` stores the server's token in an httpOnly `sp_session` cookie.
- `/shops` lists the owner's scans.
- `/shops/{id}` shows the 3D model and the inked plan with findings pinned in both.
- `/shops/{id}/report` is the printable report, grouped by element, with ADA and CBC 11B side by side.
- `/shops/{id}/live` follows `/v1/scans/{id}/live` and inks walls and doors as they arrive.

All server calls go through `src/lib/api/client.ts`. `getScene` asks for `/v1/scans/{id}/scene`, which sp-server does not serve yet, so pages fall back to a "not drawn yet" state when it returns 404. The live socket carries findings but no geometry today, so the live view refetches the scene when findings arrive; the `room` and `scene` message types are ready for when the server sends geometry.

## Ink

`src/lib/brush` is a clean rewrite of the old site's paintbrush (MIT, see `src/lib/brush/LICENSE`). `src/lib/ink` drives it: the frame loop runs only while strokes are drawing, sleeps until the next scheduled stroke, pauses while the tab is hidden and draws instantly under `prefers-reduced-motion`.

## Checks

```sh
pnpm typecheck && pnpm lint && pnpm test
PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers pnpm e2e   # builds and serves in fixture mode on :3107
pnpm fixture:scene                                    # regenerates src/fixtures/sample-scene.json
```
