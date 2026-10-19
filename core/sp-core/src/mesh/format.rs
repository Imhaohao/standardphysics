//! The SPM1 scan-mesh file written by the iOS capture (little-endian):
//! `"SPM1"`, u32 version, f32 floor y, u32 part count, then per part a 16-byte UUID, a
//! column-major 4x4 f32 transform, u32 vertex count, u32 face count, u8 has-classification,
//! f32 xyz vertices, u32 triangle indices and (when flagged) one ARMeshClassification byte per face.

use crate::geometry::Vec3;

const MAGIC: &[u8; 4] = b"SPM1";
const VERSION: u32 = 1;
/// Refuse counts that could not fit in a phone capture rather than allocating for them.
const MAX_ELEMENTS: u32 = 50_000_000;

#[derive(Debug, thiserror::Error, PartialEq, Eq)]
pub enum MeshError {
    #[error("not an SPM1 mesh file")]
    BadMagic,
    #[error("unsupported mesh version {0}")]
    UnsupportedVersion(u32),
    #[error("mesh file ends early (needed {needed} bytes at offset {offset})")]
    Truncated { offset: usize, needed: usize },
    #[error("mesh part {part} has an implausible {what} count {count}")]
    BadCount { part: usize, what: &'static str, count: u32 },
    #[error("mesh part {part} face {face} uses vertex {index} of {vertices}")]
    BadIndex { part: usize, face: usize, index: u32, vertices: usize },
}

/// ARKit's ARMeshClassification raw values.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum MeshClass {
    None,
    Wall,
    Floor,
    Ceiling,
    Table,
    Seat,
    Window,
    Door,
    Unrecognised(u8),
}

impl MeshClass {
    pub fn from_raw(raw: u8) -> Self {
        match raw {
            0 => Self::None,
            1 => Self::Wall,
            2 => Self::Floor,
            3 => Self::Ceiling,
            4 => Self::Table,
            5 => Self::Seat,
            6 => Self::Window,
            7 => Self::Door,
            other => Self::Unrecognised(other),
        }
    }

    pub fn raw(self) -> u8 {
        match self {
            Self::None => 0,
            Self::Wall => 1,
            Self::Floor => 2,
            Self::Ceiling => 3,
            Self::Table => 4,
            Self::Seat => 5,
            Self::Window => 6,
            Self::Door => 7,
            Self::Unrecognised(raw) => raw,
        }
    }
}

/// One ARMeshAnchor: vertices already moved into world space by the part's transform.
#[derive(Debug, Clone, PartialEq)]
pub struct MeshPart {
    pub id: [u8; 16],
    pub transform: [f32; 16],
    pub vertices: Vec<Vec3>,
    pub faces: Vec<[u32; 3]>,
    pub classes: Option<Vec<MeshClass>>,
}

impl MeshPart {
    pub fn class_of(&self, face: usize) -> MeshClass {
        self.classes.as_ref().and_then(|c| c.get(face).copied()).unwrap_or(MeshClass::None)
    }

