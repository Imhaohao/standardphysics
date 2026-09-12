"""Writes the fixture shop to disk so non-Python lanes can load it too."""

from __future__ import annotations

import json
import pathlib

from .shop import build_graph, build_scenario

DATA = pathlib.Path(__file__).parent / "data"


def main() -> None:
    DATA.mkdir(exist_ok=True)
    graph, scenario = build_graph(), build_scenario()
    (DATA / "shop.scene_graph.json").write_text(
        json.dumps(json.loads(graph.model_dump_json()), indent=2) + "\n"
    )
    (DATA / "shop.scenario.json").write_text(
        json.dumps(json.loads(scenario.model_dump_json()), indent=2) + "\n"
    )
    print(f"wrote {len(graph.nodes)} nodes to {DATA}")


if __name__ == "__main__":
    main()
