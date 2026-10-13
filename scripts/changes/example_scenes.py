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

# Added after every detector rule was fixed and scored once with that detector; its mistakes then
# shaped three more rules, so it is a development room now.
OFFICE = {
    "room": {"half_x": 2.4, "half_y": 2.0, "height": 2.7, "floor": "herringbone_parquet",
             "wall": "patterned_plaster_wall", "rug": ("denim_fabric", (1.6, 1.2), (0.6, -0.3))},
    "objects": [
        ("desk", "SchoolDesk_01", "desk", (-1.6, 1.5, 0), (-1.6, 1.5, 0)),
        ("desk_chair", "GreenChair_01", "chair", (-1.6, 0.95, 180), (-1.6, 0.95, 180)),
        ("console", "ClassicConsole_01", "console table", (0.6, 1.65, 0), (0.6, 1.65, 0)),
        ("table", "WoodenTable_03", "table", (1.5, -0.2, 90), (1.5, -0.2, 90)),
        ("bench", "painted_wooden_bench", "bench", (-2.1, -0.4, 90), (-2.1, -0.4, 90)),
        ("plant", "potted_plant_02", "potted plant", (2.0, 1.55, 0), (2.0, 1.55, 0)),
        ("lounge_chair", "modern_arm_chair_01", "armchair", (-0.3, 0.4, 30), (0.5, -1.05, -60)),
        ("bar_chair", "bar_chair_round_01", "bar stool", (0.9, 0.85, 0), (-0.7, -1.2, 0)),
        ("crate", "wooden_crate_01", "wooden crate", (-1.2, -1.2, 10), None),
        ("container", "industrial_pastic_container", "plastic container", None, (2.0, -1.4, 0)),
        ("pot", "brass_pot_01", "brass pot", None, (1.5, -0.2, 0, "table")),
    ],
    "walks": {
        "before": [
            ((-2.0, -1.6, 1.45), (-0.6, 1.5, 0.4)),
            ((-0.8, -1.7, 1.47), (0.4, 1.2, 0.3)),
            ((0.4, -1.65, 1.45), (-0.6, 1.0, 0.2)),
            ((1.6, -1.5, 1.43), (0.0, 1.2, 0.3)),
            ((2.0, -0.4, 1.4), (-1.2, 0.9, 0.4)),
        ],
        "after": [
            ((2.0, 0.8, 1.35), (-1.2, -0.6, 0.3)),
            ((1.0, -1.6, 1.37), (-1.0, 0.9, 0.2)),
            ((-0.4, -1.7, 1.36), (1.2, 0.6, 0.3)),
            ((-1.9, -1.3, 1.34), (0.9, 0.6, 0.35)),
            ((-2.0, 0.0, 1.33), (1.5, 1.0, 0.45)),
        ],
    },
    "unverifiable": [],
}

# Added after the office became a development room and scored once; its mistakes then shaped
# two more rules, so it is a development room now too.
BEDROOM = {
    "room": {"half_x": 2.3, "half_y": 2.1, "height": 2.6, "floor": "old_wooden_floor_03", "wall": "beige_wall_002",
             "rug": ("curly_teddy_natural", (1.4, 1.0), (0.2, -0.6))},
    "objects": [
        ("bed", "GothicBed_01", "bed", (-0.9, 1.05, 0), (-0.9, 1.05, 0)),
        ("nightstand", "ClassicNightstand_01", "nightstand", (0.35, 1.85, 0), (0.35, 1.85, 0)),
        ("commode", "GothicCommode_01", "chest of drawers", (1.95, 0.8, -90), (1.95, 0.8, -90)),
        ("chair", "painted_wooden_chair_02", "chair", (0.8, 0.3, 20), (-1.5, -1.0, 60)),
        ("barrel", "Barrel_01", "barrel", (-1.85, -0.3, 0), (0.5, -0.9, 0)),
        ("planter", "planter_box_01", "planter box", (1.1, -0.6, 0), None),
        ("trash_bag", "trashbag", "trash bag", None, (-0.3, -0.4, 30)),
        ("basket", "wicker_basket_01", "wicker basket", None, (0.35, 1.85, 0, "nightstand")),
    ],
    "walks": {
        "before": [
            ((-1.9, -1.7, 1.42), (0.6, 1.2, 0.4)),
            ((-0.6, -1.8, 1.44), (1.2, 0.6, 0.3)),
            ((0.7, -1.75, 1.43), (-0.8, 0.8, 0.3)),
            ((1.6, -1.6, 1.42), (-0.6, 1.2, 0.4)),
            ((1.9, -0.6, 1.40), (-1.2, 0.0, 0.3)),
        ],
        "after": [
            ((1.8, -1.7, 1.35), (-1.0, 0.6, 0.3)),
            ((0.4, -1.8, 1.36), (1.4, 0.8, 0.3)),
            ((-1.0, -1.75, 1.37), (1.2, 0.2, 0.2)),
            ((-1.9, -1.2, 1.35), (1.0, 1.0, 0.4)),
            ((-1.95, -0.2, 1.33), (1.5, -0.6, 0.4)),
        ],
    },
    "unverifiable": [],
}

