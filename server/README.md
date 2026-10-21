# sp-server

axum + Postgres + S3-compatible storage. Scans, presigned multipart uploads, a live WebSocket channel that runs the `sp-core` engine, finish/assessment, a Postgres job queue, and a vision labelling client.

## Run locally

```sh
# Postgres 16 and an S3-compatible store (MinIO shown)
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pw postgres:16
docker run -d -p 9000:9000 -e MINIO_ROOT_USER=minio -e MINIO_ROOT_PASSWORD=minio12345 minio/minio server /data

export DATABASE_URL=postgres://postgres:pw@localhost:5432/postgres
export S3_ENDPOINT=http://localhost:9000 S3_BUCKET=sp S3_ACCESS_KEY_ID=minio S3_SECRET_ACCESS_KEY=minio12345
cargo run -- serve        # migrations run on start (RUN_MIGRATIONS=false to skip)
cargo run -- openapi > openapi.json   # regenerate the spec
```

Create the bucket first. Without Docker, start a Postgres cluster with `initdb`/`pg_ctl` as a non-root user.

## Tests

```sh
export TEST_DATABASE_URL=postgres://postgres@localhost:5432/postgres   # a superuser; each test makes its own database
cargo test
cargo clippy --all-targets -- -D warnings && cargo fmt --check
```

Tests run the real router against Postgres, with in-process fakes for S3 (multipart), Apple JWKS and the labelling API. `tests/health.rs` fails if `openapi.json` is stale.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | required | Postgres URL |
| `DB_MAX_CONNECTIONS` | 10 | pool size |
| `RUN_MIGRATIONS` | true | run sqlx migrations on start |
| `BIND_ADDR` / `PORT` | `0.0.0.0:$PORT`, 8080 | listen address |
| `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | required | storage credentials |
| `S3_ENDPOINT` | AWS | R2: `https://<account>.r2.cloudflarestorage.com`; MinIO URL |
| `S3_PUBLIC_ENDPOINT` | `S3_ENDPOINT` | the one host presigned URLs point at, e.g. `https://<account>.r2.cloudflarestorage.com`; must be https |
| `S3_ALLOW_INSECURE_PUBLIC_ENDPOINT` | false | dev only: allow an http endpoint |
| `S3_REGION` | `auto` | |
| `S3_FORCE_PATH_STYLE` | true when endpoint set | |
| `S3_PRESIGN_TTL_SECS` | 3600 | lifetime of presigned part URLs |
| `UPLOAD_VERIFY_MAX_BYTES` | 67108864 | uploads up to this size are re-hashed server side on complete |
| `APPLE_BUNDLE_ID` | empty (Apple sign-in disabled) | expected `aud` of identity tokens |
| `APPLE_JWKS_URL`, `APPLE_JWKS_TTL_SECS` | appleid.apple.com/auth/keys, 3600 | JWKS source and cache |
| `SESSION_TTL_DAYS` | 90 | |
| `CORS_ALLOWED_ORIGINS` | none | comma-separated origins for the web app |
| `LABEL_API_BASE` | `https://openrouter.ai/api/v1` | any OpenAI-compatible chat-completions API |
| `LABEL_API_KEY` | unset (labelling off) | |
| `LABEL_MODEL` | `google/gemini-3.8-flash` | must accept image input |
| `LABEL_CONCURRENCY` | 8 | parallel label requests |
| `LABEL_DEADLINE_MS` | 20000 | hard overall labelling deadline |
| `LABEL_REQUEST_TIMEOUT_MS` | 15000 | per request |
| `RUN_JOB_WORKER`, `JOB_POLL_MS` | true, 1000 | in-process job worker |
| `LOG_FORMAT`, `RUST_LOG` | text, info | `json` for structured logs |

## API

The contract is `openapi.json` (also served at `GET /v1/openapi.json`). Everything except `/health*` and `/v1/auth/*` needs `Authorization: Bearer <token>`.

- Auth: `POST /v1/auth/register|login|apple|logout`, `GET /v1/me`. Session tokens are random, returned once, stored as SHA-256.
- Scans: `POST/GET /v1/scans`, `GET /v1/scans/{id}`, `GET /v1/scans/{id}/assessment`, `GET /v1/scans/{id}/scene` (merged sp-core Scene, 404 until a room exists), `POST /v1/scans/{id}/finish`. Another user's scan is always 404.
- Uploads (phone to storage directly):
  1. `POST /v1/scans/{id}/uploads` with `kind, filename, content_type, size_bytes[, part_size >= 5 MiB]` returns the upload and `part_count`.
  2. `POST .../uploads/{uid}/parts` with `part_numbers` returns presigned PUT URLs (and headers to send). Upload each part with a background URLSession.
  3. `GET .../uploads/{uid}` lists parts storage already has, so an interrupted upload resumes by sending only the missing parts. Resume granularity is one part, so choose a small `part_size` (5 MiB) for flaky links.
  4. `POST .../uploads/{uid}/complete` with `sha256` of the whole file. The server assembles from storage's own part list, checks size, re-hashes files up to `UPLOAD_VERIFY_MAX_BYTES`, and records the artifact. A mismatch deletes the object and returns 422.
  5. `POST .../uploads/{uid}/abort`. `GET /v1/scans/{id}/artifacts` lists artifacts.
