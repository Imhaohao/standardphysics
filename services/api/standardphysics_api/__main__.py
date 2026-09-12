"""python -m standardphysics_api  serves on :8787, the port Lane A's app expects."""

import logging
import os

import uvicorn

from .app import create_app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(create_app(), host=os.environ.get("SP_API_HOST", "0.0.0.0"), port=8787, workers=1)
