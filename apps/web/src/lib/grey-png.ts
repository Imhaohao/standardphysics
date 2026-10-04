/**
 * Reads an 8-bit grey PNG into one byte per pixel, top row first.
 *
 * The clearance map arrives as one, and its bytes are measurements rather than colours. An <img> drawn onto a
 * canvas hands them to the browser's colour management first, which is free to shift them, so this reads the format
 * itself: the chunks, the zlib stream and the five row filters, for the one kind of PNG the server writes.
 */

const SIGNATURE = [137, 80, 78, 71, 13, 10, 26, 10];
const CHUNK_FRAME_BYTES = 12;

export type GreyImage = { width: number; height: number; pixels: Uint8Array };

type Header = { width: number; height: number };

export async function readGreyPng(bytes: Uint8Array): Promise<GreyImage> {
  const { header, compressed } = chunksOf(bytes);
  const filtered = await inflate(compressed);
  return { ...header, pixels: unfilter(filtered, header) };
}

export function base64Bytes(base64: string): Uint8Array {
  return Uint8Array.from(atob(base64), (character) => character.charCodeAt(0));
}

function chunksOf(bytes: Uint8Array): { header: Header; compressed: Uint8Array } {
  if (!SIGNATURE.every((value, index) => bytes[index] === value)) throw new Error("This is not a PNG.");
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const image: Uint8Array[] = [];
  let header: Header | null = null;
  for (let at = SIGNATURE.length; at + CHUNK_FRAME_BYTES <= bytes.length; at += CHUNK_FRAME_BYTES + view.getUint32(at)) {
    const type = String.fromCharCode(...bytes.subarray(at + 4, at + 8));
    const body = bytes.subarray(at + 8, at + 8 + view.getUint32(at));
    if (type === "IHDR") header = headerOf(body);
    if (type === "IDAT") image.push(body);
  }
  if (!header) throw new Error("The PNG has no header.");
  return { header, compressed: joined(image) };
}

function headerOf(body: Uint8Array): Header {
  const view = new DataView(body.buffer, body.byteOffset, body.byteLength);
  const [bitDepth, colourType, interlace] = [body[8], body[9], body[12]];
  if (bitDepth !== 8 || colourType !== 0 || interlace !== 0) throw new Error("Only 8-bit grey PNGs without interlacing are read here.");
  return { width: view.getUint32(0), height: view.getUint32(4) };
}

function joined(parts: Uint8Array[]): Uint8Array {
  const whole = new Uint8Array(parts.reduce((length, part) => length + part.length, 0));
  parts.reduce((at, part) => {
    whole.set(part, at);
    return at + part.length;
  }, 0);
  return whole;
}

async function inflate(compressed: Uint8Array): Promise<Uint8Array> {
  const stream = new Blob([compressed as Uint8Array<ArrayBuffer>]).stream().pipeThrough(new DecompressionStream("deflate"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

/** How each row filter predicts a byte from the one to its left, the one above, and the one above-left. */
const FILTERS: ((left: number, up: number, upLeft: number) => number)[] = [
  () => 0,
  (left) => left,
  (_left, up) => up,
  (left, up) => (left + up) >> 1,
  paeth,
];

function paeth(left: number, up: number, upLeft: number): number {
  const estimate = left + up - upLeft;
  const [fromLeft, fromUp, fromUpLeft] = [Math.abs(estimate - left), Math.abs(estimate - up), Math.abs(estimate - upLeft)];
  if (fromLeft <= fromUp && fromLeft <= fromUpLeft) return left;
  return fromUp <= fromUpLeft ? up : upLeft;
}

function unfilter(filtered: Uint8Array, { width, height }: Header): Uint8Array {
  const pixels = new Uint8Array(width * height);
  for (let row = 0; row < height; row += 1) {
    const start = row * (width + 1);
    const predict = FILTERS[filtered[start]];
    if (!predict) throw new Error(`The PNG uses row filter ${filtered[start]}, which does not exist.`);
    for (let column = 0; column < width; column += 1) {
      const at = row * width + column;
      const [left, up, upLeft] = neighbours(pixels, at, row, column, width);
      pixels[at] = (filtered[start + 1 + column] + predict(left, up, upLeft)) & 0xff;
    }
  }
  return pixels;
}

function neighbours(pixels: Uint8Array, at: number, row: number, column: number, width: number): [number, number, number] {
  const left = column > 0 ? pixels[at - 1] : 0;
  const up = row > 0 ? pixels[at - width] : 0;
  return [left, up, row > 0 && column > 0 ? pixels[at - width - 1] : 0];
}
