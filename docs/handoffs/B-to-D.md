# B to D: there is a GLB waiting for you

`packages/fixtures/standardphysics_fixtures/data/shop.glb` — 19 objects, 29 KB,
built from the fixture shop. Load it in the viewer today; you do not need a real
scan and you do not need me.

**Every glTF node is named with its SceneGraph node UUID.** Select a mesh, read
`node.name`, and you have the exact ID the findings reference. No mapping file
sits in between.

That works because glTF node names are arbitrary strings. USD prim names are
not: they cannot contain hyphens or start with a digit, so a UUID silently
collapses and every object comes back as `Cube_001`. If you ever load a USDZ
directly rather than our GLB, you need `shop.node_map.json` to get identity
back.

Each node also carries extras from `export_extras`:

| Extra | Use |
|---|---|
| `kind` | wall, door, window, opening, floor, object |
| `label` | what to show a person, e.g. "Ordering counter" |
| `movable` | whether rearrange mode may drag it |

Geometry comes from the SceneGraph, not from the scanned mesh, so what you draw
is what the checks measured. Rebuild any time:

```python
from standardphysics_pipeline.blender import export_glb
export_glb(graph, pathlib.Path("scene.glb"))
```

It takes about 1.8 s, so it belongs in the job queue rather than in a request.
