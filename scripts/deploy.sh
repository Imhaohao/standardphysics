#!/usr/bin/env bash
# Deploys what is on master to the Droplet, from here.
#
#   scripts/deploy.sh
#
# One command instead of a session: it pulls on the box, rebuilds, and runs
# doctor.sh, streaming everything back. Set SP_DEPLOY_HOST in your shell if the
# box moves.
#
# It refuses to deploy behind your own work. The Droplet pulls master from
# GitHub, so a commit still sitting on this laptop is not going anywhere, and
# a deploy that silently ships the previous commit is worse than one that
# stops and says so.
set -euo pipefail

HOST="${SP_DEPLOY_HOST:-root@api.standardphysics.app}"
DIR="${SP_DEPLOY_DIR:-/root/standardphysics}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

say() { printf '\n== %s\n' "$1"; }

warn_about_unpushed() {
  cd "$REPO_ROOT"
  git fetch upstream --quiet 2>/dev/null || return 0
  local ahead
  ahead="$(git rev-list --count upstream/master..HEAD 2>/dev/null || echo 0)"
  if [ "$ahead" -gt 0 ]; then
    echo "You have $ahead commit(s) not on master. The Droplet pulls master, so they will not ship." >&2
    echo "Push them first, or run with SP_DEPLOY_ANYWAY=1 to deploy master as it stands." >&2
    [ "${SP_DEPLOY_ANYWAY:-}" = "1" ] || exit 1
  fi
  if [ -n "$(git status --porcelain)" ]; then
    echo "Note: this working tree has uncommitted changes. They are not part of this deploy."
  fi
}

deploy() {
  say "Deploying master to $HOST"
  ssh "$HOST" bash -euo pipefail -s <<REMOTE
cd "$DIR"
git pull --ff-only
cd deploy/digitalocean
docker compose up -d --build
./doctor.sh
REMOTE
}

main() {
  warn_about_unpushed
  deploy
  say "Done. https://standardphysics.app"
}

main "$@"
