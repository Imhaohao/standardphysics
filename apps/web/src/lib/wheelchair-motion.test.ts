import { describe, expect, it } from "vitest";
import type { SceneNode } from "@/types/contracts";
import { DEFAULT_WHEELCHAIR_PROFILE, assessOutletAccessibility, collidesAt, dockPoint, sweepWheelchair, sweepWheelchairInGeometry, wheelchairMotionGeometry, wheelchairProfile, wheelchairSpawn } from "./wheelchair-motion";

function node({
  id,
  kind,
  dimensions,
  x = 0,
  y = 0,
  rotation = 0,
  parentId = null,
  transform,
}: {
  id: string;
  kind: string;
  dimensions: { x: number; y: number; z: number };
  x?: number;
  y?: number;
  rotation?: number;
  parentId?: string | null;
  transform?: SceneNode["transform"]["m"];
}): SceneNode {
  const radians = (rotation * Math.PI) / 180;
  const cosine = Math.cos(radians);
  const sine = Math.sin(radians);
  return {
    id,
    kind,
    label: id,
    labeled_by: "fixture",
    movable: false,
    parent_id: parentId,
    quality: "measured",
    raw_category: kind,
    dimensions,
    transform: { m: transform ?? [cosine, -sine, 0, x, sine, cosine, 0, y, 0, 0, 1, 0, 0, 0, 0, 1] },
  };
}