    pub fn triangle(&self, face: usize) -> [Vec3; 3] {
        self.faces[face].map(|i| self.vertices[i as usize])
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ScanMesh {
    /// World height of the floor the RoomPlan capture was levelled to.
    pub floor_y: f64,
    pub parts: Vec<MeshPart>,
}

impl ScanMesh {
    pub fn from_bytes(bytes: &[u8]) -> Result<ScanMesh, MeshError> {
        let mut reader = Reader { bytes, offset: 0 };
        if reader.take(4)? != MAGIC {
            return Err(MeshError::BadMagic);
        }
        let version = reader.u32()?;
        if version != VERSION {
            return Err(MeshError::UnsupportedVersion(version));
        }
        let floor_y = f64::from(reader.f32()?);
        let part_count = reader.count(0, "part")?;
        let parts = (0..part_count).map(|i| read_part(&mut reader, i)).collect::<Result<_, _>>()?;
        Ok(ScanMesh { floor_y, parts })
    }

    /// The SPM1 encoding of this mesh, with vertices written back in each part's local frame.
    pub fn to_bytes(&self) -> Vec<u8> {
        let mut out = Vec::new();
        out.extend_from_slice(MAGIC);
        out.extend_from_slice(&VERSION.to_le_bytes());
        out.extend_from_slice(&(self.floor_y as f32).to_le_bytes());
        out.extend_from_slice(&(self.parts.len() as u32).to_le_bytes());
        self.parts.iter().for_each(|part| write_part(&mut out, part));
        out
    }

    pub fn face_count(&self) -> usize {
        self.parts.iter().map(|p| p.faces.len()).sum()
    }
}

fn read_part(reader: &mut Reader, part: usize) -> Result<MeshPart, MeshError> {
    let id: [u8; 16] = reader.take(16)?.try_into().expect("16 bytes");
    let mut transform = [0f32; 16];
    for value in &mut transform {
        *value = reader.f32()?;
    }
    let vertex_count = reader.count(part, "vertex")?;
    let face_count = reader.count(part, "face")?;
    let has_classes = reader.take(1)?[0] != 0;
    let vertices = (0..vertex_count).map(|_| reader.vec3().map(|v| apply(&transform, v))).collect::<Result<_, _>>()?;
    let faces: Vec<[u32; 3]> =
        (0..face_count).map(|_| Ok([reader.u32()?, reader.u32()?, reader.u32()?])).collect::<Result<_, MeshError>>()?;
    check_indices(part, &faces, vertex_count)?;
    let classes = if has_classes {
        Some(reader.take(face_count)?.iter().map(|&b| MeshClass::from_raw(b)).collect())
    } else {
        None
    };
    Ok(MeshPart { id, transform, vertices, faces, classes })
}

fn check_indices(part: usize, faces: &[[u32; 3]], vertices: usize) -> Result<(), MeshError> {
    let bad = faces
        .iter()
        .enumerate()
        .find_map(|(face, f)| f.iter().find(|&&i| i as usize >= vertices).map(|&index| (face, index)));
    match bad {
        Some((face, index)) => Err(MeshError::BadIndex { part, face, index, vertices }),
        None => Ok(()),
    }
}

fn write_part(out: &mut Vec<u8>, part: &MeshPart) {
    out.extend_from_slice(&part.id);
    part.transform.iter().for_each(|v| out.extend_from_slice(&v.to_le_bytes()));
    out.extend_from_slice(&(part.vertices.len() as u32).to_le_bytes());
    out.extend_from_slice(&(part.faces.len() as u32).to_le_bytes());
    out.push(u8::from(part.classes.is_some()));
    let inverse = rigid_inverse(&part.transform);
    for v in &part.vertices {
        let local = apply(&inverse, *v);
        [local.x, local.y, local.z].iter().for_each(|c| out.extend_from_slice(&(*c as f32).to_le_bytes()));
    }
    part.faces.iter().flatten().for_each(|i| out.extend_from_slice(&i.to_le_bytes()));
    if let Some(classes) = &part.classes {
        out.extend(classes.iter().map(|c| c.raw()));
    }
}

/// Column-major 4x4 times a point.
fn apply(m: &[f32; 16], v: Vec3) -> Vec3 {
    let at = |row: usize| {
        f64::from(m[row]) * v.x + f64::from(m[4 + row]) * v.y + f64::from(m[8 + row]) * v.z + f64::from(m[12 + row])
    };
    Vec3::new(at(0), at(1), at(2))
}

/// Inverse of a rotation-plus-translation transform (ARKit anchor transforms are rigid).
fn rigid_inverse(m: &[f32; 16]) -> [f32; 16] {
    let mut inverse = [0f32; 16];
    for row in 0..3 {
        for col in 0..3 {
            inverse[col * 4 + row] = m[row * 4 + col];
        }
    }
    for row in 0..3 {
        inverse[12 + row] = -(0..3).map(|k| inverse[k * 4 + row] * m[12 + k]).sum::<f32>();
    }
    inverse[15] = 1.0;
    inverse
}

struct Reader<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> Reader<'a> {
    fn take(&mut self, needed: usize) -> Result<&'a [u8], MeshError> {
        let end = self.offset.checked_add(needed).filter(|&end| end <= self.bytes.len());
        let end = end.ok_or(MeshError::Truncated { offset: self.offset, needed })?;
        let slice = &self.bytes[self.offset..end];
        self.offset = end;
        Ok(slice)
    }

    fn u32(&mut self) -> Result<u32, MeshError> {
        Ok(u32::from_le_bytes(self.take(4)?.try_into().expect("4 bytes")))
    }

    fn f32(&mut self) -> Result<f32, MeshError> {
        Ok(f32::from_le_bytes(self.take(4)?.try_into().expect("4 bytes")))
    }

    fn vec3(&mut self) -> Result<Vec3, MeshError> {
        Ok(Vec3::new(f64::from(self.f32()?), f64::from(self.f32()?), f64::from(self.f32()?)))
    }

