import { Quaternion, Vector3 } from "three";
import { doors, floor, furniture, orderingCounter, walls, type ShopBox } from "@/lib/fixtureShop";
import { backBar, cardReaderSize, cardReaderSpots, counterLayout } from "./counterLayout";

export type PartFinish = "clay" | "glass" | "ink" | "floor";
export type PartShape = "box" | "cylinder";
export type PieceRole = "context" | "counter" | "cardReader";

export type ShopPart = {
  center: Vector3;
  size: Vector3;
  finish: PartFinish;
  shape: PartShape;
};

export type ShopPiece = {
  key: string;
  role: PieceRole;
  position: Vector3;
  quaternion: Quaternion;
  parts: ShopPart[];
};

export const WALL_CUT_HEIGHT = 1.25;
const POCHE_THICKNESS = 0.004;
const PLINTH_DEPTH = 0.14;
const PLINTH_MARGIN = 0.12;

function part(center: [number, number, number], size: [number, number, number], finish: PartFinish = "clay", shape: PartShape = "box"): ShopPart {
  return { center: new Vector3(...center), size: new Vector3(...size), finish, shape };
}

function nearestTable(chair: ShopBox) {
  const tables = furniture.filter((box) => box.label === "Table");
  return tables.reduce((closest, table) =>
    table.position.distanceTo(chair.position) < closest.position.distanceTo(chair.position) ? table : closest,
  );
}

function chairParts(chair: ShopBox): ShopPart[] {
  const { x: width, y: height, z: depth } = chair.size;
  const floorY = -height / 2;
  const seatTop = floorY + 0.46;
  const backSide = Math.sign(chair.position.z - nearestTable(chair).position.z) || 1;
  const legInset = width / 2 - 0.04;
  const legs = [-1, 1].flatMap((sx) =>
    [-1, 1].map((sz) => part([sx * legInset, floorY + 0.21, sz * legInset], [0.035, 0.42, 0.035])),
  );
  const backHeight = height - 0.46;
  return [
    part([0, seatTop - 0.025, 0], [width, 0.05, depth]),
    part([0, seatTop + backHeight / 2, backSide * (depth / 2 - 0.025)], [width, backHeight, 0.05]),
    ...legs,
  ];
}

function tableParts(table: ShopBox): ShopPart[] {
  const { x: width, y: height, z: depth } = table.size;
  const floorY = -height / 2;
  return [
    part([0, height / 2 - 0.02, 0], [width, 0.04, depth]),
    part([0, floorY + (height - 0.04) / 2, 0], [0.07, height - 0.04, 0.07], "clay", "cylinder"),
    part([0, floorY + 0.012, 0], [0.42, 0.024, 0.42], "clay", "cylinder"),
  ];
}

function displayCaseParts(displayCase: ShopBox): ShopPart[] {
  const { x: width, y: height, z: depth } = displayCase.size;
  const cabinetHeight = height * 0.6;
  const glassHeight = height - cabinetHeight;
  return [
    part([0, -height / 2 + cabinetHeight / 2, 0], [width, cabinetHeight, depth]),
    part([0, height / 2 - glassHeight / 2, 0], [width, glassHeight, depth], "glass"),
  ];
}

const COUNTER_TOP_THICKNESS = 0.04;
const COUNTER_OVERHANG = 0.03;

function counterSectionParts(section: { westX: number; eastX: number; topY: number }): ShopPart[] {
  const length = section.eastX - section.westX;
  const centerX = (section.westX + section.eastX) / 2;
  const bodyHeight = section.topY - COUNTER_TOP_THICKNESS;
  const { centerZ, depth } = counterLayout;
  return [
    part([centerX, bodyHeight / 2, centerZ], [length, bodyHeight, depth]),
    part(
      [centerX, section.topY - COUNTER_TOP_THICKNESS / 2, centerZ + COUNTER_OVERHANG / 2],
      [length, COUNTER_TOP_THICKNESS, depth + COUNTER_OVERHANG],
    ),
  ];
}

const CUP_DIAMETER = 0.085;
const CUP_SPACING = 0.13;
const CUP_CLEARANCE = 0.16;

function cupParts(): ShopPart[] {
  const { high, centerZ } = counterLayout;
  const readerEastEdge = cardReaderSpots.onHighCounter.x + cardReaderSize.x / 2;
  const firstCupX = high.eastX - CUP_CLEARANCE;
  const cups = [0, 1, 2, 3]
    .map((slot) => firstCupX - slot * CUP_SPACING)
    .filter((cupX) => cupX - CUP_DIAMETER / 2 > readerEastEdge + CUP_CLEARANCE / 2);
  return cups.map((cupX) =>
    part([cupX, high.topY + 0.075, centerZ - 0.12], [CUP_DIAMETER, 0.15, CUP_DIAMETER], "clay", "cylinder"),
  );
}

function counterPiece(): ShopPiece {
  return {
    key: orderingCounter.id,
    role: "counter",
    position: new Vector3(),
    quaternion: new Quaternion(),
    parts: [...counterSectionParts(counterLayout.high), ...counterSectionParts(counterLayout.low), ...cupParts()],
  };
}

