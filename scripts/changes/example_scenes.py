"""The rooms render_example_room.py can film, each with what changes between its two walks.

An object is (name, Poly Haven id, label, placement before, placement after). A placement is
(x, y, yaw in degrees) on the floor, or None when the object is absent; a fourth value stacks
it on top of another object, by name. A walk is a list of (camera position, point looked at).

`unverifiable` names changes the before walk never had a chance to see. They are real, but the
detector should not report them, because one look cannot tell "new" from "was always there".
"""

LIVING_ROOM_STATIC = [
    ("sofa", "Sofa_01", "sofa", (0.0, 1.72, 0)),
    ("coffee_table", "modern_coffee_table_01", "coffee table", (0.0, 0.78, 0)),
    ("bookshelf", "Shelf_01", "bookshelf", (-2.33, 0.35, 90)),
    ("cabinet", "drawer_cabinet", "chest of drawers", (2.22, -1.05, -90)),
    ("side_table", "side_table_01", "side table", (1.2, 1.78, 0)),
    ("succulent", "potted_plant_04", "small potted succulent", (1.2, 1.78, 0, "side_table")),
]

LIVING_ROOM_WALKS = {
    "before": [
        ((-1.9, -1.65, 1.48), (-1.2, 1.6, 0.45)),
        ((-0.9, -1.75, 1.5), (-0.6, 1.2, 0.25)),
        ((0.2, -1.7, 1.46), (0.3, 0.6, 0.05)),
        ((1.2, -1.6, 1.44), (1.0, 1.4, 0.35)),
        ((1.85, -1.2, 1.42), (0.6, 1.8, 0.55)),
        ((1.9, -0.4, 1.4), (-1.0, 1.4, 0.5)),
    ],
    "after": [
        ((1.95, 0.6, 1.3), (-1.6, 1.4, 0.4)),
        ((1.7, -0.6, 1.32), (-1.9, 0.9, 0.3)),
        ((0.8, -1.55, 1.36), (-0.4, 0.9, 0.0)),
        ((-0.3, -1.75, 1.38), (0.6, 0.7, 0.05)),
        ((-1.4, -1.55, 1.34), (0.9, 1.3, 0.35)),
        ((-2.0, -0.9, 1.3), (0.4, 1.7, 0.5)),
    ],
}

LIVING_ROOM = {
    "room": {"half_x": 2.5, "half_y": 2.1, "height": 2.6, "floor": "laminate_floor_02", "wall": "beige_wall_001",
             "rug": ("fabric_pattern_07", (2.6, 1.7), (0.0, 0.65))},
    "objects": [(name, asset, label, spot, spot) for name, asset, label, spot in LIVING_ROOM_STATIC] + [
        ("armchair", "ArmChair_01", "armchair", (-1.3, 0.45, 55), (1.35, 0.15, -105)),
        ("stool", "wooden_stool_01", "wooden stool", (1.35, -0.55, 10), (-1.55, -0.35, 40)),
        ("floor_plant", "potted_plant_01", "potted plant", (-1.95, 1.62, 0), None),
        ("box", "cardboard_box_01", "cardboard box", None, (0.35, -0.2, 22)),
        ("basket", "wicker_basket_02", "wicker basket", None, (0.3, 0.78, -15, "coffee_table")),
    ],
    "walks": LIVING_ROOM_WALKS,
    "unverifiable": [],
}

LIVING_ROOM_SAME = {
    **LIVING_ROOM,
    "objects": [(name, asset, label, spot, spot) for name, asset, label, spot in LIVING_ROOM_STATIC] + [
        ("armchair", "ArmChair_01", "armchair", (-1.3, 0.45, 55), (-1.3, 0.45, 55)),
        ("stool", "wooden_stool_01", "wooden stool", (1.35, -0.55, 10), (1.35, -0.55, 10)),
        ("floor_plant", "potted_plant_01", "potted plant", (-1.95, 1.62, 0), (-1.95, 1.62, 0)),
    ],
}

