use crate::geometry::{OrientedBox2, Vec2, yaw_axes};
use crate::grid::{ClearanceField, OccupancyGrid, area_is_free};
use crate::units::inches;

/// Diameter of the largest circle of free floor centred inside the room (304.3.1).
pub fn largest_turning_circle(grid: &OccupancyGrid, clearance: &ClearanceField, room: u16) -> f64 {
    let cells = (0..grid.spec.len()).filter(|&i| grid.room[i] == room && grid.is_free(i));
    2.0 * cells.map(|i| clearance.at(i)).fold(0.0, f64::max)
}

/// True when a T-shaped turning space (304.3.2: 60 in square, 36 in arms and base) fits on free
/// floor in the room, tried at the four orientations aligned with `axis_yaw`.
pub fn t_turn_fits(grid: &OccupancyGrid, clearance: &ClearanceField, room: u16, axis_yaw: f64) -> bool {
    let stride = ((0.1 / grid.spec.cell).round() as usize).max(1);
    let half_arm = inches(18.0);
    let candidates = (0..grid.spec.len())
        .step_by(stride)
        .filter(|&i| grid.room[i] == room && clearance.at(i) >= half_arm - grid.spec.cell);
    candidates.into_iter().any(|i| (0..4).any(|k| t_shape_is_free(grid, grid.spec.center(i), axis_yaw + k as f64 * std::f64::consts::FRAC_PI_2)))
}

/// T centred in its 60 in square at `centre`: base towards local -Z of `yaw`, bar across +Z.
fn t_shape_is_free(grid: &OccupancyGrid, centre: Vec2, yaw: f64) -> bool {
    let (_, ahead) = yaw_axes(yaw);
    let (stem_len, bar_depth, square) = (inches(24.0), inches(36.0), inches(60.0));
    let stem_root = centre - ahead * (square / 2.0);
    let stem_centre = stem_root + ahead * (stem_len / 2.0);
    let bar_centre = stem_root + ahead * (stem_len + bar_depth / 2.0);
    let stem = OrientedBox2::new(stem_centre, inches(36.0), stem_len, yaw);
    let bar = OrientedBox2::new(bar_centre, square, bar_depth, yaw);
    area_is_free(grid, &stem) && area_is_free(grid, &bar)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::Polygon2;
    use crate::grid::GridOptions;
    use crate::scene::{Room, RoomKind, Wall};

    fn open_room(width: f64, depth: f64) -> Room {
        let c = [Vec2::new(0.0, 0.0), Vec2::new(width, 0.0), Vec2::new(width, depth), Vec2::new(0.0, depth)];
        Room {
            id: "r".into(),
            name: "r".into(),
            kind: RoomKind::Restroom,
            storey: 0,
            floor: Polygon2::new(c.to_vec()),
            ceiling_height: 2.5,
            walls: (0..4).map(|i| Wall { id: format!("w{i}"), start: c[i], end: c[(i + 1) % 4], height: 2.5, thickness: 0.0 }).collect(),
            openings: vec![],
            objects: vec![],
        }
    }

    fn analyse(room: &Room) -> (OccupancyGrid, ClearanceField) {
        let grid = OccupancyGrid::build(&[room], GridOptions::default());
        let clearance = ClearanceField::compute(grid.spec, |i| !grid.is_free(i));
        (grid, clearance)
    }

    #[test]
    fn sixty_inch_circle_fits_in_a_62_inch_room() {
        let room = open_room(inches(62.0), inches(62.0));
        let (grid, clearance) = analyse(&room);
        let diameter = largest_turning_circle(&grid, &clearance, 0);
        assert!(diameter >= inches(60.0), "{}", diameter / 0.0254);
    }

    #[test]
    fn sixty_inch_circle_does_not_fit_in_a_56_inch_room() {
        let room = open_room(inches(56.0), inches(80.0));
        let (grid, clearance) = analyse(&room);
        let diameter = largest_turning_circle(&grid, &clearance, 0);
        assert!(diameter < inches(60.0));
        assert!((diameter - inches(56.0)).abs() < 0.06, "{}", diameter / 0.0254);
    }

    #[test]
    fn t_turn_fits_in_62_inch_square_but_not_in_50() {
        let (grid, clearance) = analyse(&open_room(inches(62.0), inches(62.0)));
        assert!(t_turn_fits(&grid, &clearance, 0, 0.0));
        let (grid, clearance) = analyse(&open_room(inches(50.0), inches(90.0)));
        assert!(!t_turn_fits(&grid, &clearance, 0, 0.0));
    }
}
