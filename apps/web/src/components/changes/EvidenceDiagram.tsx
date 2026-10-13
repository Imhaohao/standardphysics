type Case = { title: string; reach: number; blocked: boolean; tone: string; outline: "solid" | "dashed" };

const OBJECT_LEFT = 74;
const OBJECT_SIZE = 30;
const WALL = 136;

const CASES: Case[] = [
  { title: "Still there", reach: OBJECT_LEFT, blocked: false, tone: "var(--color-ink)", outline: "solid" },
  { title: "Gone", reach: WALL, blocked: false, tone: "var(--color-removed)", outline: "dashed" },
  { title: "Can't tell", reach: 50, blocked: true, tone: "var(--color-unseen)", outline: "dashed" },
];

function Phone() {
  return <rect x={4} y={36} width={12} height={22} rx={2.5} fill="var(--color-ink)" />;
}

function Panel({ item, x }: { item: Case; x: number }) {
  return (
    <g transform={`translate(${x} 0)`}>
      <Phone />
      <line x1={16} y1={47} x2={WALL + 4} y2={47} stroke="var(--color-ink-faint)" strokeWidth={1} strokeDasharray="2 3" />
      <line x1={16} y1={47} x2={item.reach} y2={47} stroke={item.tone} strokeWidth={2} />
      <circle cx={item.reach} cy={47} r={3.5} fill={item.tone} />
      <rect x={OBJECT_LEFT} y={32} width={OBJECT_SIZE} height={OBJECT_SIZE} rx={3} fill="none" stroke={item.tone}
        strokeWidth={1.5} strokeDasharray={item.outline === "dashed" ? "4 3" : undefined} />
      {item.blocked && <rect x={50} y={26} width={9} height={42} rx={2} fill="var(--color-ink-muted)" />}
      <rect x={WALL} y={16} width={4} height={62} fill="var(--color-ink-faint)" />
      <text x={72} y={104} textAnchor="middle" fill="var(--color-ink)" fontSize={15} fontWeight={600}>{item.title}</text>
    </g>
  );
}

/**
 * A phone from the other video looks toward a surface the first video saw. Landing on it means
 * it is still there, landing on the wall behind means it is gone, and being stopped short means nothing.
 */
export function EvidenceDiagram() {
  return (
    <svg viewBox="0 0 450 112" className="w-full" role="img"
      aria-label="Three cases. A line of sight that lands on the old surface means it is still there. One that passes it and lands on the wall behind means it is gone. One stopped by something in front means the video can't tell.">
      {CASES.map((item, index) => <Panel key={item.title} item={item} x={index * 152} />)}
    </svg>
  );
}