LIVING_ROOM_BLIND_SPOT = {
    **LIVING_ROOM,
    "objects": [(name, asset, label, spot, spot) for name, asset, label, spot in LIVING_ROOM_STATIC] + [
        ("armchair", "ArmChair_01", "armchair", (-1.3, 0.45, 55), (-1.05, -0.55, 10)),
        ("floor_plant", "potted_plant_01", "potted plant", (-1.95, 1.62, 0), (-1.95, 1.62, 0)),
        ("crate", "plastic_crate_02", "plastic crate", None, (1.75, 0.55, 30)),
    ],
    "walks": {
        "before": [
            ((-1.9, -1.6, 1.45), (-1.7, 1.6, 0.4)),
            ((-1.0, -1.75, 1.45), (-1.3, 1.3, 0.25)),
            ((-0.2, -1.7, 1.45), (-1.6, 0.6, 0.2)),
            ((0.3, -1.3, 1.45), (-2.1, 0.9, 0.45)),
        ],
        "after": LIVING_ROOM_WALKS["after"],
    },
    "unverifiable": ["crate"],
}

STUDIO = {
    "room": {"half_x": 2.2, "half_y": 1.9, "height": 2.7, "floor": "diagonal_parquet", "wall": "grey_plaster",
             "rug": ("caban", (1.9, 1.4), (-0.6, 0.3))},
    "objects": [
        ("dining_table", "round_wooden_table_02", "round table", (1.2, 0.9, 0), (1.2, 0.9, 0)),
        ("dining_chair", "dining_chair_02", "dining chair", (1.2, 0.25, 180), (1.2, 0.25, 180)),
        ("sideboard", "painted_wooden_cabinet", "sideboard", (-0.6, 1.55, 0), (-0.6, 1.55, 0)),
        ("rocking_chair", "Rockingchair_01", "rocking chair", (-1.7, 1.2, 140), (-1.7, 1.2, 140)),
        ("plant", "potted_plant_02", "potted plant", (1.85, 1.55, 0), (1.85, 1.55, 0)),
        ("green_chair", "GreenChair_01", "armchair", (-1.4, -0.2, 70), (0.1, -0.6, -20)),
        ("ottoman", "Ottoman_01", "ottoman", (-0.4, 0.3, 0), (0.5, 0.45, 90)),
        ("crate", "wooden_crate_02", "wooden crate", (1.55, -1.1, 15), None),
        ("plastic_crate", "plastic_crate_02", "plastic crate", None, (-1.5, -1.1, -10)),
        ("vase", "brass_vase_01", "brass vase", None, (-0.3, 1.55, 0, "sideboard")),
    ],
    "walks": {
        "before": [
            ((-1.85, -1.5, 1.42), (0.4, 1.4, 0.3)),
            ((-0.6, -1.65, 1.44), (0.9, 1.0, 0.2)),
            ((0.6, -1.6, 1.43), (-0.6, 1.2, 0.25)),
            ((1.8, -1.4, 1.4), (-1.0, 0.9, 0.35)),
            ((1.85, -0.2, 1.38), (-1.5, 0.4, 0.4)),
        ],
        "after": [
            ((1.8, 0.1, 1.33), (-1.4, -0.6, 0.3)),
            ((1.2, -1.5, 1.35), (-1.2, 0.8, 0.2)),
            ((-0.2, -1.65, 1.36), (0.6, 1.2, 0.3)),
            ((-1.7, -1.4, 1.35), (1.2, 0.6, 0.3)),
            ((-1.85, -0.4, 1.32), (1.5, 1.0, 0.45)),
        ],
    },
    "unverifiable": [],
}

SCENES = {
    "living-room": LIVING_ROOM,
    "living-room-same": LIVING_ROOM_SAME,
    "living-room-blind-spot": LIVING_ROOM_BLIND_SPOT,
    "studio": STUDIO,
}