# Added after the bedroom became a development room, and scored once with the detector fixed after it.
KITCHEN = {
    "room": {"half_x": 2.4, "half_y": 2.0, "height": 2.7, "floor": "concrete_floor_painted", "wall": "painted_brick",
             "rug": ("hessian_230", (1.8, 1.3), (0.2, 0.2))},
    "objects": [
        ("dining_table", "wooden_table_02", "dining table", (0.2, 0.4, 0), (0.2, 0.4, 0)),
        ("sideboard", "modern_wooden_cabinet", "sideboard", (0.3, 1.7, 0), (0.3, 1.7, 0)),
        ("stove", "electric_stove", "stove", (2.05, 0.6, -90), (2.05, 0.6, -90)),
        ("pantry", "painted_wooden_cabinet_02", "cupboard", (-2.0, 1.1, 90), (-2.0, 1.1, 90)),
        ("dining_chair", "dining_chair_02", "dining chair", (0.2, -0.3, 180), (0.2, -0.3, 180)),
        ("plastic_chair", "plastic_monobloc_chair_01", "plastic chair", (1.1, 0.4, -90), (-1.6, -1.1, 45)),
        ("stool", "metal_stool_02", "metal stool", (-0.9, 0.3, 0), (1.4, -1.0, 0)),
        ("barrel", "Barrel_02", "barrel", (1.9, -0.6, 0), None),
        ("sack", "compost_bag_02", "sack", None, (-0.6, -1.0, 20)),
        ("vase", "ceramic_vase_01", "vase", None, (0.0, 0.45, 0, "dining_table")),
    ],
    "walks": {
        "before": [
            ((-1.9, -1.6, 1.44), (0.8, 1.2, 0.4)),
            ((-0.6, -1.7, 1.46), (0.6, 0.8, 0.2)),
            ((0.6, -1.7, 1.45), (-0.8, 0.9, 0.3)),
            ((1.7, -1.5, 1.43), (-0.5, 1.0, 0.3)),
            ((1.9, -0.2, 1.41), (-1.4, 0.4, 0.4)),
        ],
        "after": [
            ((1.8, 1.1, 1.35), (-1.2, -0.8, 0.3)),
            ((1.6, -1.6, 1.36), (-1.2, 0.6, 0.25)),
            ((0.0, -1.75, 1.37), (0.6, 1.0, 0.3)),
            ((-1.8, -1.5, 1.35), (1.0, 0.8, 0.35)),
            ((-1.9, -0.2, 1.34), (1.6, -0.3, 0.4)),
        ],
    },
    "unverifiable": [],
}

SCENES = {
    "living-room": LIVING_ROOM,
    "living-room-same": LIVING_ROOM_SAME,
    "living-room-blind-spot": LIVING_ROOM_BLIND_SPOT,
    "studio": STUDIO,
    "office": OFFICE,
    "bedroom": BEDROOM,
    "kitchen": KITCHEN,
}
