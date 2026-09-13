import { Vector3 } from "three";
import { facts } from "@/lib/facts";
import { orderingCounter, walls } from "@/lib/fixtureShop";
import { inchesToMeters } from "@/lib/units";

const northWall = walls.reduce((northmost, wall) => (wall.position.z < northmost.position.z ? wall : northmost));
const northWallFaceZ = northWall.position.z + northWall.size.z / 2;

const BACK_BAR_DEPTH = 0.55;
const BACK_BAR_HEIGHT = 0.9;
const STAFF_AISLE_DEPTH = 0.95;
const SERVICE_COUNTER_LENGTH = 2.2;

const depth = orderingCounter.size.z;
const centerZ = northWallFaceZ + BACK_BAR_DEPTH + STAFF_AISLE_DEPTH + depth / 2;
const westEndX = orderingCounter.position.x - SERVICE_COUNTER_LENGTH / 2;
const eastEndX = orderingCounter.position.x + SERVICE_COUNTER_LENGTH / 2;
const lowSectionEastX = westEndX + inchesToMeters(facts.accessibleCounterMinLength.value);

const READER_HEIGHT = 0.08;
const READER_SET_BACK = 0.1;
const READER_LIFT = 0.22;

export const backBar = {
  westX: orderingCounter.position.x - orderingCounter.size.x / 2,
  eastX: orderingCounter.position.x + orderingCounter.size.x / 2,
  centerZ: northWallFaceZ + BACK_BAR_DEPTH / 2,
  depth: BACK_BAR_DEPTH,
  topY: BACK_BAR_HEIGHT,
};

export const counterLayout = {
  centerZ,
  frontZ: centerZ + depth / 2,
  depth,
  high: {
    westX: lowSectionEastX,
    eastX: eastEndX,
    inches: facts.counterHeightInLawsuit.value,
    topY: inchesToMeters(facts.counterHeightInLawsuit.value),
  },
  low: {
    westX: westEndX,
    eastX: lowSectionEastX,
    inches: facts.accessibleCounterMaxHeight.value,
    topY: inchesToMeters(facts.accessibleCounterMaxHeight.value),
  },
};

const readerZ = centerZ - READER_SET_BACK;

export const cardReaderSpots = {
  onHighCounter: new Vector3(lowSectionEastX + 0.4, counterLayout.high.topY, readerZ),
  onLowCounter: new Vector3((westEndX + lowSectionEastX) / 2, counterLayout.low.topY, readerZ),
};

export const cardReaderSize = new Vector3(0.2, READER_HEIGHT, 0.16);

export function placeCardReader(target: Vector3, moved: number) {
  const { onHighCounter, onLowCounter } = cardReaderSpots;
  target.lerpVectors(onHighCounter, onLowCounter, moved);
  target.y += Math.sin(moved * Math.PI) * READER_LIFT;
  return target;
}

export function counterTopUnderReader(moved: number) {
  const { high, low } = counterLayout;
  return high.topY + (low.topY - high.topY) * moved;
}
