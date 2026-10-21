"""Writes `ios/Resources/Models/LICENSES.md` for the model being installed.

`python -m sp_detector.licenses LICENSES_MD` describes the published COCO weights;
add `--datasets RUN/datasets.json` for a fine-tuned model, naming every dataset it learned from.
"""

import argparse
import json
from pathlib import Path

from sp_detector import base_model

HEADER = f"""# Bundled model licences

This file is written by `ios/scripts/export-detector.sh` and `ios/scripts/train-detector.sh --install`;
change `ios/scripts/detector/sp_detector/licenses.py` rather than editing it.

## ObjectDetector.mlpackage

A Core ML conversion of D-FINE nano, whose published weights were trained on COCO.

| | |
| --- | --- |
| Weights | {base_model.SOURCE_URL} |
| Revision | `{base_model.REVISION}` |
| Weights licence | Apache-2.0 (declared in the model card) |
| Model code | https://github.com/Peterande/D-FINE, Apache-2.0; Hugging Face Transformers port, Apache-2.0 |
| Paper | Peng et al., "D-FINE: Redefine Regression Task in DETRs as Fine-grained Distribution Refinement", arXiv:2410.13842 |

Changes from the original: converted to Core ML with FP16 weights and a fixed 640x640 input, and the
output reduced to each query's best class score, class id and box. The Apache-2.0 licence text is at
https://www.apache.org/licenses/LICENSE-2.0.
"""

PUBLISHED_WEIGHTS = """
### Fine-tuning data

None. The bundled model uses the published COCO weights unchanged.
"""

FINE_TUNED_INTRO = """
### Fine-tuning data

The weights above were fine-tuned with a new class head on the photos below. No photos ship in the
app; only the trained weights do. Every source allows commercial use, and the attribution each
licence asks for is listed under the table.

| Dataset | Photos | Annotation licence | Photo licence | Classes learned |
| --- | --- | --- | --- | --- |
"""


def _dataset_row(dataset: dict) -> str:
    labels = ", ".join(dataset["labels"])
    return (
        f"| [{dataset['name']}]({dataset['url']}) | {dataset['image_count']:,} | {dataset['annotation_license']} "
        f"| {dataset['image_license']} | {labels} |"
    )


def fine_tuned_section(datasets: list[dict]) -> str:
    rows = "\n".join(_dataset_row(dataset) for dataset in datasets)
    attributions = "\n".join(f"- {dataset['name']}: {dataset['attribution']}" for dataset in datasets)
    return f"{FINE_TUNED_INTRO}{rows}\n\nAttribution:\n\n{attributions}\n"


def write(licenses_file: Path, datasets: list[dict] | None) -> None:
    section = fine_tuned_section(datasets) if datasets else PUBLISHED_WEIGHTS
    licenses_file.write_text(HEADER + section)


def main() -> None:
    parser = argparse.ArgumentParser(description="Write the bundled model's licence notice.")
    parser.add_argument("licenses_file", type=Path)
    parser.add_argument("--datasets", type=Path, help="datasets.json from a training run")
    arguments = parser.parse_args()
    datasets = json.loads(arguments.datasets.read_text()) if arguments.datasets else None
    write(arguments.licenses_file, datasets)


if __name__ == "__main__":
    main()
