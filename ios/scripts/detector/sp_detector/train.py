"""One training run: gather photos, fine-tune, score, export.

`python -m sp_detector.train WORK_DIR` leaves in WORK_DIR/run:
- `model/`, the best fine-tuned checkpoint (Hugging Face format)
- `metrics.json`, its validation mAP overall and per class, with the photo and box counts
- `datasets.json`, the sources used and their licences, for LICENSES.md
- `ObjectDetector.mlpackage`, the Core ML package `train-detector.sh --install` copies into the app
"""

import argparse
import json
from pathlib import Path

from sp_detector import collect, coreml_export, splits, training
from sp_detector.config import TrainingConfig
from sp_detector.labels import LabelVocabulary


def _report(result: training.TrainingResult, dataset: splits.Splits) -> dict:
    per_class = {
        label: result.metrics["per_class"].get(label, {"ap": None, "ap50": None})
        | {"train_boxes": dataset.train_instances[label], "val_boxes": dataset.val_instances[label]}
        for label in dataset.labels
    }
    return {
        "map_50_95": result.metrics["map_50_95"],
        "map_50": result.metrics["map_50"],
        "best_epoch": result.metrics.get("epoch"),
        "epochs": result.epochs_completed,
        "steps": result.steps,
        "hours": round(result.elapsed_hours, 2),
        "device": result.device,
        "labels": dataset.labels,
        "per_class": per_class,
    }


def _score(value: float | None) -> str:
    return "  n/a" if value is None else f"{value:5.3f}"


def _print_report(report: dict) -> None:
    print(f"\nValidation mAP@[.5:.95] {report['map_50_95']:.3f}, mAP@.5 {report['map_50']:.3f} "
          f"(best of {report['epochs']} epochs, {report['hours']} h on {report['device']})")
    print(f"{'class':<26}{'AP':>7}{'AP50':>7}{'train boxes':>13}{'val boxes':>11}")
    for label, scores in report["per_class"].items():
        print(f"{label:<26}{_score(scores['ap']):>7}{_score(scores['ap50']):>7}"
              f"{scores['train_boxes']:>13}{scores['val_boxes']:>11}")


def _export(config: TrainingConfig, model_dir: Path, labels: list[str]) -> None:
    description = coreml_export.ExportDescription(
        summary=(
            "D-FINE nano object detector fine-tuned for accessibility surveys. Per query: best sigmoid score, "
            f"its class id (named by the labels metadata: {len(labels)} classes), and box (cx, cy, w, h) "
            "normalized to the input."
        ),
        source=coreml_export.PUBLISHED_COCO.source,
        revision=coreml_export.PUBLISHED_COCO.revision,
    )
    staged = config.run_dir / "ObjectDetector.mlpackage"
    coreml_export.export(str(model_dir), None, description, staged)
    print(f"Core ML package written to {staged}")


def run(config: TrainingConfig) -> None:
    config.run_dir.mkdir(parents=True, exist_ok=True)
    records, used_sources = collect.all_records(config, LabelVocabulary(config.label_renames))
    dataset = splits.write_splits(records, config.dataset_dir, config.validation_fraction)
    print(f"{len(records)} photos, {len(dataset.labels)} classes: {', '.join(dataset.labels)}")
    (config.run_dir / "datasets.json").write_text(json.dumps([s.as_json() for s in used_sources], indent=2))

    result = training.train(config, dataset.train_file, dataset.val_file, dataset.labels)
    report = _report(result, dataset)
    (config.run_dir / "metrics.json").write_text(json.dumps(report, indent=2))
    _print_report(report)
    if not config.skip_export:
        _export(config, result.model_dir, dataset.labels)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("work_dir", type=Path)
    run(TrainingConfig.from_environment(parser.parse_args().work_dir.resolve()))


if __name__ == "__main__":
    main()