describe("wheelchair motion geometry", () => {
  it("bounds adjustable navigation estimates before they reach collision and camera movement", () => {
    expect(wheelchairProfile({ eyeHeight: Number.NaN, speed: 99, collisionRadius: 0.01 })).toEqual({
      eyeHeight: DEFAULT_WHEELCHAIR_PROFILE.eyeHeight,
      speed: 4,
      collisionRadius: 0.3,
    });
    expect(wheelchairProfile({ eyeHeight: 0.95, speed: 1.8, collisionRadius: 0.55 })).toEqual({
      eyeHeight: 0.95,
      speed: 1.8,
      collisionRadius: 0.55,
    });
  });

  it("uses the actual extent of a long, thin rotated wall", () => {
    const geometry = wheelchairMotionGeometry([node({ id: "wall", kind: "wall", dimensions: { x: 10, y: 0.12, z: 3 }, rotation: 45 })]);
    const wall = geometry.obstacles[0];
    expect(wall.axisX.x).toBeCloseTo(Math.SQRT1_2);
    expect(wall.axisX.z).toBeCloseTo(-Math.SQRT1_2);

    const pastEnd = {
      x: wall.center.x + wall.axisX.x * 5.7 + wall.axisY.x,
      z: wall.center.z + wall.axisX.z * 5.7 + wall.axisY.z,
    };
    const alongside = sweepWheelchair(pastEnd, { x: -wall.axisY.x * 2, z: -wall.axisY.z * 2 }, geometry.obstacles, 0.3);
    expect(alongside.reached).toBe(true);

    const across = sweepWheelchair(
      { x: wall.center.x + wall.axisY.x * 2, z: wall.center.z + wall.axisY.z * 2 },
      { x: -wall.axisY.x * 4, z: -wall.axisY.z * 4 },
      geometry.obstacles,
      0.3,
    );
    expect(across.reached).toBe(false);
  });

  it("keeps a door opening passable while retaining its wall segments", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "wall", kind: "wall", dimensions: { x: 8, y: 0.2, z: 3 } }),
      node({ id: "door", kind: "door", dimensions: { x: 1.6, y: 0.6, z: 2 }, y: 0 }),
    ]);
    expect(geometry.obstacles).toHaveLength(2);
    expect(sweepWheelchair({ x: 0, z: 2 }, { x: 0, z: -4 }, geometry.obstacles, 0.3).reached).toBe(true);
    expect(sweepWheelchair({ x: 3, z: 2 }, { x: 0, z: -4 }, geometry.obstacles, 0.3).reached).toBe(false);
  });

  it("keeps zero-thickness exported walls solid and their actual doorway width open", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "wall", kind: "wall", dimensions: { x: 8, y: 0, z: 3 } }),
      node({ id: "door", kind: "door", dimensions: { x: 1.6, y: 0, z: 2 }, parentId: "wall" }),
    ]);
    expect(geometry.obstacles).toHaveLength(2);
    expect(sweepWheelchair({ x: 0, z: 2 }, { x: 0, z: -4 }, geometry.obstacles, 0.3).reached).toBe(true);
    expect(sweepWheelchair({ x: 3, z: 2 }, { x: 0, z: -4 }, geometry.obstacles, 0.3).reached).toBe(false);
  });

  it("does not let an unrelated or out-of-bounds portal cut a wall", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "wall", kind: "wall", dimensions: { x: 8, y: 0, z: 3 } }),
      node({ id: "other-wall", kind: "wall", dimensions: { x: 8, y: 0, z: 3 }, y: 5 }),
      node({ id: "wrong-parent", kind: "opening", dimensions: { x: 2, y: 0, z: 2 }, parentId: "other-wall" }),
      node({ id: "outside", kind: "opening", dimensions: { x: 1, y: 0, z: 2 }, x: 20 }),
    ]);
    expect(sweepWheelchair({ x: 0, z: 2 }, { x: 0, z: -4 }, geometry.obstacles, 0.3).reached).toBe(false);
  });

  it("does not turn floors or portals into collision targets", () => {
    const floor = node({ id: "floor", kind: "floor", dimensions: { x: 8, y: 8, z: 0.05 } });
    const opening = node({ id: "opening", kind: "opening", dimensions: { x: 1, y: 0.4, z: 2 } });
    const table = node({ id: "table", kind: "object", dimensions: { x: 1, y: 1, z: 0.7 } });
    const geometry = wheelchairMotionGeometry([floor, opening, table]);
    expect(geometry.obstacles.map((rect) => rect.node.id)).toEqual(["table"]);
    expect(geometry.targets.map((rect) => rect.node.id)).toEqual(["table"]);
  });

  it("extracts a published-style X/Z floor surface and constrains the default spawn to it", () => {
    const geometry = wheelchairMotionGeometry([
      node({
        id: "published-floor",
        kind: "floor",
        dimensions: { x: 4, y: 0, z: 4 },
        transform: [1, 0, 0, 0, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1],
      }),
    ]);
    expect(geometry.floors).toHaveLength(1);
    expect(geometry.floors[0].axisX.x).toBeCloseTo(1);
    expect(geometry.floors[0].axisX.z).toBeCloseTo(0);
    expect(geometry.floors[0].axisY.x).toBeCloseTo(0);
    expect(geometry.floors[0].axisY.z).toBeCloseTo(-1);

    const spawn = wheelchairSpawn({ x: -3, z: -3 }, geometry, 0.45);
    expect(spawn).not.toBeNull();
    if (!spawn) throw new Error("expected a constrained spawn");
    expect(Math.abs(spawn.x)).toBeLessThanOrEqual(1.55);
    expect(Math.abs(spawn.z)).toBeLessThanOrEqual(1.55);
  });

  it("keeps overlapping published-style floor regions available as one traversal area", () => {
    const xzFloor = (id: string, x: number) => node({
      id,
      kind: "floor",
      dimensions: { x: 4, y: 0, z: 4 },
      transform: [1, 0, 0, x, 0, 0, 1, 0, 0, -1, 0, 0, 0, 0, 0, 1],
    });
    const geometry = wheelchairMotionGeometry([xzFloor("first", 0), xzFloor("second", 3)]);
    expect(geometry.floors).toHaveLength(2);
    const spawn = wheelchairSpawn({ x: 0, z: 0 }, geometry, 0.45);
    expect(spawn).toEqual({ x: 0, z: 0 });
    expect(sweepWheelchair({ x: 0, z: 0 }, { x: 3, z: 0 }, geometry.obstacles, 0.45).reached).toBe(true);
  });

  it("does not drive or dock across a measured-floor gap", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "first-floor", kind: "floor", dimensions: { x: 4, y: 4, z: 0.05 } }),
      node({ id: "second-floor", kind: "floor", dimensions: { x: 4, y: 4, z: 0.05 }, x: 6 }),
    ]);
    const radius = 0.45;
    expect(sweepWheelchairInGeometry({ x: 0, z: 0 }, { x: 6, z: 0 }, geometry, radius).reached).toBe(false);

    const targetGeometry = wheelchairMotionGeometry([
      node({ id: "floor", kind: "floor", dimensions: { x: 4, y: 4, z: 0.05 } }),
      node({ id: "outside-target", kind: "object", dimensions: { x: 1, y: 1, z: 0.7 }, x: 4 }),
    ]);
    const target = targetGeometry.targets.find((rect) => rect.node.id === "outside-target");
    if (!target) throw new Error("expected target");
    const destination = dockPoint({ x: 0, z: 0 }, target, radius);
    expect(sweepWheelchairInGeometry({ x: 0, z: 0 }, { x: destination.x, z: destination.z }, targetGeometry, radius).reached).toBe(false);
  });

  it("finds a free spawn point on the measured floor", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "floor", kind: "floor", dimensions: { x: 8, y: 8, z: 0.05 } }),
      node({ id: "table", kind: "object", dimensions: { x: 1.5, y: 1.5, z: 0.7 } }),
    ]);
    const spawn = wheelchairSpawn({ x: 0, z: 0 }, geometry, 0.3);
    expect(spawn).not.toEqual({ x: 0, z: 0 });
    if (!spawn) throw new Error("expected a free spawn point");
    expect(collidesAt(spawn, geometry.obstacles, 0.3)).toBe(false);
    expect(Math.abs(spawn.x)).toBeLessThanOrEqual(3.7);
    expect(Math.abs(spawn.z)).toBeLessThanOrEqual(3.7);
  });

  it("reports when no free spawn exists instead of placing the wheelchair in a barrier", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "floor", kind: "floor", dimensions: { x: 1, y: 1, z: 0.05 } }),
      node({ id: "block", kind: "object", dimensions: { x: 1, y: 1, z: 0.7 } }),
    ]);
    expect(wheelchairSpawn({ x: 0, z: 0 }, geometry, 0.3)).toBeNull();
  });

  it("stops docking before a barrier instead of teleporting through it", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "wall", kind: "wall", dimensions: { x: 0.2, y: 6, z: 3 } }),
      node({ id: "table", kind: "object", dimensions: { x: 1, y: 1, z: 0.7 }, x: 2.5 }),
    ]);
    const target = geometry.targets[0];
    const start = { x: -3, z: 0 };
    const destination = dockPoint(start, target, 0.3);
    const move = sweepWheelchair(start, { x: destination.x - start.x, z: destination.z - start.z }, geometry.obstacles, 0.3);
    expect(move.reached).toBe(false);
    expect(move.point.x).toBeLessThan(0);
  });

  it("rests at a wall without collision pushes or drift", () => {
    const geometry = wheelchairMotionGeometry([node({ id: "wall", kind: "wall", dimensions: { x: 0.2, y: 6, z: 3 } })]);
    const first = sweepWheelchair({ x: -0.5, z: 0 }, { x: 1, z: 0 }, geometry.obstacles, 0.3);
    const second = sweepWheelchair(first.point, { x: 1, z: 0 }, geometry.obstacles, 0.3);
    expect(first.reached).toBe(false);
    expect(second.reached).toBe(false);
    expect(second.point).toEqual(first.point);
  });

  it("uses the selected circular radius consistently for spawning and movement", () => {
    const geometry = wheelchairMotionGeometry([
      node({ id: "floor", kind: "floor", dimensions: { x: 4, y: 4, z: 0.05 } }),
      node({ id: "table", kind: "object", dimensions: { x: 0.6, y: 0.6, z: 0.7 } }),
    ]);
    const radius = 0.6;
    const spawn = wheelchairSpawn({ x: 0, z: 0 }, geometry, radius);
    expect(spawn).not.toBeNull();
    if (!spawn) throw new Error("expected a clear point for the selected radius");
    expect(collidesAt(spawn, geometry.obstacles, radius)).toBe(false);
    expect(sweepWheelchair(spawn, { x: -4, z: 0 }, geometry.obstacles, radius).point).toBeDefined();
  });

  describe("assessOutletAccessibility", () => {
    const floor = node({ id: "floor", kind: "floor", dimensions: { x: 10, y: 10, z: 0.05 }, y: 0 });
    const wall = node({ id: "wall", kind: "wall", dimensions: { x: 6, y: 0.2, z: 3 }, y: 2 });
    const outlet: SceneNode = {
      id: "outlet-1",
      kind: "outlet",
      label: "Outlet 1",
      raw_category: "outlet",
      dimensions: { x: 0.12, y: 0.03, z: 0.12 },
      transform: { m: [1, 0, 0, 0, 0, 1, 0, 1.9, 0, 0, 1, 0.45, 0, 0, 0, 1] },
      quality: "measured",
      movable: false,
      labeled_by: "discovery",
      parent_id: "wall",
      relation: "mounted_on",
      attachment: {
        support_node_id: "wall",
        support_type: "lidar_surface",
        normal: { x: 0, y: -1, z: 0 },
        local_anchor: null,
        observed_region: [],
        localization_quality: "verified_support",
        identity_confidence: 0.95,
        review_status: "detected",
        uncertainty_reasons: [],
        sockets: [],
        observations: [],
      },
    };

    it("returns clear approach and within_reach when path is free and reach profile matches", () => {
      const geometry = wheelchairMotionGeometry([floor, wall, outlet]);
      const profile = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.75, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });
      const currentPos = { x: 0, z: 0 };
      const res = assessOutletAccessibility(currentPos, outlet, geometry, profile);
      expect(res.approachStatus).toBe("clear");
      expect(res.reachStatus).toBe("within_reach");
      expect(res.targetHeightAboveFloor).toBeCloseTo(0.45, 1);
      expect(res.disclaimers.length).toBeGreaterThan(0);
    });

    it("returns blocked when an obstacle blocks route to the outlet", () => {
      // Barrier between user and outlet
      const barrier = node({ id: "barrier", kind: "object", dimensions: { x: 8, y: 0.5, z: 2 }, y: 1 });
      const geometry = wheelchairMotionGeometry([floor, wall, barrier, outlet]);
      const profile = wheelchairProfile({ collisionRadius: 0.35 });
      const res = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, profile);
      expect(res.approachStatus).toBe("blocked");
      expect(res.unresolvedReasons.some((r) => r.includes("obstructed") || r.includes("No valid"))).toBe(true);
    });

    it("returns needs_verification when personalized reach profile is missing", () => {
      const geometry = wheelchairMotionGeometry([floor, wall, outlet]);
      const profile = wheelchairProfile({ reach: null });
      const res = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, profile);
      expect(res.reachStatus).toBe("needs_verification");
      expect(res.unresolvedReasons.some((r) => r.includes("reach profile"))).toBe(true);
    });

    it("differentiates two reach profiles with different reach limits", () => {
      const geometry = wheelchairMotionGeometry([floor, wall, outlet]);
      const shortReach = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.40, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });
      const longReach = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.85, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });

      const resShort = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, shortReach);
      const resLong = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, longReach);
      expect(resShort.reachStatus).toBe("outside_reach");
      expect(resLong.reachStatus).toBe("within_reach");
    });

    it("blocks wheelchair navigation through a narrow passage narrower than chair footprint", () => {
      // Two wall segments with a gap of 0.60 m between them (X from -5 to -0.3, and X from 0.3 to 5)
      const leftWall = node({ id: "left-wall", kind: "wall", dimensions: { x: 4.7, y: 0.2, z: 3 }, x: -2.65, y: 2 });
      const rightWall = node({ id: "right-wall", kind: "wall", dimensions: { x: 4.7, y: 0.2, z: 3 }, x: 2.65, y: 2 });
      const narrowGeometry = wheelchairMotionGeometry([floor, leftWall, rightWall]);
      // Wheelchair radius 0.40m (diameter 0.80m > 0.60m gap)
      const sweep = sweepWheelchairInGeometry({ x: 0, z: 0 }, { x: 0, z: -4 }, narrowGeometry, 0.40);
      expect(sweep.reached).toBe(false);
    });

    it("blocks approach to an outlet on the far side of a wall", () => {
      // Outlet is at y=2.1 with normal pointing away (+y in RoomPlan -> -z in Three.js)
      const farSideOutlet: SceneNode = {
        ...outlet,
        id: "far-side-outlet",
        transform: { m: [1, 0, 0, 0, 0, 1, 0, 2.1, 0, 0, 1, 0.45, 0, 0, 0, 1] },
        attachment: {
          ...outlet.attachment!,
          normal: { x: 0, y: 1, z: 0 }, // Normal points into +y (far side)
        },
      };
      const geometry = wheelchairMotionGeometry([floor, wall, farSideOutlet]);
      const profile = wheelchairProfile({ collisionRadius: 0.35 });
      // Chair is at y=0 (near side). Moving to the far side requires crossing the solid wall.
      const res = assessOutletAccessibility({ x: 0, z: 0 }, farSideOutlet, geometry, profile);
      expect(res.approachStatus).toBe("blocked");
      expect(res.unresolvedReasons.some((r) => r.includes("obstructed") || r.includes("No valid"))).toBe(true);
    });

    it("computes target height relative to local finished floor, not world origin", () => {
      // Raised platform floor at z = 0.40m
      const raisedFloor = node({
        id: "raised-floor",
        kind: "floor",
        dimensions: { x: 10, y: 10, z: 0.05 },
        transform: [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0.40, 0, 0, 0, 1],
      });
      // Outlet at world z = 0.85m
      const elevatedOutlet: SceneNode = {
        ...outlet,
        id: "elevated-outlet",
        transform: { m: [1, 0, 0, 0, 0, 1, 0, 1.9, 0, 0, 1, 0.85, 0, 0, 0, 1] },
      };
      const geometry = wheelchairMotionGeometry([raisedFloor, wall, elevatedOutlet]);
      const profile = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.80, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });
      const res = assessOutletAccessibility({ x: 0, z: 0 }, elevatedOutlet, geometry, profile);
      // Target height above floor should be 0.85 - 0.40 = 0.45m, NOT 0.85m!
      expect(res.targetHeightAboveFloor).toBeCloseTo(0.45, 2);
      expect(res.reachStatus).toBe("within_reach");
    });

    it("returns outside_reach when outlet is behind deep furniture", () => {
      // Deep desk (1.2m deep along Y) placed in front of wall outlet at Y=1.9
      const deepDesk = node({ id: "deep-desk", kind: "object", dimensions: { x: 1.5, y: 1.2, z: 0.75 }, x: 0, y: 1.3 });
      const geometry = wheelchairMotionGeometry([floor, wall, deepDesk, outlet]);
      const profile = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.50, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });
      const res = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, profile);
      // Chair can approach the room, but stopping position is stopped by desk, so reach to wall outlet exceeds 0.50m
      expect(res.reachStatus).toBe("outside_reach");
      expect(res.unresolvedReasons.some((r) => r.includes("exceeds maximum modeled reach"))).toBe(true);
    });

    it("flags uncertainty when reach distance is close to the threshold (90-100%)", () => {
      const geometry = wheelchairMotionGeometry([floor, wall, outlet]);
      // The stopping candidate chosen closest to chair at (0,0) is at dist = 0.65m from outlet.
      // With maxReachDistance = 0.70m, reachDistance (0.65m) is within 90%-100% of maxReach (0.63m - 0.70m).
      const borderlineProfile = wheelchairProfile({
        collisionRadius: 0.35,
        reach: { maxReachDistance: 0.70, minReachHeight: 0.38, maxReachHeight: 1.22 },
      });
      const res = assessOutletAccessibility({ x: 0, z: 0 }, outlet, geometry, borderlineProfile);
      expect(res.reachStatus).toBe("needs_verification");
      expect(res.unresolvedReasons.some((r) => r.includes("close to threshold"))).toBe(true);
    });

    it("invalidates approach from clear to blocked after an obstacle is introduced", () => {
      const profile = wheelchairProfile({ collisionRadius: 0.35 });
      const initialGeometry = wheelchairMotionGeometry([floor, wall, outlet]);
      const initialRes = assessOutletAccessibility({ x: 0, z: 0 }, outlet, initialGeometry, profile);
      expect(initialRes.approachStatus).toBe("clear");

      // Move a barrier directly in the path between start and outlet
      const barrier = node({ id: "barrier", kind: "object", dimensions: { x: 8, y: 0.5, z: 2 }, y: 1.0 });
      const updatedGeometry = wheelchairMotionGeometry([floor, wall, barrier, outlet]);
      const updatedRes = assessOutletAccessibility({ x: 0, z: 0 }, outlet, updatedGeometry, profile);
      expect(updatedRes.approachStatus).toBe("blocked");
    });
  });
});

