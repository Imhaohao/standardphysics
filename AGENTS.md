Commit to git whenever a feature is finished and verified (typecheck + tests pass), without waiting to be asked. One commit per feature, message describing the change. Use the default git user. Branch first if on the default branch.

This file is the authority on how work reaches master. [`docs/archive/AGENT_PROTOCOL.md`](docs/archive/AGENT_PROTOCOL.md) and [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) link here instead of repeating it.

master is the only shared branch. Pull master before you start, branch from it for your own work, and merge that branch back into master when it's done. Don't build on someone else's branch, and don't start a new long-lived integration branch; if two branches need combining, merge each into master instead.

## Running here

Install `python3.12-venv` before creating `.venv`. The image Python has no ensurepip until that package is present. `./start.sh` installs the lockfile into `.venv`, installs `apps/web`, and serves the API on port 8787 and the workspace on port 3000. Open the workspace at http://localhost:3000. Next.js refuses the dev hot-reload socket for http://127.0.0.1:3000, and the buttons on that origin do nothing. `SP_SEED_SAMPLE_SHOP=1` puts the sample shop on demo@standardphysics.app and, on the run that creates the account, writes the password to `services/api/var/demo-password`. That shop can be read without Blender.
