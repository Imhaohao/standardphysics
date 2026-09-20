# Running Standard Physics for real shops

Two Fly apps from the one image in `Dockerfile`. `standardphysics-api` holds
the scans and runs the reconstruction worker; `standardphysics-web` serves the
workspace and proxies `/api` to the API over Fly's private network.

The phone talks to the API directly rather than through the workspace, because
a scan bundle can reach the 1 GB ceiling in `Settings.max_artifact_bytes` and
there is no reason to push that through a Next rewrite.

```
 iPhone ──── https://standardphysics-api.fly.dev ──┐
                                                   ├── API + worker + /data volume
 Browser ─── https://standardphysics-web.fly.dev ──┘   (private 6PN hop)
```

## Before the first deploy

You need the Fly CLI and an account with a card on file. Volumes and always-on
machines are not in the free allowance.

```bash
brew install flyctl
fly auth login
```

Create both apps without deploying, so the secrets are in place before any
code runs:

```bash
fly apps create standardphysics-api
fly apps create standardphysics-web
```

## Secrets

Only the API reads these. The workspace holds no keys.

```bash
fly secrets set --app standardphysics-api \
  APP_SESSION_SECRET="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')" \
  OPENROUTER_API_KEY=... \
  OPENROUTER_MODEL=openai/gpt-6-astra \
  DISCOVERY_API_KEY=... \
  DISCOVERY_BASE_URL=... \
  DISCOVERY_MODEL=...
```

Set a spend limit on the OpenRouter account before the first shop scans
anything, and turn on zero data retention. Every scan sends photographs of
somebody's business to that endpoint.

`WANDB_API_KEY`, `WANDB_ENTITY` and `WANDB_PROJECT` are optional. Without them
the server runs untraced, which is the right setting for a deployment holding
real shops.

## Deploy

Both commands run from the repository root, because the build context is the
whole repo:

```bash
fly deploy --config deploy/fly/api.toml --dockerfile Dockerfile .
fly deploy --config deploy/fly/web.toml --dockerfile Dockerfile .
```

The first API deploy creates the 10 GB volume named in `[[mounts]]`. Check it
came up:

```bash
curl https://standardphysics-api.fly.dev/health
fly logs --app standardphysics-api
```

## One machine, on purpose

The database is SQLite on the volume and the worker claims jobs from it, so a
second machine would be a second database and two workers racing the same
queue. `fly scale count 1 --app standardphysics-api` is the only correct
number until the store moves to Postgres.

The API also never autostops. A machine stopped for idleness is a machine
stopped in the middle of a reconstruction, since that work happens long after
the upload connection closed. The workspace has no such problem and suspends
when nobody is using it.

## Backups

A volume snapshot is not a database backup: SQLite may be mid-write when the
snapshot is taken. Fly takes daily volume snapshots and keeps them for a set
window, which is a floor to fall back on rather than a plan. Check the
retention on your volume with `fly volumes list`. For a real copy:

```bash
fly ssh console --app standardphysics-api \
  -C "/opt/venv/bin/python -c \"import sqlite3;s=sqlite3.connect('/data/standardphysics.sqlite3');d=sqlite3.connect('/data/backup.sqlite3');s.backup(d)\""
fly sftp get /data/backup.sqlite3 --app standardphysics-api
```

The scan artifacts live beside it under `/data` and are the larger half. Until
they are on object storage, losing the volume loses the rooms.

## Pointing the app at it

The iPhone app ships with both addresses compiled in, set in
`apps/ios/project.yml`:

```
CAPTURE_API_BASE_URL: https://standardphysics-api.fly.dev
CAPTURE_WORKSPACE_BASE_URL: https://standardphysics-web.fly.dev
```

The connection screen stays in the app for development, and an owner never has
to open it. Once the apps answer on a custom domain, change these two values
and ship a build; `AppEnvironment` prefers anything already saved in
`UserDefaults`, so a phone that was pointed at a laptop keeps pointing there
until someone clears it.

## Cost

Four things are billed, and only the last one moves with use:

| | |
|---|---|
| API machine | shared-cpu-2x, 2 GB, never stopped |
| Workspace machine | shared-cpu-1x, 1 GB, suspended when idle |
| Volume | 10 GB |
| Model calls | per scan |

Fly prices the machines and the volume, and `fly platform vm-sizes` plus their
calculator give the current numbers. Measure the model calls yourself with
`scripts/scan_cost.py`, which reads what OpenRouter actually billed for one
scan rather than estimating it.
