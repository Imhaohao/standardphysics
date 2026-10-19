//! Swift-facing mirrors of the Scene and Finding types, with conversions to and from `sp-core`.

use sp_core::geometry::{Polygon2, Vec2, Vec3};
use sp_core::rules::{Finding, GoverningFinding, Report, Status};
use sp_core::scene::{self, ObjectSource, ObservationSource, ObservationValue, OpeningKind, RoomKind};
use std::collections::HashMap;

#[derive(Debug, Clone, Copy, PartialEq, uniffi::Record)]
pub struct SpVec2 {
    pub x: f64,
    pub y: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, uniffi::Record)]
pub struct SpVec3 {
    pub x: f64,
    pub y: f64,
    pub z: f64,
}

impl From<Vec2> for SpVec2 {
    fn from(v: Vec2) -> Self {
        Self { x: v.x, y: v.y }
    }
}

impl From<SpVec2> for Vec2 {
    fn from(v: SpVec2) -> Self {
        Vec2::new(v.x, v.y)
    }
}

impl From<Vec3> for SpVec3 {
    fn from(v: Vec3) -> Self {
        Self { x: v.x, y: v.y, z: v.z }
    }
}

impl From<SpVec3> for Vec3 {
    fn from(v: SpVec3) -> Self {
        Vec3::new(v.x, v.y, v.z)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum SpRoomKind {
    Shop,
    Restaurant,
    Restroom,
    Office,
    Corridor,
    Kitchen,
    Storage,
    Other,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum SpOpeningKind {
    Door,
    Window,
    Opening,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum SpObjectSource {
    Roomplan,
    Detector,
    Mesh,
    Owner,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum SpObservationSource {
    Measured,
    Photo,
    Owner,
}

#[derive(Debug, Clone, PartialEq, uniffi::Enum)]
pub enum SpObservationValue {
    Bool { value: bool },
    Number { value: f64 },
    Text { value: String },
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpWall {
    pub id: String,
    pub start: SpVec2,
    pub end: SpVec2,
    pub height: f64,
    pub thickness: f64,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpDoorSwing {
    pub hinge_left: bool,
    pub swings_in: bool,
    pub leaves: u32,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpOpening {
    pub id: String,
    pub kind: SpOpeningKind,
    pub wall_id: String,
    pub center: SpVec3,
    pub width: f64,
    pub height: f64,
    pub swing: Option<SpDoorSwing>,
    pub hardware: Option<String>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpObject {
    pub id: String,
    pub category: String,
    pub center: SpVec3,
    pub size: SpVec3,
    pub yaw: f64,
    pub top_height: f64,
    pub confidence: f64,
    pub source: SpObjectSource,
    pub attributes: HashMap<String, String>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpRoom {
    pub id: String,
    pub name: String,
    pub kind: SpRoomKind,
    pub storey: i32,
    pub floor: Vec<SpVec2>,
    pub ceiling_height: f64,
    pub walls: Vec<SpWall>,
    pub openings: Vec<SpOpening>,
    pub objects: Vec<SpObject>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpObservation {
    pub id: String,
    pub subject_id: String,
    pub metric: String,
    pub value: SpObservationValue,
    pub unit: Option<String>,
    pub source: SpObservationSource,
    pub confidence: f64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Enum)]
pub enum SpStatus {
    Pass,
    Fail,
    NeedsInfo,
    NotApplicable,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpMeasured {
    pub text: String,
    pub value: Option<f64>,
    pub lo: Option<f64>,
    pub hi: Option<f64>,
    pub unit: String,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpFinding {
    pub rule_id: String,
    pub jurisdiction: String,
    pub section: String,
    pub title: String,
    pub subject_id: String,
    pub room_id: Option<String>,
    pub status: SpStatus,
    pub measured: Option<SpMeasured>,
    pub required: String,
    pub message: String,
    pub evidence: String,
    pub severity: String,
    pub location: Option<SpVec3>,
    pub counterpart: Option<String>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpGoverningFinding {
    pub subject_id: String,
    pub status: SpStatus,
    pub governing_rule_id: String,
    pub governing_jurisdiction: String,
    pub rule_ids: Vec<String>,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpStatusCounts {
    pub pass: u32,
    pub fail: u32,
    pub needs_info: u32,
    pub not_applicable: u32,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpJurisdictionReport {
    pub jurisdiction: String,
    pub counts: SpStatusCounts,
    pub findings: Vec<SpFinding>,
}

#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SpReport {
    pub jurisdictions: Vec<SpJurisdictionReport>,
    pub governing: Vec<SpGoverningFinding>,
    pub governing_counts: SpStatusCounts,
}

macro_rules! mirror_enum {
    ($from:ty, $to:ty, $($variant:ident),+) => {
        impl From<$from> for $to {
            fn from(value: $from) -> Self {
                match value { $(<$from>::$variant => <$to>::$variant),+ }
            }
        }
        impl From<$to> for $from {
            fn from(value: $to) -> Self {
                match value { $(<$to>::$variant => <$from>::$variant),+ }
            }
        }
    };
}

mirror_enum!(RoomKind, SpRoomKind, Shop, Restaurant, Restroom, Office, Corridor, Kitchen, Storage, Other);
mirror_enum!(OpeningKind, SpOpeningKind, Door, Window, Opening);
mirror_enum!(ObjectSource, SpObjectSource, Roomplan, Detector, Mesh, Owner);
mirror_enum!(ObservationSource, SpObservationSource, Measured, Photo, Owner);
mirror_enum!(Status, SpStatus, Pass, Fail, NeedsInfo, NotApplicable);

impl From<ObservationValue> for SpObservationValue {
    fn from(value: ObservationValue) -> Self {
        match value {
            ObservationValue::Bool(value) => SpObservationValue::Bool { value },
            ObservationValue::Number(value) => SpObservationValue::Number { value },
            ObservationValue::Text(value) => SpObservationValue::Text { value },
        }
    }
}

impl From<SpObservationValue> for ObservationValue {
    fn from(value: SpObservationValue) -> Self {
        match value {
            SpObservationValue::Bool { value } => ObservationValue::Bool(value),
            SpObservationValue::Number { value } => ObservationValue::Number(value),
            SpObservationValue::Text { value } => ObservationValue::Text(value),
        }
    }
}

impl From<scene::Wall> for SpWall {
    fn from(w: scene::Wall) -> Self {
        Self { id: w.id, start: w.start.into(), end: w.end.into(), height: w.height, thickness: w.thickness }
    }
}

impl From<SpWall> for scene::Wall {
    fn from(w: SpWall) -> Self {
        Self { id: w.id, start: w.start.into(), end: w.end.into(), height: w.height, thickness: w.thickness }
    }
}

impl From<scene::DoorSwing> for SpDoorSwing {
    fn from(s: scene::DoorSwing) -> Self {
        Self { hinge_left: s.hinge == scene::HingeSide::Left, swings_in: s.swings_in, leaves: s.leaves }
    }
}

impl From<SpDoorSwing> for scene::DoorSwing {
    fn from(s: SpDoorSwing) -> Self {
        let hinge = if s.hinge_left { scene::HingeSide::Left } else { scene::HingeSide::Right };
        Self { hinge, swings_in: s.swings_in, leaves: s.leaves }
    }
}

impl From<scene::Opening> for SpOpening {
    fn from(o: scene::Opening) -> Self {
        Self {
            id: o.id,
            kind: o.kind.into(),
            wall_id: o.wall_id,
            center: o.center.into(),
            width: o.width,
            height: o.height,
            swing: o.swing.map(Into::into),
            hardware: o.hardware,
        }
    }
}

impl From<SpOpening> for scene::Opening {
    fn from(o: SpOpening) -> Self {
        Self {
            id: o.id,
            kind: o.kind.into(),
            wall_id: o.wall_id,
            center: o.center.into(),
            width: o.width,
            height: o.height,
            swing: o.swing.map(Into::into),
            hardware: o.hardware,
        }
    }
}

impl From<scene::Object> for SpObject {
    fn from(o: scene::Object) -> Self {
        Self {
            id: o.id,
            category: o.category,
            center: o.center.into(),
            size: o.size.into(),
            yaw: o.yaw,
            top_height: o.top_height,
            confidence: o.confidence,
            source: o.source.into(),
            attributes: o.attributes.into_iter().collect(),
        }
    }
}

impl From<SpObject> for scene::Object {
    fn from(o: SpObject) -> Self {
        Self {
            id: o.id,
            category: o.category,
            center: o.center.into(),
            size: o.size.into(),
            yaw: o.yaw,
            top_height: o.top_height,
            confidence: o.confidence,
            source: o.source.into(),
            attributes: o.attributes.into_iter().collect(),
        }
    }
}

impl From<scene::Room> for SpRoom {
    fn from(r: scene::Room) -> Self {
        Self {
            id: r.id,
            name: r.name,
            kind: r.kind.into(),
            storey: r.storey,
            floor: r.floor.points.into_iter().map(Into::into).collect(),
            ceiling_height: r.ceiling_height,
            walls: r.walls.into_iter().map(Into::into).collect(),
            openings: r.openings.into_iter().map(Into::into).collect(),
            objects: r.objects.into_iter().map(Into::into).collect(),
        }
    }
}

impl From<SpRoom> for scene::Room {
    fn from(r: SpRoom) -> Self {
        Self {
            id: r.id,
            name: r.name,
            kind: r.kind.into(),
            storey: r.storey,
            floor: Polygon2::new(r.floor.into_iter().map(Into::into).collect()),
            ceiling_height: r.ceiling_height,
            walls: r.walls.into_iter().map(Into::into).collect(),
            openings: r.openings.into_iter().map(Into::into).collect(),
            objects: r.objects.into_iter().map(Into::into).collect(),
        }
    }
}

impl From<SpObservation> for scene::Observation {
    fn from(o: SpObservation) -> Self {
        Self {
            id: o.id,
            subject_id: o.subject_id,
            metric: o.metric,
            value: o.value.into(),
            unit: o.unit,
            source: o.source.into(),
            confidence: o.confidence,
        }
    }
}

impl From<scene::Observation> for SpObservation {
    fn from(o: scene::Observation) -> Self {
        Self {
            id: o.id,
            subject_id: o.subject_id,
            metric: o.metric,
            value: o.value.into(),
            unit: o.unit,
            source: o.source.into(),
            confidence: o.confidence,
        }
    }
}

impl From<Finding> for SpFinding {
    fn from(f: Finding) -> Self {
        Self {
            rule_id: f.rule_id,
            jurisdiction: f.jurisdiction,
            section: f.section,
            title: f.title,
            subject_id: f.subject_id,
            room_id: f.room_id,
            status: f.status.into(),
            measured: f.measured.map(|m| SpMeasured { text: m.text, value: m.value, lo: m.lo, hi: m.hi, unit: m.unit }),
            required: f.required,
            message: f.message,
            evidence: f.evidence,
            severity: f.severity,
            location: f.location.map(Into::into),
            counterpart: f.counterpart,
        }
    }
}

impl From<GoverningFinding> for SpGoverningFinding {
    fn from(g: GoverningFinding) -> Self {
        Self {
            subject_id: g.subject_id,
            status: g.status.into(),
            governing_rule_id: g.governing_rule_id,
            governing_jurisdiction: g.governing_jurisdiction,
            rule_ids: g.rule_ids,
            message: g.message,
        }
    }
}

fn counts(c: sp_core::rules::StatusCounts) -> SpStatusCounts {
    let n = |v: usize| u32::try_from(v).unwrap_or(u32::MAX);
    SpStatusCounts {
        pass: n(c.pass),
        fail: n(c.fail),
        needs_info: n(c.needs_info),
        not_applicable: n(c.not_applicable),
    }
}

impl From<Report> for SpReport {
    fn from(r: Report) -> Self {
        Self {
            jurisdictions: r
                .jurisdictions
                .into_iter()
                .map(|j| SpJurisdictionReport {
                    jurisdiction: j.jurisdiction,
                    counts: counts(j.counts),
                    findings: j.findings.into_iter().map(Into::into).collect(),
                })
                .collect(),
            governing: r.governing.into_iter().map(Into::into).collect(),
            governing_counts: counts(r.governing_counts),
        }
    }
}
