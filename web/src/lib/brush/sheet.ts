export const DRAFTING_UNIT_PX = 12;

export interface ZoneGrid {
  columns: number;
  rows: number;
}

export function zoneGridFor(width: number, height: number): ZoneGrid {
  return { columns: width >= 720 ? 8 : 4, rows: height >= 600 ? 6 : 4 };
}

export function zoneRowLetter(row: number) {
  return String.fromCharCode(65 + row);
}

export function zoneAt(x: number, y: number, width: number, height: number): string {
  const { columns, rows } = zoneGridFor(width, height);
  const column = Math.min(columns - 1, Math.max(0, Math.floor((x / width) * columns)));
  const row = Math.min(rows - 1, Math.max(0, Math.floor((y / height) * rows)));
  return `${zoneRowLetter(row)}${column + 1}`;
}