    fn count(&mut self, part: usize, what: &'static str) -> Result<usize, MeshError> {
        let count = self.u32()?;
        if count > MAX_ELEMENTS {
            return Err(MeshError::BadCount { part, what, count });
        }
        Ok(count as usize)
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub const IDENTITY: [f32; 16] = [1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0];

    /// A flat square floor patch `size` metres wide centred on `centre`, split into two triangles.
    pub fn floor_patch(centre: Vec3, size: f64, class: MeshClass) -> MeshPart {
        let h = size / 2.0;
        let corners = [(-h, -h), (h, -h), (h, h), (-h, h)];
        MeshPart {
            id: [7; 16],
            transform: IDENTITY,
            vertices: corners.iter().map(|&(dx, dz)| Vec3::new(centre.x + dx, centre.y, centre.z + dz)).collect(),
            faces: vec![[0, 1, 2], [0, 2, 3]],
            classes: Some(vec![class; 2]),
        }
    }

    fn translated(x: f32, y: f32, z: f32) -> [f32; 16] {
        let mut m = IDENTITY;
        m[12] = x;
        m[13] = y;
        m[14] = z;
        m
    }

    #[test]
    fn round_trips_a_synthetic_file() {
        let mut part = floor_patch(Vec3::new(1.0, 0.0, 2.0), 1.0, MeshClass::Floor);
        part.transform = translated(0.5, -1.0, 0.0);
        let mesh = ScanMesh { floor_y: -1.25, parts: vec![part, floor_patch(Vec3::ZERO, 2.0, MeshClass::Table)] };
        let decoded = ScanMesh::from_bytes(&mesh.to_bytes()).unwrap();
        assert_eq!(decoded.floor_y, -1.25);
        assert_eq!(decoded.parts.len(), 2);
        assert_eq!(decoded.face_count(), 4);
        assert_eq!(decoded.parts[1].class_of(0), MeshClass::Table);
        let moved = decoded.parts[0].vertices[0];
        assert!((moved.x - 0.5).abs() < 1e-6 && (moved.z - 1.5).abs() < 1e-6, "{moved:?}");
    }

    #[test]
    fn applies_the_part_transform_to_local_vertices() {
        let mut bytes = Vec::new();
        bytes.extend_from_slice(b"SPM1");
        bytes.extend_from_slice(&1u32.to_le_bytes());
        bytes.extend_from_slice(&0.0f32.to_le_bytes());
        bytes.extend_from_slice(&1u32.to_le_bytes());
        bytes.extend_from_slice(&[0; 16]);
        translated(1.0, 2.0, 3.0).iter().for_each(|v| bytes.extend_from_slice(&v.to_le_bytes()));
        bytes.extend_from_slice(&3u32.to_le_bytes());
        bytes.extend_from_slice(&1u32.to_le_bytes());
        bytes.push(0);
        [0.0f32, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0].iter().for_each(|v| bytes.extend_from_slice(&v.to_le_bytes()));
        [0u32, 1, 2].iter().for_each(|v| bytes.extend_from_slice(&v.to_le_bytes()));
        let mesh = ScanMesh::from_bytes(&bytes).unwrap();
        assert_eq!(mesh.parts[0].vertices[1], Vec3::new(2.0, 2.0, 3.0));
        assert_eq!(mesh.parts[0].classes, None);
        assert_eq!(mesh.parts[0].class_of(0), MeshClass::None);
    }

    #[test]
    fn rejects_bad_headers_and_truncation() {
        assert_eq!(ScanMesh::from_bytes(b"PLY1xxxxxxxxxxxx"), Err(MeshError::BadMagic));
        let mut bytes =
            ScanMesh { floor_y: 0.0, parts: vec![floor_patch(Vec3::ZERO, 1.0, MeshClass::Floor)] }.to_bytes();
        bytes[4] = 2;
        assert_eq!(ScanMesh::from_bytes(&bytes), Err(MeshError::UnsupportedVersion(2)));
        bytes[4] = 1;
        bytes.truncate(bytes.len() - 1);
        assert!(matches!(ScanMesh::from_bytes(&bytes), Err(MeshError::Truncated { .. })));
    }

    #[test]
    fn rejects_out_of_range_indices() {
        let mut part = floor_patch(Vec3::ZERO, 1.0, MeshClass::Floor);
        part.faces[1] = [0, 2, 9];
        let bytes = ScanMesh { floor_y: 0.0, parts: vec![part] }.to_bytes();
        assert_eq!(ScanMesh::from_bytes(&bytes), Err(MeshError::BadIndex { part: 0, face: 1, index: 9, vertices: 4 }));
    }
}
