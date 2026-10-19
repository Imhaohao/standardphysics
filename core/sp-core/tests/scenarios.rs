//! Hand-computed scenes evaluated against the repo rulepacks.

mod common;

use sp_core::Engine;
use sp_core::geometry::{Polygon2, Vec2, Vec3};
use sp_core::mesh::{MeshClass, MeshPart, ScanMesh};
use sp_core::rules::{Finding, Status};
use sp_core::scene::{Object, ObjectSource, Opening, OpeningKind, Room, RoomConnection, RoomKind, Scene, Wall};
use sp_core::units::{inches, to_inches};

/// Rectangular room with walls w0 (south, y = min) .. w3 (west), going counter-clockwise.
fn rect_room(id: &str, kind: RoomKind, width: f64, depth: f64) -> Room {
    let c = [Vec2::new(0.0, 0.0), Vec2::new(width, 0.0), Vec2::new(width, depth), Vec2::new(0.0, depth)];
    Room {
        id: id.into(),
        name: id.into(),
        kind,
        storey: 0,
        floor: Polygon2::new(c.to_vec()),
        ceiling_height: 2.7,
        walls: (0..4)
            .map(|i| Wall { id: format!("{id}-w{i}"), start: c[i], end: c[(i + 1) % 4], height: 2.7, thickness: 0.1 })
            .collect(),
        openings: vec![],
        objects: vec![],
    }
}

/// A door in the south wall centred at `x`, with frame width `width`.
fn south_door(room: &Room, id: &str, x: f64, width: f64) -> Opening {
    Opening {
        id: id.into(),
        kind: OpeningKind::Door,
        wall_id: format!("{}-w0", room.id),
        center: Vec3::new(x, 1.0, 0.0),
        width,
        height: 2.03,
        swing: None,
        hardware: None,
    }
}

fn object(id: &str, category: &str, center: Vec2, size: Vec3, bottom: f64) -> Object {
    Object {
        id: id.into(),
        category: category.into(),
        center: Vec3::new(center.x, bottom + size.y / 2.0, center.y),
        size,
        yaw: 0.0,
        top_height: bottom + size.y,
        confidence: 0.9,
        source: ObjectSource::Detector,
        attributes: Default::default(),
    }
}

fn evaluate(rooms: Vec<Room>) -> Option<(Engine, Vec<Finding>)> {
    let mut engine = common::repo_engine()?;
    engine.set_scene(Scene { rooms, ..Scene::default() });
    engine.evaluate_all();
    let findings = engine.findings();
    Some((engine, findings))
}

fn finding<'a>(findings: &'a [Finding], rule_id: &str, subject: &str) -> &'a Finding {
    findings
        .iter()
        .find(|f| f.rule_id == rule_id && f.subject_id == subject)
        .unwrap_or_else(|| panic!("no {rule_id} finding for {subject}"))
}

fn shop_with_door(frame_width: f64) -> Room {
    let mut shop = rect_room("shop", RoomKind::Shop, 6.0, 5.0);
    shop.openings.push(south_door(&shop, "entry", 3.0, frame_width));
    shop
}

#[test]
fn thirty_six_inch_door_passes_clear_width() {
    let Some((_, findings)) = evaluate(vec![shop_with_door(inches(36.0) + inches(2.0))]) else { return };
    let f = finding(&findings, "ADA-404.2.3-clear-width", "entry");
    assert_eq!(f.status, Status::Pass, "{}", f.message);
    let measured = f.measured.as_ref().unwrap();
    assert!((measured.lo.unwrap() - 35.5).abs() < 0.01 && (measured.hi.unwrap() - 36.5).abs() < 0.01, "{measured:?}");
}

#[test]
fn narrow_door_with_nothing_scanned_behind_it_is_a_question() {
    let Some((_, findings)) = evaluate(vec![shop_with_door(inches(30.0))]) else { return };
    let f = finding(&findings, "ADA-404.2.3-clear-width", "entry");
    assert_eq!(f.status, Status::NeedsInfo, "{}", f.message);
}

/// A shop whose entry door leads into a scanned hall, so the door is known to be walked through.
fn shop_and_hall(frame_width: f64) -> Option<Engine> {
    let mut engine = common::repo_engine()?;
    let rooms = vec![shop_with_door(frame_width), rect_room("hall", RoomKind::Corridor, 6.0, 2.0)];
    let connections =
        vec![RoomConnection { from_room: "shop".into(), to_room: "hall".into(), opening_id: Some("entry".into()) }];
    engine.set_scene(Scene { rooms, connections, ..Scene::default() });
    engine.evaluate_all();
    Some(engine)
}

