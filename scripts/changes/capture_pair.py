"""Cut a before and after pair from one real phone capture, with the phone's own camera track as truth.

A Standard Physics capture folder holds walkthrough.mp4 and poses.json, where ARKit wrote
where the phone was every half second. Two stretches of the walk that look at the same
part of the room become before.mp4 and after.mp4, turned upright, and truth.json records
the ARKit camera position for every frame of both clips. Nothing was staged between the
two stretches, so the truth lists no changes: anything reported either really moved
(people do) or is a false alarm, and the camera track scores the reconstruction's path
and scale against real metres.

    python scripts/changes/capture_pair.py datasets/phone/sharetea --before 168 16 --after 198 16 \
        --out /tmp/sharetea-pair
"""

import argparse
import json
import pathlib
import subprocess

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("capture", type=pathlib.Path)
    parser.add_argument("--before", type=float, nargs=2, metavar=("START_S", "LENGTH_S"), required=True)
    parser.add_argument("--after", type=float, nargs=2, metavar=("START_S", "LENGTH_S"), required=True)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--turn", default="transpose=1", help="ffmpeg filter that stands the frames upright")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    return parser.parse_args()


def arkit_track(capture: pathlib.Path) -> tuple[np.ndarray, np.ndarray]:
    """Seconds since the first pose, and camera positions in metres, from ARKit's column-major transforms."""
    poses = json.loads((capture / "poses.json").read_text())
    times = np.array([pose["timestamp"] for pose in poses], dtype=float)
    positions = np.array([np.array(pose["transform"], dtype=float).reshape(4, 4).T[:3, 3] for pose in poses])
    return times - times[0], positions


def cut(capture: pathlib.Path, start: float, length: float, fps: int, turn: str, target: pathlib.Path) -> None:
    command = ["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start), "-t", str(length),
               "-i", str(capture / "walkthrough.mp4"), "-vf", f"{turn},fps={fps}", "-c:v", "libx264", "-crf", "20",
               "-pix_fmt", "yuv420p", "-an", str(target)]
    subprocess.run(command, check=True)


def clip_cameras(times: np.ndarray, positions: np.ndarray, start: float, length: float, fps: int) -> list:
    """One pose per clip frame: the ARKit position at that moment, with an identity rotation."""
    poses = []
    for frame in range(int(round(length * fps)) + 1):
        moment = start + frame / fps
        position = [float(np.interp(moment, times, positions[:, axis])) for axis in range(3)]
        pose = np.eye(4)
        pose[:3, 3] = position
        poses.append(pose.round(5).tolist())
    return poses


def main() -> None:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    times, positions = arkit_track(args.capture)
    cameras = {}
    for walk, (start, length) in (("before", args.before), ("after", args.after)):
        cut(args.capture, start, length, args.fps, args.turn, args.out / f"{walk}.mp4")
        cameras[walk] = clip_cameras(times, positions, start, length, args.fps)
    truth = {
        "frame": "ARKit world, metres, y up; only camera positions are recorded",
        "source": str(args.capture),
        "clips": {"before": args.before, "after": args.after, "fps": args.fps},
        "cameras_opencv_c2w": cameras,
        "changes": [],
        "unverifiable": [],
    }
    (args.out / "truth.json").write_text(json.dumps(truth, indent=1))


if __name__ == "__main__":
    main()