function backBarPiece(): ShopPiece {
  const { westX, eastX, centerZ, depth, topY } = backBar;
  const length = eastX - westX;
  const centerX = (westX + eastX) / 2;
  const urns = [0, 1, 2, 3].map((slot) =>
    part([westX + 0.45 + slot * 0.32, topY + 0.2, centerZ - 0.05], [0.2, 0.4, 0.2], "clay", "cylinder"),
  );
  return {
    key: "back-bar",
    role: "context",
    position: new Vector3(),
    quaternion: new Quaternion(),
    parts: [
      part([centerX, (topY - COUNTER_TOP_THICKNESS) / 2, centerZ], [length, topY - COUNTER_TOP_THICKNESS, depth]),
      part([centerX, topY - COUNTER_TOP_THICKNESS / 2, centerZ], [length, COUNTER_TOP_THICKNESS, depth]),
      part([eastX - 0.55, topY + 0.2, centerZ], [0.36, 0.4, 0.4]),
      ...urns,
    ],
  };
}

function cardReaderPiece(): ShopPiece {
  const { x: width, y: height, z: depth } = cardReaderSize;
  return {
    key: "card-reader",
    role: "cardReader",
    position: cardReaderSpots.onHighCounter.clone(),
    quaternion: new Quaternion(),
    parts: [
      part([0, height / 2, 0], [width, height, depth], "ink"),
      part([0, height + 0.05, -depth / 2 + 0.01], [width * 0.8, 0.1, 0.02], "ink"),
    ],
  };
}

function blockParts(box: ShopBox): ShopPart[] {
  return [part([0, 0, 0], [box.size.x, box.size.y, box.size.z])];
}

const partsByLabel: Record<string, (box: ShopBox) => ShopPart[]> = {
  Chair: chairParts,
  Table: tableParts,
  "Display case": displayCaseParts,
};

function furniturePiece(box: ShopBox): ShopPiece {
  const buildParts = partsByLabel[box.label] ?? blockParts;
  return { key: box.id, role: "context", position: box.position, quaternion: box.quaternion, parts: buildParts(box) };
}

type Span = { start: number; end: number };

function subtractSpans(span: Span, holes: Span[]): Span[] {
  return holes
    .sort((a, b) => a.start - b.start)
    .reduce<Span[]>(
      (remaining, hole) =>
        remaining.flatMap((piece) => {
          if (hole.end <= piece.start || hole.start >= piece.end) return [piece];
          return [
            { start: piece.start, end: hole.start },
            { start: hole.end, end: piece.end },
          ].filter((result) => result.end - result.start > 0.001);
        }),
      [span],
    );
}

function wallPieces(wall: ShopBox): ShopPiece[] {
  const runsAlongX = wall.size.x >= wall.size.z;
  const along = runsAlongX ? "x" : "z";
  const across = runsAlongX ? "z" : "x";
  const length = wall.size[along];
  const thickness = wall.size[across];
  const wallSpan = { start: wall.position[along] - length / 2, end: wall.position[along] + length / 2 };
  const doorways = doors
    .filter((door) => Math.abs(door.position[across] - wall.position[across]) <= thickness)
    .map((door) => ({ start: door.position[along] - door.size[along] / 2, end: door.position[along] + door.size[along] / 2 }));

  return subtractSpans(wallSpan, doorways).map((segment, index) => {
    const segmentLength = segment.end - segment.start;
    const position = new Vector3(0, WALL_CUT_HEIGHT / 2, 0);
    position[along] = (segment.start + segment.end) / 2;
    position[across] = wall.position[across];
    const size: [number, number, number] = runsAlongX
      ? [segmentLength, WALL_CUT_HEIGHT, thickness]
      : [thickness, WALL_CUT_HEIGHT, segmentLength];
    const pocheSize: [number, number, number] = [size[0], POCHE_THICKNESS, size[2]];
    return {
      key: `${wall.id}-${index}`,
      role: "context",
      position,
      quaternion: new Quaternion(),
      parts: [part([0, 0, 0], size), part([0, WALL_CUT_HEIGHT / 2 + POCHE_THICKNESS / 2, 0], pocheSize, "ink")],
    };
  });
}

function plinthPiece(): ShopPiece {
  const width = floor.size.x + PLINTH_MARGIN * 2;
  const depth = floor.size.z + PLINTH_MARGIN * 2;
  return {
    key: "plinth",
    role: "context",
    position: new Vector3(floor.position.x, -PLINTH_DEPTH / 2, floor.position.z),
    quaternion: new Quaternion(),
    parts: [part([0, 0, 0], [width, PLINTH_DEPTH, depth], "floor")],
  };
}

export const shopPieces: ShopPiece[] = [
  plinthPiece(),
  ...walls.flatMap(wallPieces),
  ...furniture.filter((box) => box.id !== orderingCounter.id).map(furniturePiece),
  counterPiece(),
  backBarPiece(),
  cardReaderPiece(),
];

export const doorSwings = doors.map((door) => ({
  key: door.id,
  hinge: new Vector3(door.position.x - door.size.x / 2, 0.004, door.position.z - door.size.z / 2),
  width: door.size.x,
}));