#[test]
fn thirty_inch_door_between_scanned_rooms_fails_clear_width() {
    let Some(engine) = shop_and_hall(inches(30.0)) else { return };
    assert_eq!(finding(&engine.findings(), "ADA-404.2.3-clear-width", "entry").status, Status::Fail);
}

#[test]
fn forty_two_inch_counter_fails_904_4_1() {
    let mut shop = shop_with_door(inches(38.0));
    shop.objects.push(object("counter", "counter", Vec2::new(3.0, 4.0), Vec3::new(2.4, inches(42.0), 0.6), 0.0));
    let Some((_, findings)) = evaluate(vec![shop]) else { return };
    let f = finding(&findings, "ADA-904.4.1-parallel", "counter");
    assert_eq!(f.status, Status::Fail, "{}", f.message);
    assert!((f.measured.as_ref().unwrap().value.unwrap() - 42.0).abs() < 0.01, "{:?}", f.measured);
    assert_eq!(finding(&findings, "ADA-904.4.2-forward", "counter").status, Status::NotApplicable);
}

#[test]
fn thirty_four_inch_counter_passes_904_4_1() {
    let mut shop = shop_with_door(inches(38.0));
    shop.objects.push(object("counter", "counter", Vec2::new(3.0, 4.0), Vec3::new(2.4, inches(34.0), 0.6), 0.0));
    let Some((_, findings)) = evaluate(vec![shop]) else { return };
    assert_eq!(finding(&findings, "ADA-904.4.1-parallel", "counter").status, Status::Pass);
}

/// 1.5 m corridor, 8 m long, door at the south end, a drinking fountain at the north end, and a
/// cabinet that pinches the corridor to 30 in halfway along.
fn pinched_corridor(pinch: f64) -> Room {
    let mut corridor = rect_room("corridor", RoomKind::Corridor, 1.5, 8.0);
    corridor.openings.push(south_door(&corridor, "entry", 0.75, inches(38.0)));
    let cabinet_width = 1.5 - 0.1 - pinch;
    corridor.objects.push(object(
        "cabinet",
        "storage",
        Vec2::new(1.5 - 0.05 - cabinet_width / 2.0, 4.0),
        Vec3::new(cabinet_width, 0.9, 0.6),
        0.0,
    ));
    corridor.objects.push(object(
        "fountain",
        "drinking_fountain",
        Vec2::new(0.75, 7.75),
        Vec3::new(0.5, 0.9, 0.4),
        0.0,
    ));
    corridor
}

#[test]
fn corridor_pinched_to_thirty_inches_fails_route_width_at_the_pinch() {
    let Some((engine, findings)) = evaluate(vec![pinched_corridor(inches(30.0))]) else { return };
    let route = engine.analysis(0).unwrap().route_to("fountain").unwrap();
    let leg = route.leg.as_ref().unwrap();
    let width = to_inches(leg.min_clear_width.unwrap());
    assert!((width - 30.0).abs() <= 1.5, "measured {width} in");
    let pinch = &leg.pinches[0];
    assert!((pinch.location.y - 4.0).abs() < 0.35, "pinch at {:?}", pinch.location);
    let f = finding(&findings, "ADA-403.5.1-clear-width", "route:fountain");
    assert_eq!(f.status, Status::Fail, "{}", f.message);
    assert!(f.location.is_some_and(|l| (l.z - 4.0).abs() < 0.35));
}

#[test]
fn corridor_with_forty_inches_passes_route_width() {
    let Some((_, findings)) = evaluate(vec![pinched_corridor(inches(40.0))]) else { return };
    assert_eq!(finding(&findings, "ADA-403.5.1-clear-width", "route:fountain").status, Status::Pass);
}

fn restroom(width: f64, depth: f64) -> Room {
    let mut room = rect_room("wc", RoomKind::Restroom, width, depth);
    room.openings.push(south_door(&room, "wc-door", width / 2.0, inches(38.0)));
    room
}

#[test]
fn sixty_inch_turning_circle_fits_in_a_68_inch_restroom() {
    let Some((engine, findings)) = evaluate(vec![restroom(inches(68.0), inches(68.0))]) else { return };
    let diameter = engine.analysis(0).unwrap().turning_diameter("wc").unwrap();
    assert!(to_inches(diameter) >= 60.0, "{}", to_inches(diameter));
    assert_eq!(finding(&findings, "ADA-304.3-turning-space", "wc").status, Status::Pass);
}

#[test]
fn turning_space_does_not_fit_in_a_54_inch_restroom() {
    let Some((engine, findings)) = evaluate(vec![restroom(inches(54.0), inches(80.0))]) else { return };
    let diameter = to_inches(engine.analysis(0).unwrap().turning_diameter("wc").unwrap());
    assert!(diameter < 60.0 && diameter > 50.0, "{diameter}");
    assert_eq!(finding(&findings, "ADA-304.3-turning-space", "wc").status, Status::Fail);
}

