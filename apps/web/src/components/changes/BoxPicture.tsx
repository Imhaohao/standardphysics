/* eslint-disable @next/next/no-img-element -- crops are static files beside scene.json, already sized */
import { BOX_EDGES, type ChangePicture, type ChangeType } from "@/lib/room-changes";

function clockTime(seconds: number): string {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

type BoxPictureProps = {
  picture: ChangePicture | undefined;
  base: string;
  type: ChangeType;
  emptySpot: boolean;
  alt: string;
};

/** A frame from one video with the change's 3D box drawn where the camera saw it. */
export function BoxPicture({ picture, base, type, emptySpot, alt }: BoxPictureProps) {
  if (!picture) {
    return <div className="grid aspect-[4/5] place-items-center rounded-md bg-ink/5 text-sm text-ink-faint">No clear view</div>;
  }
  return (
    <figure className="min-w-0">
      <div className={`change-tone-${type} relative overflow-hidden rounded-md bg-ink/5`} style={{ aspectRatio: picture.aspect }}>
        <img src={`${base}/${picture.file}`} alt={alt} className="size-full object-cover outline outline-1 -outline-offset-1 outline-black/10" />
        <svg viewBox="0 0 1 1" preserveAspectRatio="none" className="pointer-events-none absolute inset-0 size-full" aria-hidden>
          {BOX_EDGES.map(([a, b]) => (
            <line key={`${a}-${b}`} x1={picture.box[a][0]} y1={picture.box[a][1]} x2={picture.box[b][0]} y2={picture.box[b][1]}
              stroke="var(--change)" strokeWidth={2} vectorEffect="non-scaling-stroke"
              strokeDasharray={emptySpot ? "5 4" : undefined} />
          ))}
        </svg>
      </div>
      <figcaption className="mt-1.5 flex items-baseline justify-between gap-2 text-sm text-ink-muted">
        <span className="font-medium text-ink">{picture.video === "before" ? "Before" : "After"}</span>
        <span className="measurement text-xs">{clockTime(picture.time_s)}</span>
      </figcaption>
    </figure>
  );
}