- Presigned URL host: every URL is path-style on the `S3_PUBLIC_ENDPOINT` host, `https://<account>.r2.cloudflarestorage.com/<bucket>/scans/...?X-Amz-...`; the presign response repeats the host as `host`. The server refuses to hand out a URL on any other host or over http (unless the dev flag is set). Keep `S3_FORCE_PATH_STYLE` consistent (default true with an endpoint).
- Idempotency: `POST /v1/scans` and `POST /v1/scans/{id}/uploads` accept `Idempotency-Key` (1-255 chars). Same key and body within 24 h replays the stored response (header `Idempotent-Replayed: true`); same key with a different body is 409; a request still in flight is 409. Failed requests do not consume the key.
- Apple sign-in: the body must include the raw `nonce`; the token's `nonce` claim must equal its lowercase hex SHA-256. `iss`, `aud` (= `APPLE_BUNDLE_ID`) and `exp` are verified.
- Live: `GET /v1/scans/{id}/live` (WebSocket; native clients send `Authorization: Bearer`; browsers `POST /v1/scans/{id}/live-ticket` and pass the single-use `?ticket=` valid 30 s; session tokens in the query string are rejected; `?role=viewer` for read-only).
  - Client sends `{"type":"room","room_id","final","seq","captured_room":<RoomPlan CapturedRoom JSON>,"observations":[{"id",...}]}` per room and periodically for partials. Observations merge by `id`; `captured_room` replaces. Observations with `center`/`size`/`category` become detector objects in the room; observations with a `metric` are sp-core scene Observations. Detector observations without a `category` may carry `crop_artifact_id` (an uploaded crop) for vision labelling at finish.
  - Server sends `hello` (snapshot), `scene` (merged Scene, after hello and after finish), `room` (converted sp-core Room on every update), `findings` (room findings + running summary + `elapsed_ms`), `report` (after finish), `error`, `pong`. Schemas are in `openapi.json` under `ClientMessage`/`ServerMessage`.
  - Rooms persist per update, so a dropped or restarted connection resumes from Postgres.
- Owner answers: findings that are `needs_info` only because an owner answer or photo is missing carry `ask` (`subject_id`, `metric`, `prompt`, `value_type`, `unit`, `options`, `photo`); ADA and CBC findings sharing `subject_id` + `metric` are one question. `GET /v1/scans/{id}/answers` lists answers; `PUT /v1/scans/{id}/answers` with `{"answers": [{subject_id, metric, value}]}` (`null` deletes) saves them as owner observations and returns the re-evaluated report. Re-evaluation reuses the vision labels saved at finish, so it never calls the labelling API. 409 before the scan is finished.
- Photo answers: upload a photo (`kind: photo`), then `POST /v1/scans/{id}/photo-answers` with `{subject_id, metric, artifact_id}` for an open `ask`. The vision model (`LABEL_*`) answers the question from the photo; a reading with confidence of at least 0.6 is saved as an answer with `source: photo` and the report is re-evaluated. The response is `{answered, answer, confidence, report}`; `answered: false` means the photo was unclear. 409 when no `LABEL_API_KEY` is set.
- Scan edits: `PATCH /v1/scans/{id}` (`name`, `site_name`; a missing field is kept, `site_name: null` clears it), `DELETE /v1/scans/{id}` (rows cascade; stored files are deleted best effort). `DELETE /v1/me` removes the account, its sessions, scans and files.
- Share links: `POST|GET /v1/scans/{id}/shares`, `DELETE /v1/scans/{id}/shares/{token}`. `GET /v1/shared/{token}` needs no auth and returns `{scan, report, scene}`; the web page is `/r/{token}`.
- Health: `/health`, `/health/ready` (database + bucket).

## Finish pipeline

`POST /v1/scans/{id}/finish`: load rooms, vision-label uncategorised crops (bounded parallelism, hard deadline), evaluate with a fresh engine, store the assessment, enqueue `texture_bake`, push `report` to subscribers. Objects the labeller did not resolve in time yield `needs_info` findings (`label.unresolved`) and never block. Per-stage timings are logged (`finish pipeline timings`) and returned in `report.timings`.

## Jobs

Table `jobs`, claimed with `FOR UPDATE SKIP LOCKED`, per-job `deadline_secs`, exponential-backoff retries up to `max_attempts`, then `dead`. A worker that dies leaves an expired lease; another worker re-claims it, or buries it if attempts are exhausted. `texture_bake` is a stub handler.

## Deploy

Build context is the repo root: `docker build -f server/Dockerfile -t sp-server .`

Modal: put the env vars above in a Modal Secret named `sp-server`, then `MIN_CONTAINERS=1 modal deploy server/deploy/modal_app.py` (`MAX_CONTAINERS`, `SCALEDOWN_SECONDS` also read). The app uses `@modal.web_server(8080)`. WebSockets work through Modal web endpoints; set `min_containers >= 1` to avoid cold starts during a scan.