#[test]
fn unknowns_are_never_reported_as_pass() {
    let Some((_, findings)) = evaluate(vec![shop_with_door(inches(38.0))]) else { return };
    let passes_without_value = findings
        .iter()
        .filter(|f| f.status == Status::Pass && f.measured.is_none())
        .map(|f| &f.rule_id)
        .collect::<Vec<_>>();
    assert!(passes_without_value.is_empty(), "{passes_without_value:?}");
}

#[test]
fn stricter_jurisdiction_governs() {
    let Some(engine) = shop_and_hall(inches(30.0)) else { return };
    let report = engine.report();
    let governing = report
        .governing
        .iter()
        .find(|g| g.subject_id == "entry" && g.rule_ids.iter().any(|r| r == "ADA-404.2.3-clear-width"))
        .unwrap();
    assert_eq!(governing.status, Status::Fail);
    assert_eq!(report.jurisdictions.len(), 2);
}

#[test]
fn update_room_matches_full_evaluation() {
    let Some(mut engine) = common::repo_engine() else { return };
    let mut shop = shop_with_door(inches(38.0));
    let corridor = pinched_corridor(inches(30.0));
    shop.storey = 1;
    engine.set_scene(Scene { rooms: vec![shop.clone(), corridor.clone()], ..Scene::default() });
    let full = engine.evaluate_all();
    shop.objects.push(object("counter", "counter", Vec2::new(3.0, 4.0), Vec3::new(2.4, inches(42.0), 0.6), 0.0));
    let touched = engine.update_room(shop.clone());
    assert!(touched.iter().all(|f| f.room_id.as_deref() != Some("corridor")), "corridor storey re-evaluated");
    assert!(touched.iter().any(|f| f.subject_id == "counter"));
    let incremental = engine.report();
    let mut fresh = common::repo_engine().unwrap();
    fresh.set_scene(engine.scene().clone());
    let expected = fresh.evaluate_all();
    assert_eq!(incremental.governing_counts, expected.governing_counts);
    assert_ne!(full.governing_counts, expected.governing_counts);
}

/// A floor mesh over `width` x `depth` metres of 10 cm triangles, with height given by `height_at(x, z)`.
fn floor_mesh(width: f64, depth: f64, height_at: impl Fn(f64, f64) -> f64) -> ScanMesh {
    const STEP: f64 = 0.1;
    let (nx, nz) = ((width / STEP).round() as u32, (depth / STEP).round() as u32);
    let vertex = |i: u32, j: u32| {
        let (x, z) = (f64::from(i) * STEP, f64::from(j) * STEP);
        Vec3::new(x, height_at(x, z), z)
    };
    let vertices = (0..=nz).flat_map(|j| (0..=nx).map(move |i| (i, j))).map(|(i, j)| vertex(i, j)).collect();
    let at = |i: u32, j: u32| j * (nx + 1) + i;
    let faces = (0..nz)
        .flat_map(|j| (0..nx).map(move |i| (i, j)))
        .flat_map(|(i, j)| [[at(i, j), at(i + 1, j), at(i + 1, j + 1)], [at(i, j), at(i + 1, j + 1), at(i, j + 1)]])
        .collect::<Vec<_>>();
    let classes = Some(vec![MeshClass::Floor; faces.len()]);
    let identity = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0];
    ScanMesh { floor_y: 0.0, parts: vec![MeshPart { id: [1; 16], transform: identity, vertices, faces, classes }] }
}

fn evaluate_with_mesh(room: Room, mesh: ScanMesh) -> Option<Vec<Finding>> {
    let mut engine = common::repo_engine()?;
    let decoded = ScanMesh::from_bytes(&mesh.to_bytes()).expect("synthetic mesh decodes");
    engine.set_room_mesh(&room.id, decoded);
    engine.set_scene(Scene { rooms: vec![room], ..Scene::default() });
    engine.evaluate_all();
    Some(engine.findings())
}

