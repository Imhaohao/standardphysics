# Standard Physics iOS app

The capture app: SwiftUI, Swift 6, iOS 26 or later, on an iPhone with LiDAR. `scripts/bootstrap.sh`
generates the Xcode project from `project.yml`.

## Teaching the detector new objects

Out of the box the on-phone detector is D-FINE nano trained on COCO, which knows chairs, tables,
toilets and sinks but has never seen a grab bar, a light switch or a soap dispenser.
`scripts/train-detector.sh` fine-tunes it on free photo collections that allow commercial use, so
it learns these classes as well:

| Detector label | Category in `rules/metrics.json` | Photos from |
| --- | --- | --- |
| door handle | `door_hardware` | Open Images |
| light switch | `light_switch` | Open Images |
| power plugs and sockets | `outlet` | Open Images |
| soap dispenser, paper towel | `dispenser` | Open Images |
| toilet paper | `toilet_paper_dispenser` | Open Images |
| hand dryer | `hand_dryer` | Open Images |
| mirror | `mirror` | Open Images |
| countertop | `counter` | Open Images |
| grab bar | `grab_bar` | an extra folder you add (see below) |
| sign | `sign` | an extra folder you add (see below) |

It also keeps training on COCO photos of the furniture and fixtures the app already detects, so
those don't get worse. The app reads the class names from the model file, so no Swift change is
needed after installing a new model.

### What you need

- An Apple-silicon Mac (M1 or later) with 16 GB of memory, plugged into power, with at least 15 GB of
  free disk space.
- `uv`, which installs Python and every package for you. If `uv --version` prints nothing, install
  it with `curl -LsSf https://astral.sh/uv/install.sh | sh` and open a new Terminal window.

### 1. Train overnight

Open Terminal in the repository folder and run:

```sh
ios/scripts/train-detector.sh
```

First it downloads about 9 GB of photos and annotations into `~/sp-detector-training`, which
takes one to two hours on a fast connection. Training then runs for 7.5 hours and stops by
itself. The Mac stays awake while it runs, but leave the lid open and the charger in. Progress
goes to the Terminal and to `~/sp-detector-training/train.log`.

When it finishes, it prints a table of scores for each class. AP50 is the share of objects the
model found with a box that overlaps the real one by at least half, from 0 (none) to 1 (all of
them). The same table is saved in `~/sp-detector-training/run/metrics.json`.

### 2. Install the model

When you're happy with the scores, run:

```sh
ios/scripts/train-detector.sh --install
```

This replaces `Resources/Models/ObjectDetector.mlpackage` and rewrites
`Resources/Models/LICENSES.md` with the datasets the model learned from. Build the app as usual and
commit both files. To go back to the original COCO model, run `ios/scripts/export-detector.sh`.

### Adding grab bars and signs

Open Images has no grab bars or accessible-toilet signs, so those come from small datasets on
[Roboflow Universe](https://universe.roboflow.com), for example
[disabled bathroom](https://universe.roboflow.com/afi-khan/disabled-bathroom-vb7zs).

1. Check the licence on the dataset's page. It must allow commercial use, such as CC BY 4.0;
   skip anything marked NC (non-commercial).
2. Choose **Download Dataset**, pick the **COCO** format, and unzip it into a folder, for example
   `~/datasets/disabled-bathroom`.
3. The zip includes `README.dataset.txt` with a `License: CC BY 4.0` line. The training script
   reads that line and refuses a folder without one. If a download lacks it, add a `LICENSE.txt`
   holding the licence line and the dataset's web address.
4. Train with the folder listed in `SP_EXTRA_COCO_DIRS`. Separate several folders with `:`.

```sh
SP_EXTRA_COCO_DIRS=~/datasets/disabled-bathroom ios/scripts/train-detector.sh
```

Common spellings such as `grab-bars` and `accessible-toilet-sign` become `grab bar` and `sign`
automatically. Labels the app has no use for are dropped, and the script prints how many photos
each folder contributed. For another spelling, add a rename:

```sh
SP_LABEL_RENAMES="handrail-wc=grab bar;wc-sign=sign" SP_EXTRA_COCO_DIRS=~/datasets/disabled-bathroom ios/scripts/train-detector.sh
```

### Settings

Each setting is an environment variable placed before the command, as above.

| Variable | Default | What it changes |
| --- | --- | --- |
| `SP_TRAIN_HOURS` | `7.5` | How long training runs, not counting downloads |
| `SP_OPEN_IMAGES_PER_CLASS` | `1000` | Most photos fetched for each Open Images class |
| `SP_COCO_PER_CLASS` | `300` | Most photos kept for each COCO class; `0` skips COCO |
| `SP_EXTRA_COCO_DIRS` | none | COCO-format folders to add, separated by `:` |
| `SP_LABEL_RENAMES` | none | `from=to` pairs separated by `;` |
| `SP_BATCH_SIZE` | `8` | Photos per training step; lower it if the Mac runs out of memory |
| `SP_EPOCHS` | `30` | Most passes over the photos, if time remains |
| `SP_DETECTOR_WORK_DIR` | `~/sp-detector-training` | Where downloads, checkpoints and logs go |

The full list, with the rest of the defaults, is in `scripts/detector/sp_detector/config.py`.
Running the script again reuses the photos it already downloaded.
