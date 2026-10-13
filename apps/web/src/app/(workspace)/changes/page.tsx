import type { Metadata } from "next";
import { ChangeViewer } from "@/components/changes/ChangeViewer";

export const metadata: Metadata = {
  title: "What changed in the room, Standard Physics",
  description: "Compare two phone videos of one room and see, in 3D, which things changed.",
};

const DEFAULT_ROOM = "living-room";
const ROOM_NAME = /^[a-z0-9][a-z0-9-]{0,63}$/;

/** A room the change detector compared; ?room= picks another output folder under public/changes. */
export default async function ChangesPage({ searchParams }: { searchParams: Promise<{ room?: string }> }) {
  const { room } = await searchParams;
  const name = room && ROOM_NAME.test(room) ? room : DEFAULT_ROOM;
  return <ChangeViewer key={name} room={name} base={`/changes/${name}`} />;
}
