"""Runs the sp-server container on Modal.

Deploy from the repository root:

    MIN_CONTAINERS=1 modal deploy server/deploy/modal_app.py

Configuration is read from a Modal Secret named by SP_SERVER_SECRET (default
"sp-server") that holds the env vars listed in server/README.md
(DATABASE_URL, S3_*, APPLE_BUNDLE_ID, LABEL_API_KEY, ...). Nothing secret lives in this file.
"""

import os
import subprocess
from pathlib import Path

import modal

PORT = 8080
REPO_ROOT = Path(__file__).resolve().parents[2]
MIN_CONTAINERS = int(os.environ.get("MIN_CONTAINERS", "0"))
MAX_CONTAINERS = int(os.environ.get("MAX_CONTAINERS", "10"))
SCALEDOWN_SECONDS = int(os.environ.get("SCALEDOWN_SECONDS", "300"))
SECRET_NAME = os.environ.get("SP_SERVER_SECRET", "sp-server")

image = modal.Image.from_dockerfile(
    str(REPO_ROOT / "server" / "Dockerfile"),
    context_dir=str(REPO_ROOT),
    add_python="3.12",
)

app = modal.App("sp-server", image=image)


@app.function(
    secrets=[modal.Secret.from_name(SECRET_NAME)],
    min_containers=MIN_CONTAINERS,
    max_containers=MAX_CONTAINERS,
    scaledown_window=SCALEDOWN_SECONDS,
    timeout=3600,
)
@modal.concurrent(max_inputs=200)
@modal.web_server(PORT, startup_timeout=60)
def serve():
    env = {**os.environ, "PORT": str(PORT), "BIND_ADDR": f"0.0.0.0:{PORT}"}
    subprocess.Popen(["/usr/local/bin/sp-server", "serve"], env=env)
