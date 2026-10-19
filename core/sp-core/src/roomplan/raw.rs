//! Serde mirror of RoomPlan's Codable output. Only the fields the engine reads are declared.

use crate::geometry::{Vec2, Vec3};
use serde::Deserialize;
use serde_json::Value;
use std::collections::BTreeMap;

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct CapturedRoom {
    pub identifier: Option<String>,
    pub story: i32,
    pub version: i32,
    pub walls: Vec<Surface>,
    pub doors: Vec<Surface>,
    pub windows: Vec<Surface>,
    pub openings: Vec<Surface>,
    pub floors: Vec<Surface>,
    pub objects: Vec<CapturedObject>,
    pub sections: Vec<Section>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct CapturedStructure {
    pub rooms: Vec<CapturedRoom>,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Surface {
    pub identifier: String,
    pub parent_identifier: Option<String>,
    pub category: BTreeMap<String, Value>,
    pub confidence: BTreeMap<String, Value>,
    pub dimensions: [f64; 3],
    pub polygon_corners: Vec<[f64; 3]>,
    pub transform: Transform,
    pub story: i32,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct CapturedObject {
    pub identifier: String,
    pub parent_identifier: Option<String>,
    pub category: BTreeMap<String, Value>,
    pub confidence: BTreeMap<String, Value>,
    pub dimensions: [f64; 3],
    pub transform: Transform,
    pub attributes: BTreeMap<String, Value>,
    pub story: i32,
}

#[derive(Debug, Clone, Deserialize, Default)]
#[serde(rename_all = "camelCase", default)]
pub struct Section {
    pub label: String,
    pub center: [f64; 3],
    pub story: i32,
}

/// A 4x4 column-major affine transform (`simd_float4x4` encoded as 16 floats).
#[derive(Debug, Clone, Copy, PartialEq, Deserialize)]
#[serde(from = "Vec<f64>")]
pub struct Transform(pub [f64; 16]);

impl Default for Transform {
    fn default() -> Self {
        let mut m = [0.0; 16];
        m[0] = 1.0;
        m[5] = 1.0;
        m[10] = 1.0;
        m[15] = 1.0;
        Transform(m)
    }
}

impl From<Vec<f64>> for Transform {
    fn from(values: Vec<f64>) -> Self {
        if values.len() != 16 {
            return Transform::default();
        }
        let mut m = [0.0; 16];
        m.copy_from_slice(&values);
        Transform(m)
    }
}

impl Transform {
    fn column(&self, index: usize) -> Vec3 {
        let m = &self.0;
        Vec3::new(m[index * 4], m[index * 4 + 1], m[index * 4 + 2])
    }

    pub fn translation(&self) -> Vec3 {
        self.column(3)
    }

    pub fn apply(&self, local: Vec3) -> Vec3 {
        let (cx, cy, cz, t) = (self.column(0), self.column(1), self.column(2), self.column(3));
        Vec3::new(
            cx.x * local.x + cy.x * local.y + cz.x * local.z + t.x,
            cx.y * local.x + cy.y * local.y + cz.y * local.z + t.y,
            cx.z * local.x + cy.z * local.y + cz.z * local.z + t.z,
        )
    }

    /// Rotation about +Y of the local X axis, matching [`crate::geometry::yaw_axes`].
    pub fn yaw(&self) -> f64 {
        let x_axis = self.column(0);
        (-x_axis.z).atan2(x_axis.x)
    }

    /// Plan direction of the local X axis.
    pub fn plan_x_axis(&self) -> Vec2 {
        let x_axis = self.column(0);
        Vec2::new(x_axis.x, x_axis.z).normalized()
    }
}

/// The single key of a Swift enum encoded as `{"case": {...}}`.
pub fn enum_case(category: &BTreeMap<String, Value>) -> &str {
    category.keys().next().map(String::as_str).unwrap_or("unknown")
}

pub fn confidence_value(confidence: &BTreeMap<String, Value>) -> f64 {
    match enum_case(confidence) {
        "high" => 0.9,
        "medium" => 0.6,
        "low" => 0.3,
        _ => 0.5,
    }
}
