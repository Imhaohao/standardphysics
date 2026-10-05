import { deflateSync } from "node:zlib";
import { describe, expect, it } from "vitest";
import { base64Bytes, readGreyPng } from "./grey-png";

/**
 * A 12 by 10 cell room with walls all round and a box in the middle, as the server's `widths_png` writes it:
 * Pillow picks a row filter per row, and this one uses None, Sub, Up and Paeth.
 */
const SERVER_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAwAAAAKCAAAAAClR+AmAAAAOUlEQVR42m3MOQ7AMBQC0Wfy739iLykcWS5CNWIQXGmew6Ooj7tCG5Nk12sOhNwHhZYt9iw5pvvNC42dCRzkA/eYAAAAAElFTkSuQmCC";
const SERVER_ROWS = [
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
  [0, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 0],
  [0, 3, 7, 7, 7, 7, 7, 7, 7, 7, 3, 0],
  [0, 3, 7, 8, 5, 3, 3, 3, 5, 7, 3, 0],
  [0, 3, 7, 7, 3, 0, 0, 0, 3, 7, 3, 0],
  [0, 3, 7, 7, 3, 0, 0, 0, 3, 7, 3, 0],
  [0, 3, 7, 8, 5, 3, 3, 3, 5, 7, 3, 0],
  [0, 3, 7, 7, 7, 7, 7, 7, 7, 7, 3, 0],
  [0, 3, 3, 3, 3, 3, 3, 3, 3, 3, 3, 0],
  [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
];

function chunk(type: string, body: Uint8Array): Uint8Array {
  const framed = new Uint8Array(12 + body.length);
  new DataView(framed.buffer).setUint32(0, body.length);
  framed.set(Array.from(type, (character) => character.charCodeAt(0)), 4);
  framed.set(body, 8);
  return framed;
}

function header(width: number, height: number, bitDepth = 8, colourType = 0): Uint8Array {
  const body = new Uint8Array(13);
  const view = new DataView(body.buffer);
  view.setUint32(0, width);
  view.setUint32(4, height);
  body.set([bitDepth, colourType, 0, 0, 0], 8);
  return body;
}

/** The PNG specification's Paeth predictor, written out here so the test encodes rows the way an encoder would. */
function paeth(left: number, up: number, upLeft: number): number {
  const [fromLeft, fromUp, fromUpLeft] = [left, up, upLeft].map((value) => Math.abs(left + up - upLeft - value));
  if (fromLeft <= fromUp && fromLeft <= fromUpLeft) return left;
  return fromUp <= fromUpLeft ? up : upLeft;
}

const PREDICTORS = [() => 0, (left: number) => left, (_: number, up: number) => up, (left: number, up: number) => (left + up) >> 1, paeth];

function encode(rows: number[][], filters: number[], idatParts = 1): Uint8Array {
  const width = rows[0].length;
  const at = (r: number, c: number) => (r >= 0 && c >= 0 ? rows[r][c] : 0);
  const filtered = rows.flatMap((row, r) => [
    filters[r],
    ...row.map((value, c) => (value - PREDICTORS[filters[r]](at(r, c - 1), at(r - 1, c), at(r - 1, c - 1)) + 256) & 0xff),
  ]);
  const compressed = deflateSync(Uint8Array.from(filtered));
  const size = Math.ceil(compressed.length / idatParts);
  const parts = Array.from({ length: idatParts }, (_, index) => chunk("IDAT", compressed.subarray(index * size, (index + 1) * size)));
  const pieces = [Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10]), chunk("IHDR", header(width, rows.length)), ...parts, chunk("IEND", new Uint8Array())];
  return Uint8Array.from(pieces.flatMap((piece) => Array.from(piece)));
}

function rowsOf(image: { width: number; pixels: Uint8Array }): number[][] {
  return Array.from({ length: image.pixels.length / image.width }, (_, row) => Array.from(image.pixels.subarray(row * image.width, (row + 1) * image.width)));
}

describe("readGreyPng", () => {
  it("reads the bytes the server writes, row filters and all", async () => {
    const image = await readGreyPng(base64Bytes(SERVER_PNG));
    expect([image.width, image.height]).toEqual([12, 10]);
    expect(rowsOf(image)).toEqual(SERVER_ROWS);
  });

  it("undoes every one of the five row filters, including the average one Pillow skipped above", async () => {
    const rows = [[3, 200, 7, 255], [9, 0, 250, 1], [128, 64, 32, 16], [255, 255, 0, 0], [1, 2, 3, 4]];
    const image = await readGreyPng(encode(rows, [0, 1, 2, 3, 4]));
    expect(rowsOf(image)).toEqual(rows);
  });

  it("joins image data split across several chunks", async () => {
    const rows = Array.from({ length: 20 }, (_, row) => Array.from({ length: 30 }, (_, column) => (row * 31 + column * 7) % 256));
    const image = await readGreyPng(encode(rows, rows.map((_, row) => row % 5), 4));
    expect(rowsOf(image)).toEqual(rows);
  });

  it("refuses bytes that are not a PNG, and PNGs it cannot read exactly", async () => {
    await expect(readGreyPng(Uint8Array.from([1, 2, 3, 4, 5, 6, 7, 8, 9]))).rejects.toThrow("not a PNG");
    const colour = Uint8Array.from([137, 80, 78, 71, 13, 10, 26, 10, ...chunk("IHDR", header(1, 1, 8, 2))]);
    await expect(readGreyPng(colour)).rejects.toThrow("Only 8-bit grey");
  });
});
