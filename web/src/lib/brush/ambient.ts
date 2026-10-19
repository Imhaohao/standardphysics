import { clamp, polylineLength, type Box, type Point } from "./geometry";

/** The ambient pen wanders through the empty paper below the page content, never near it. */
export const AMBIENT_CELL_PX = 24;

const MINIMUM_CLEARANCE_CELLS = 3;
const STEP_PX = 6;
const TURN_TRIES = [0, 0.5, -0.5, 1, -1, 1.6, -1.6, 2.4, -2.4];
const MAX_ROUTES = 4;
const MINIMUM_ROUTE_PX = 180;
const ROUTE_BUDGET_PX = 900;
const ROUTE_SPACING_PX = 360;
const BOTTOM_BAND_CENTER = 0.84;
const BOTTOM_BAND_TOP = 0.55;
const UNREACHED = 0xffff;

/** A grid of cells, each holding its distance in cells to the nearest content or page edge. */
export interface FreeSpace {
  width: number;
  height: number;
  columns: number;
  rows: number;
  clearance: Uint16Array;
}

export interface AmbientPlanOptions {
  random?: () => number;
  budgetPx?: number;
}

function cellRange(from: number, to: number, count: number): [number, number] {
  return [clamp(Math.floor(from / AMBIENT_CELL_PX), 0, count), clamp(Math.ceil(to / AMBIENT_CELL_PX), 0, count)];
}

function seedClearance(columns: number, rows: number, keepOuts: readonly Box[]) {
  const clearance = new Uint16Array(columns * rows).fill(UNREACHED);
  for (const [left, top, right, bottom] of keepOuts) {
    const [firstColumn, lastColumn] = cellRange(left, right, columns);
    const [firstRow, lastRow] = cellRange(top, bottom, rows);
    for (let row = firstRow; row < lastRow; row++) clearance.fill(0, row * columns + firstColumn, row * columns + lastColumn);
  }
  for (let column = 0; column < columns; column++) {
    clearance[column] = Math.min(clearance[column]!, 1);
    clearance[(rows - 1) * columns + column] = Math.min(clearance[(rows - 1) * columns + column]!, 1);
  }
  for (let row = 0; row < rows; row++) {
    clearance[row * columns] = Math.min(clearance[row * columns]!, 1);
    clearance[row * columns + columns - 1] = Math.min(clearance[row * columns + columns - 1]!, 1);
  }
  return clearance;
}

function relaxNeighbours(space: FreeSpace, index: number, queue: number[]) {
  const { columns, rows, clearance } = space;
  const [column, row] = [index % columns, Math.floor(index / columns)];
  const next = clearance[index]! + 1;
  for (let dy = -1; dy <= 1; dy++) {
    for (let dx = -1; dx <= 1; dx++) {
      const [c, r] = [column + dx, row + dy];
      if (c < 0 || r < 0 || c >= columns || r >= rows) continue;
      const neighbour = r * columns + c;
      if (clearance[neighbour]! <= next) continue;
      clearance[neighbour] = next;
      queue.push(neighbour);
    }
  }
}

export function buildFreeSpace(width: number, height: number, keepOuts: readonly Box[]): FreeSpace {
  const columns = Math.max(1, Math.floor(width / AMBIENT_CELL_PX));
  const rows = Math.max(1, Math.floor(height / AMBIENT_CELL_PX));
  const space: FreeSpace = { width, height, columns, rows, clearance: seedClearance(columns, rows, keepOuts) };
  const queue: number[] = [];
  space.clearance.forEach((value, index) => {
    if (value !== UNREACHED) queue.push(index);
  });
  for (let head = 0; head < queue.length; head++) relaxNeighbours(space, queue[head]!, queue);
  return space;
}

export function clearanceAt(space: FreeSpace, x: number, y: number) {
  const column = Math.floor(x / AMBIENT_CELL_PX);
  const row = Math.floor(y / AMBIENT_CELL_PX);
  if (column < 0 || row < 0 || column >= space.columns || row >= space.rows) return 0;
  return space.clearance[row * space.columns + column]!;
}

