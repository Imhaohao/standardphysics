# Standard Physics

Walk around your shop with an iPhone. The app records a video and measures the room with LiDAR at the same time, and it tells you where to point next until it has the whole place. A few seconds later you get a 3D model of your shop, a plain-English list of what would block a wheelchair customer, and a rearrangement that fixes it.

## Start here

| You are | Read |
|---|---|
| Any agent, before your first commit | [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) |
| Anyone, for what we're building | [`docs/PLAN.md`](docs/PLAN.md) |
| Lane A, capture | [`docs/lanes/LANE_A.md`](docs/lanes/LANE_A.md) |
| Lane B, model and measurement | [`docs/lanes/LANE_B.md`](docs/lanes/LANE_B.md) |
| Lane C, checks and evaluation | [`docs/lanes/LANE_C.md`](docs/lanes/LANE_C.md) |
| Lane D, contracts, API, web | [`docs/lanes/LANE_D.md`](docs/lanes/LANE_D.md) |
| Anyone writing UI or copy | [`CLAUDE.md`](CLAUDE.md), then section 2 of the plan |

## Setup

```bash
python -m pip install -e . -e packages/contracts -e packages/fixtures pytest
python -m pytest
```

Lane B additionally needs Blender 5.x. `brew install --cask --force blender` — the `--force` matters, because a plain install silently does nothing when Blender was installed by hand.

## What already works

Every lane can start right now without waiting on another.

**`packages/contracts/`** holds the types everyone shares: `SceneGraph`, `Finding`, `Locus`, `Proposal`, `Assessment`, and the `MeasurementProvider` protocol that joins Lane B to Lane C. Lane D owns this package; everyone else reads it.

**`packages/fixtures/`** holds a synthetic boba shop. Two display cases run in from the side walls and leave exactly 31 inches between them, on the only path from the door to the counter. Moving one case 5 inches opens it to the 36 inches the standard requires, so the whole find-then-fix loop is testable before any real scan exists.

```python
from standardphysics_fixtures import FixtureMeasurements, build_graph, build_scenario

result = FixtureMeasurements().route_clear_width(build_graph(), build_scenario(), 0)
result.inches          # 31.0
result.pinch_point     # where the camera should fly to
```

`FixtureMeasurements` implements `MeasurementProvider`, so Lane C writes checks against it today and swaps in Lane B's real implementation later by changing one constructor argument.

**`services/api/openapi.json`** is the upload contract. Lane A codes against it, Lane D implements it, and it runs locally right now:

```bash
python -m standardphysics_fixtures.mock_api    # :8787
```

**`packages/fixtures/standardphysics_fixtures/data/`** holds `shop.scene_graph.json`, `shop.usdz`, and `shop.node_map.json`.

That last file matters more than it looks. USD prim names must be alphanumeric with underscores and cannot start with a digit, so a UUID cannot be one — export it as a name and the hyphens vanish, the names collide, and every object comes back as `Cube_001`. Prims are named `n_<uuid hex>` and the map carries them home. RoomPlan solves the same problem with its `metadataURL` mapping file, which is why Lane A has to capture it.
