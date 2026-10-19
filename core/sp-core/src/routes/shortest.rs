use crate::grid::{CellIndex, CellState, OccupancyGrid};
use std::cmp::Ordering;
use std::collections::BinaryHeap;

const UNREACHED: u32 = u32::MAX;

/// Shortest walking paths (anyone, stairs allowed) from a set of sources: the general circulation
/// path an accessible route is compared against (402.2, 206.3).
#[derive(Debug, Clone)]
pub struct ShortestTree {
    distance: Vec<f32>,
    parent: Vec<u32>,
    cell: f64,
}

#[derive(PartialEq)]
struct Frontier(f32, CellIndex);

impl Eq for Frontier {}

impl Ord for Frontier {
    fn cmp(&self, other: &Self) -> Ordering {
        other.0.total_cmp(&self.0).then_with(|| self.1.cmp(&other.1))
    }
}

impl PartialOrd for Frontier {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

pub fn is_walkable(grid: &OccupancyGrid, index: CellIndex) -> bool {
    matches!(grid.state(index), CellState::Free | CellState::Stairs)
}

impl ShortestTree {
    pub fn grow(grid: &OccupancyGrid, sources: &[CellIndex]) -> Self {
        let n = grid.spec.len();
        let mut tree = Self { distance: vec![f32::INFINITY; n], parent: vec![UNREACHED; n], cell: grid.spec.cell };
        let mut heap = BinaryHeap::new();
        for &source in sources.iter().filter(|&&s| is_walkable(grid, s)) {
            tree.distance[source] = 0.0;
            tree.parent[source] = source as u32;
            heap.push(Frontier(0.0, source));
        }
        while let Some(Frontier(distance, cell)) = heap.pop() {
            if distance <= tree.distance[cell] {
                tree.relax(grid, &mut heap, cell);
            }
        }
        tree
    }

    fn relax(&mut self, grid: &OccupancyGrid, heap: &mut BinaryHeap<Frontier>, cell: CellIndex) {
        for (next, step) in grid.spec.neighbours(cell) {
            let candidate = self.distance[cell] + step as f32;
            if is_walkable(grid, next) && candidate < self.distance[next] {
                self.distance[next] = candidate;
                self.parent[next] = cell as u32;
                heap.push(Frontier(candidate, next));
            }
        }
    }

    /// Walking distance in metres, or `None` when unreachable.
    pub fn distance_to(&self, cell: CellIndex) -> Option<f64> {
        let d = self.distance[cell];
        d.is_finite().then(|| f64::from(d) * self.cell)
    }

    pub fn path_to(&self, cell: CellIndex) -> Vec<CellIndex> {
        let mut path = Vec::new();
        if self.parent[cell] == UNREACHED {
            return path;
        }
        let mut at = cell;
        while self.parent[at] as usize != at {
            path.push(at);
            at = self.parent[at] as usize;
        }
        path.push(at);
        path.reverse();
        path
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::Vec2;
    use crate::grid::{GridOptions, occupancy::tests::box_room};

    #[test]
    fn walking_distance_across_an_empty_room() {
        let mut room = box_room();
        room.objects.clear();
        let grid = OccupancyGrid::build(&[&room], GridOptions::default());
        let start = grid.spec.locate(Vec2::new(0.5, 1.5)).unwrap();
        let end = grid.spec.locate(Vec2::new(3.5, 1.5)).unwrap();
        let tree = ShortestTree::grow(&grid, &[start]);
        assert!((tree.distance_to(end).unwrap() - 3.0).abs() < 0.03);
        assert_eq!(*tree.path_to(end).first().unwrap(), start);
    }
}