function cellCenter(space: FreeSpace, index: number): Point {
  return [((index % space.columns) + 0.5) * AMBIENT_CELL_PX, (Math.floor(index / space.columns) + 0.5) * AMBIENT_CELL_PX];
}

function distanceFromDrawn(point: Point, drawn: readonly Point[]) {
  return drawn.reduce((nearest, other) => Math.min(nearest, Math.hypot(point[0] - other[0], point[1] - other[1])), Infinity);
}

/** Starts favour deep, open paper low on the page, away from routes already drawn. */
function startWeight(space: FreeSpace, index: number, drawn: readonly Point[]) {
  const clearance = space.clearance[index]!;
  const depth = (Math.floor(index / space.columns) + 0.5) / space.rows;
  if (clearance < MINIMUM_CLEARANCE_CELLS + 1 || depth < BOTTOM_BAND_TOP) return 0;
  const spread = Math.min(1, distanceFromDrawn(cellCenter(space, index), drawn) / ROUTE_SPACING_PX) ** 2;
  return Math.min(clearance, 8) ** 2 * (0.02 + depth ** 6) * spread;
}

function pickStart(space: FreeSpace, drawn: readonly Point[], random: () => number): Point | null {
  const weights = Float64Array.from(space.clearance, (_, index) => startWeight(space, index, drawn));
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  if (total <= 0) return null;
  let roll = random() * total;
  const index = Math.max(0, weights.findIndex((weight) => (roll -= weight) < 0));
  return cellCenter(space, index);
}

function steerTowardBottom(space: FreeSpace, y: number, heading: number) {
  const targetY = space.height * BOTTOM_BAND_CENTER;
  return clamp((targetY - y) / space.height, -0.5, 0.5) * 0.4 * Math.sign(Math.cos(heading) || 1);
}

function nextStep(space: FreeSpace, x: number, y: number, heading: number): [number, number, number] | null {
  for (const turn of TURN_TRIES) {
    const angle = heading + turn;
    const [nextX, nextY] = [x + Math.cos(angle) * STEP_PX, y + Math.sin(angle) * STEP_PX];
    const inBand = nextY >= space.height * BOTTOM_BAND_TOP;
    if (inBand && clearanceAt(space, nextX, nextY) >= MINIMUM_CLEARANCE_CELLS) return [nextX, nextY, angle];
  }
  return null;
}

function wander(space: FreeSpace, start: Point, budgetPx: number, random: () => number): Point[] {
  const route: Point[] = [start];
  let [x, y] = start;
  let heading = random() < 0.5 ? 0 : Math.PI;
  for (let travelled = 0; travelled < budgetPx; travelled += STEP_PX) {
    heading += (random() - 0.5) * 0.25 + steerTowardBottom(space, y, heading);
    const step = nextStep(space, x, y, heading);
    if (!step) break;
    [x, y, heading] = step;
    route.push([x, y]);
  }
  return route;
}

export function ambientBudget(space: FreeSpace) {
  const openCells = space.clearance.reduce((count, clearance) => count + (clearance >= MINIMUM_CLEARANCE_CELLS ? 1 : 0), 0);
  return clamp(openCells * AMBIENT_CELL_PX * AMBIENT_CELL_PX * 0.0028, 0, 2600);
}

export function planAmbientRoutes(space: FreeSpace, options: AmbientPlanOptions = {}): Point[][] {
  const random = options.random ?? Math.random;
  let remaining = options.budgetPx ?? ambientBudget(space);
  const routes: Point[][] = [];
  const drawn: Point[] = [];
  for (let attempt = 0; attempt < MAX_ROUTES && remaining >= MINIMUM_ROUTE_PX; attempt++) {
    const start = pickStart(space, drawn, random);
    if (!start) break;
    const route = wander(space, start, Math.min(remaining, ROUTE_BUDGET_PX), random);
    const length = polylineLength(route);
    if (length < MINIMUM_ROUTE_PX) continue;
    routes.push(route);
    drawn.push(...route.filter((_, index) => index % 8 === 0));
    remaining -= length;
  }
  return routes;
}