#[test]
fn route_slope_needs_a_mesh_and_is_judged_from_one() {
    let Some((_, findings)) = evaluate(vec![pinched_corridor(inches(40.0))]) else { return };
    assert_eq!(finding(&findings, "ADA-402.2-running-slope", "route:fountain").status, Status::NeedsInfo);
    let Some(flat) = evaluate_with_mesh(pinched_corridor(inches(40.0)), floor_mesh(1.5, 8.0, |_, _| 0.0)) else {
        return;
    };
    assert_eq!(finding(&flat, "ADA-402.2-running-slope", "route:fountain").status, Status::Pass);
    assert_eq!(finding(&flat, "ADA-303.2-level-change", "route:fountain").status, Status::Pass);
    let ramp = floor_mesh(1.5, 8.0, |_, z| z / 12.0);
    let Some(sloped) = evaluate_with_mesh(pinched_corridor(inches(40.0)), ramp) else { return };
    let f = finding(&sloped, "ADA-402.2-running-slope", "route:fountain");
    assert_eq!(f.status, Status::Fail, "{}", f.message);
    let tilted = floor_mesh(1.5, 8.0, |x, _| x / 30.0);
    let Some(tilted) = evaluate_with_mesh(pinched_corridor(inches(40.0)), tilted) else { return };
    assert_eq!(finding(&tilted, "ADA-403.3-cross-slope", "route:fountain").status, Status::Fail);
    assert_eq!(finding(&tilted, "ADA-402.2-running-slope", "route:fountain").status, Status::Pass);
}

#[test]
fn a_one_inch_step_in_the_corridor_fails_the_level_change_rule() {
    let step = floor_mesh(1.5, 8.0, |_, z| if z > 2.05 { inches(1.0) } else { 0.0 });
    let Some(findings) = evaluate_with_mesh(pinched_corridor(inches(40.0)), step) else { return };
    let f = finding(&findings, "ADA-303.2-level-change", "route:fountain");
    assert_eq!(f.status, Status::Fail, "{}", f.message);
    assert!(f.location.is_some_and(|l| (l.z - 2.05).abs() < 0.15), "{:?}", f.location);
    assert_eq!(finding(&findings, "ADA-303.2-level-change", "floor:corridor").status, Status::Fail);
}

#[test]
fn seat_geometry_from_the_mesh_narrows_the_route() {
    let mut mesh = floor_mesh(1.5, 8.0, |_, _| 0.0);
    let mut chair = floor_mesh(0.9, 0.5, |_, _| 0.45);
    chair.parts[0].vertices.iter_mut().for_each(|v| (v.x, v.z) = (v.x + 0.05, v.z + 5.5));
    chair.parts[0].classes = Some(vec![MeshClass::Seat; chair.parts[0].faces.len()]);
    mesh.parts.extend(chair.parts);
    let Some(findings) = evaluate_with_mesh(pinched_corridor(inches(40.0)), mesh) else { return };
    let f = finding(&findings, "ADA-403.5.1-clear-width", "route:fountain");
    assert_eq!(f.status, Status::Fail, "{}", f.message);
}

#[test]
fn updating_one_storey_keeps_the_route_findings_of_the_others() {
    let Some(mut engine) = common::repo_engine() else { return };
    let ground = pinched_corridor(inches(30.0));
    let mut upper = rect_room("upper-corridor", RoomKind::Corridor, 1.5, 8.0);
    upper.storey = 1;
    upper.openings.push(south_door(&upper, "upper-entry", 0.75, inches(38.0)));
    upper.objects.push(object(
        "upper-fountain",
        "drinking_fountain",
        Vec2::new(0.75, 7.75),
        Vec3::new(0.5, 0.9, 0.4),
        0.0,
    ));
    engine.set_scene(Scene { rooms: vec![ground.clone(), upper.clone()], ..Scene::default() });
    engine.evaluate_all();
    let route_findings =
        |engine: &Engine, subject: &str| engine.findings().into_iter().filter(|f| f.subject_id == subject).count();
    let ground_routes = route_findings(&engine, "route:fountain");
    let upper_routes = route_findings(&engine, "route:upper-fountain");
    assert!(ground_routes > 0 && upper_routes > 0);

    upper.name = "renamed".into();
    engine.update_room(upper);
    assert_eq!(route_findings(&engine, "route:fountain"), ground_routes, "other storey kept");
    assert_eq!(route_findings(&engine, "route:upper-fountain"), upper_routes, "updated storey rebuilt");

    engine.update_room(ground);
    assert_eq!(route_findings(&engine, "route:fountain"), ground_routes);
    assert_eq!(route_findings(&engine, "route:upper-fountain"), upper_routes, "other storey kept");
}

#[test]
fn microwave_gets_reach_range_checks() {
    let mut shop = shop_with_door(inches(38.0));
    shop.objects.push(object("microwave", "microwave", Vec2::new(3.0, 4.6), Vec3::new(0.5, 0.3, 0.4), inches(54.0)));
    let Some((_, findings)) = evaluate(vec![shop]) else { return };
    let reach = findings.iter().filter(|f| f.subject_id == "microwave" && f.rule_id.starts_with("ADA-308")).count();
    assert!(reach > 0, "no reach-range findings for the microwave");
}
