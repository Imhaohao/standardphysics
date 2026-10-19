import { boxesOverlap, boxInside, type Box } from "./geometry";

/** Areas of the sheet the pen must avoid: page content (keep-outs) and marks already drawn (claims). */
export class Occupancy {
  private claims: Box[] = [];
  private keepOuts: readonly Box[] = [];
  private bounds: Box | null = null;

  setKeepOuts(keepOuts: readonly Box[], bounds: Box | null) {
    this.keepOuts = keepOuts;
    this.bounds = bounds;
  }

  isAllowed(box: Box) {
    if (this.bounds && !boxInside(box, this.bounds)) return false;
    return this.keepOuts.every((keepOut) => !boxesOverlap(box, keepOut));
  }

  isFree(box: Box) {
    return this.isAllowed(box) && this.claims.every((taken) => !boxesOverlap(box, taken));
  }

  claim(box: Box) {
    this.claims.push(box);
  }

  get claimCount() {
    return this.claims.length;
  }

  rollbackTo(claimCount: number) {
    this.claims.length = claimCount;
  }

  clear() {
    this.claims = [];
  }
}
