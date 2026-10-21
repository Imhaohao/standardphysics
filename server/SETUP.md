# Backend setup

This guide takes the server (`sp-server`) from nothing to running on the internet, written for someone who has never done it before. The server is the part of Standard Physics that stores scans, checks them against the ADA and California rules, and sends results back to the iPhone app and the website.

It needs three outside services, each free to start:

| Service | What it does for us | Status |
| --- | --- | --- |
| Neon | The database: accounts, scans, rooms and findings | Connected (project `restless-pond-73109557` in `aws-us-east-1`, next to Modal's servers) |
| Cloudflare R2 | File storage: room scans and 3D meshes uploaded from the phone | Connected (bucket `standard-physics-scans`) |
| Modal | Runs the server on the internet so the phone can reach it | Live at `https://tyadgirkar--sp-server-serve.us-east.modal.run`, sleeping when idle |

Every secret (passwords, keys) lives in a file called `.env.local` on your Mac or in Modal's secret settings. Git ignores every `.env` and `.env.*` file in this repository, so they never reach GitHub. Never paste a secret into chat, an issue or a commit.

## 1. Open Terminal in the repository

Open the Terminal app (Cmd+Space, type "Terminal", Enter) and run:

```sh
cd ~/TarunsCode/"standard physics"/standardphysics
```

Every command below starts from this folder unless it says otherwise.

## 2. Cloudflare R2 (file storage)

1. In the Cloudflare dashboard, open R2 Object Storage. The bucket `standard-physics-scans` already exists. Leave it private.
2. Click Manage API Tokens, then Create Account API token. An account token belongs to the Cloudflare account rather than to your login, so it keeps working if your login changes.
3. Name it `standard-physics-server`, give it Object Read & Write, limit it to the bucket `standard-physics-scans`, and create it.
4. Cloudflare shows two values once: the Access Key ID and the Secret Access Key. The server needs only those two.
5. Put them in `server/.env.local`, a file only you can read:

   ```sh
   cd server
   touch .env.local && chmod 600 .env.local
   nano .env.local
   ```

   Paste the block below and replace the two `PASTE_…` values. Use no spaces and no quotes. Save with Ctrl+O then Enter, and close with Ctrl+X.

   ```sh
   S3_ENDPOINT=https://3a62492c4b6146cecd61f746a9ee2707.r2.cloudflarestorage.com
   S3_BUCKET=standard-physics-scans
   S3_REGION=auto
   S3_ACCESS_KEY_ID=PASTE_ACCESS_KEY_ID
   S3_SECRET_ACCESS_KEY=PASTE_SECRET_ACCESS_KEY
   APPLE_BUNDLE_ID=com.tarunyadgirkar.standardphysics
   ```

6. Check that git ignores it. This should print `.env.local`:

   ```sh
   git check-ignore .env.local
   cd ..
   ```

The phone uploads straight to R2 through short-lived links the server signs, so the bucket needs no public access and no CORS rules. The iPhone app's release build only accepts links on `3a62492c4b6146cecd61f746a9ee2707.r2.cloudflarestorage.com` (set in `ios/project.yml`).

## 3. Neon (the database)

1. Install the Neon tool once:

   ```sh
   npm i -g neon@latest
   ```

2. Link this repository to the Neon project and create the config file `neon.ts`:

   ```sh
   neon init -y --org-id org-plain-math-89839281 --project-id restless-pond-73109557 --branch production --services postgres
   ```

   If a browser window opens asking you to sign in to Neon, finish signing in there.

3. Provision the database and write its address into `.env.local` in the repository folder:

   ```sh
   neon deploy
   ```

4. Copy the database address into the server's file too, so the server and Modal read everything from one place. Neon gives two addresses. The server needs the direct one, whose host does not contain `-pooler`, because the server's database migrations take a lock that Neon's pooler does not keep. In the Neon dashboard, open Connect, turn Connection pooling off, copy the connection string, and add this line to `server/.env.local` with `nano server/.env.local`:

   ```sh
   DATABASE_URL=postgresql://neondb_owner:PASSWORD@ep-old-paper-b86pzice.c-14.us-east-1.aws.neon.tech/neondb?sslmode=require
   DB_MAX_CONNECTIONS=5
   ```

   Keep the database in the same region as the server. Modal runs this app in the US East, so the project lives in `aws-us-east-1`; with the database in Oregon every request crossed the country and took several times longer.

   `DB_MAX_CONNECTIONS=5` keeps the total under Neon's connection limit when Modal runs several copies of the server.

The server creates its own tables the first time it starts (`RUN_MIGRATIONS` is on by default).

## 4. Check it on your Mac

Start the server with the values from `server/.env.local`:

```sh
cd server
set -a; source .env.local; set +a
cargo run --release -- serve
```

In a second Terminal window, ask it whether the database and the bucket both answer:

```sh
curl -s http://localhost:8080/health/ready
```

A healthy server answers `{"database":true,"storage":true}`. A `false` points at the service to check (see the table at the end). Press Ctrl+C in the first window to stop it.

## 5. Modal (running the server on the internet)

1. Make an account at modal.com.
2. Install the Modal tool and sign in. The second command opens a browser to approve the login:

   ```sh
   uv tool install modal --with python-dotenv
   modal setup
   ```

3. Give Modal the server's secrets. This copies `server/.env.local` into a Modal Secret named `sp-server`; nothing is printed:

   ```sh
   modal secret create sp-server --from-dotenv server/.env.local
   ```

   To change a value later, edit `server/.env.local` and run the same command with `--force` added.

4. Deploy. With `MIN_CONTAINERS=0` the server sleeps when nobody uses it and costs nothing then; the first request after a sleep takes about 7 seconds. `MIN_CONTAINERS=1` keeps one copy always running (roughly $30 to $35 of Modal credit a month):

   ```sh
   MIN_CONTAINERS=0 modal deploy server/deploy/modal_app.py
   ```

   Modal builds `server/Dockerfile.modal`, a copy of the server image on Debian slim, because Modal needs a shell inside the image.

   Modal prints the server's web address, which looks like `https://YOUR-WORKSPACE--sp-server-serve.modal.run`.

5. Check it:

   ```sh
   curl -s https://YOUR-WORKSPACE--sp-server-serve.modal.run/health/ready
   ```

## 6. Point the apps at the server

| App | Where | Setting |
| --- | --- | --- |
| iPhone, release builds | `ios/project.yml`, `configs: Release:` | `SP_API_BASE_URL: https://YOUR-WORKSPACE--sp-server-serve.modal.run` |
| iPhone, debug builds | `ios/project.yml`, `configs: Debug:` | `http://localhost:8080` while testing on the Mac; the Modal address to test against the real server |
| Website | the website's environment | `NEXT_PUBLIC_SP_API_URL=https://YOUR-WORKSPACE--sp-server-serve.modal.run` |
| Server | `server/.env.local`, then step 5.3 again | `CORS_ALLOWED_ORIGINS=https://standardphysics.app` (the website's address) |

The address `api.standardphysics.app` still points at the old v1 server. Once the Modal server is checked, move that name to Modal with Modal's custom domain settings and switch the apps back to `https://api.standardphysics.app`.

## 7. Optional extras

| Variable | What it turns on |
| --- | --- |
| `LABEL_API_KEY` | Names objects the phone could not identify, using an image model (OpenRouter by default). Without it those objects become questions for the owner. |
| `LOG_FORMAT=json` | Structured logs, already set inside the container |

The full list of settings is in `server/README.md`.

## When something goes wrong

| What you see | What it means | Fix |
| --- | --- | --- |
| `DATABASE_URL` or `S3_…` "is required" | A line is missing from `server/.env.local` | Add it, then restart (or re-run step 5.3 for Modal) |
| `must be https` | The storage address starts with `http://` | Use the `https://…r2.cloudflarestorage.com` address |
| Migrations hang or fail with a lock error | `DATABASE_URL` is the pooled address | Use the direct address, without `-pooler` |
| `/health/ready` says storage is not ready | Wrong key, or the token is not allowed on this bucket | Make a new R2 token limited to `standard-physics-scans` |
| The phone says it can't upload | The upload link's host is not on the app's list | Check `SP_STORAGE_HOSTS` in `ios/project.yml` |
