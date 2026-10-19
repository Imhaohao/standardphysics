use super::RouteField;
use crate::grid::{CellIndex, GridSpec};
use std::collections::VecDeque;

const UNREACHED: u32 = u32::MAX;

/// Single-source widest-path tree: for every cell, the largest bottleneck (minimum field value)
/// over all paths from the sources, and the parent on one such path. Within equal bottlenecks the
/// FIFO bucket order prefers fewer steps.
#[derive(Debug, Clone)]
pub struct WidestTree {
    best: Vec<u16>,
    parent: Vec<u32>,
}

impl WidestTree {
    /// Bucket-queue search, O(cells + distinct field values).
    pub fn grow(spec: &GridSpec, field: &RouteField, sources: &[CellIndex]) -> Self {
        let mut tree = Self { best: vec![0; field.len()], parent: vec![UNREACHED; field.len()] };
        let mut queue = BucketQueue::default();
        for &source in sources.iter().filter(|&&s| field.is_passable(s)) {
            tree.best[source] = field.value(source);
            tree.parent[source] = source as u32;
            queue.push(field.value(source), source);
        }
        while let Some((key, cell)) = queue.pop() {
            if key == tree.best[cell] {
                tree.relax_neighbours(spec, field, &mut queue, cell);
            }
        }
        tree
    }

    fn relax_neighbours(&mut self, spec: &GridSpec, field: &RouteField, queue: &mut BucketQueue, cell: CellIndex) {
        let width = self.best[cell];
        for (next, _) in spec.neighbours(cell) {
            let candidate = width.min(field.value(next));
            if candidate > self.best[next] {
                self.best[next] = candidate;
                self.parent[next] = cell as u32;
                queue.push(candidate, next);
            }
        }
    }

    /// Bottleneck field value (mm, or [`super::EXEMPT`]) of the widest path to `cell`; 0 when unreachable.
    pub fn bottleneck(&self, cell: CellIndex) -> u16 {
        self.best[cell]
    }

    pub fn is_reached(&self, cell: CellIndex) -> bool {
        self.parent[cell] != UNREACHED
    }

    /// Cells from the source to `cell`, inclusive.
    pub fn path_to(&self, cell: CellIndex) -> Vec<CellIndex> {
        let mut path = Vec::new();
        if !self.is_reached(cell) {
            return path;
        }
        let mut at = cell;
        loop {
            path.push(at);
            let parent = self.parent[at] as usize;
            if parent == at {
                break;
            }
            at = parent;
        }
        path.reverse();
        path
    }
}

/// Max-priority bucket queue keyed by u16, FIFO within a bucket. Keys pushed never exceed the
/// last popped key, so the cursor only moves down.
#[derive(Default)]
struct BucketQueue {
    buckets: Vec<VecDeque<CellIndex>>,
    cursor: usize,
    len: usize,
}

impl BucketQueue {
    fn push(&mut self, key: u16, cell: CellIndex) {
        let key = usize::from(key);
        if key >= self.buckets.len() {
            self.buckets.resize_with(key + 1, VecDeque::new);
        }
        self.buckets[key].push_back(cell);
        self.cursor = self.cursor.max(key);
        self.len += 1;
    }

    fn pop(&mut self) -> Option<(u16, CellIndex)> {
        if self.len == 0 {
            return None;
        }
        while self.buckets[self.cursor].is_empty() {
            self.cursor -= 1;
        }
        self.len -= 1;
        let cell = self.buckets[self.cursor].pop_front()?;
        Some((self.cursor as u16, cell))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::geometry::Vec2;
    use crate::grid::{ClearanceField, GridOptions, OccupancyGrid};
    use proptest::prelude::*;

    fn field_from(values: Vec<u16>) -> RouteField {
        RouteField::from_values(values)
    }

    #[test]
    fn prefers_the_wide_detour_over_the_narrow_shortcut() {
        // 5x3: middle row narrow (1), top row wide (9); bottom blocked.
        let spec = GridSpec { origin: Vec2::ZERO, cell: 1.0, nx: 5, ny: 3 };
        let field = field_from(vec![9, 1, 1, 1, 9, 9, 9, 9, 9, 9, 0, 0, 0, 0, 0]);
        let tree = WidestTree::grow(&spec, &field, &[0]);
        assert_eq!(tree.bottleneck(4), 9);
        assert!(tree.path_to(4).iter().all(|&c| field.value(c) == 9));
    }

    #[test]
    fn unreachable_cells_have_no_path() {
        let spec = GridSpec { origin: Vec2::ZERO, cell: 1.0, nx: 3, ny: 1 };
        let tree = WidestTree::grow(&spec, &field_from(vec![5, 0, 5]), &[0]);
        assert!(!tree.is_reached(2));
        assert!(tree.path_to(2).is_empty());
    }

    proptest! {
        #[test]
        fn bottleneck_equals_min_along_returned_path(values in proptest::collection::vec(0u16..20, 64), source in 0usize..64) {
            let spec = GridSpec { origin: Vec2::ZERO, cell: 1.0, nx: 8, ny: 8 };
            let field = field_from(values.clone());
            let tree = WidestTree::grow(&spec, &field, &[source]);
            for cell in 0..64 {
                let path = tree.path_to(cell);
                if path.is_empty() { continue; }
                let min = path.iter().map(|&c| values[c]).min().unwrap();
                prop_assert_eq!(min, tree.bottleneck(cell));
                prop_assert_eq!(path[0], source);
            }
        }

        #[test]
        fn bottleneck_is_optimal_against_threshold_flood(values in proptest::collection::vec(0u16..6, 49), source in 0usize..49) {
            let spec = GridSpec { origin: Vec2::ZERO, cell: 1.0, nx: 7, ny: 7 };
            let field = field_from(values.clone());
            let tree = WidestTree::grow(&spec, &field, &[source]);
            for threshold in 1u16..6 {
                let reach = flood(&spec, &values, source, threshold);
                for cell in 0..49 {
                    prop_assert_eq!(reach[cell], tree.bottleneck(cell) >= threshold);
                }
            }
        }
    }

    fn flood(spec: &GridSpec, values: &[u16], source: usize, threshold: u16) -> Vec<bool> {
        let mut seen = vec![false; values.len()];
        if values[source] < threshold { return seen; }
        let mut stack = vec![source];
        seen[source] = true;
        while let Some(cell) = stack.pop() {
            for (next, _) in spec.neighbours(cell) {
                if !seen[next] && values[next] >= threshold {
                    seen[next] = true;
                    stack.push(next);
                }
            }
        }
        seen
    }

    #[test]
    fn corridor_width_from_real_grid() {
        let grid = OccupancyGrid::build(&[], GridOptions::default());
        let clearance = ClearanceField::compute(grid.spec, |i| !grid.is_free(i));
        let field = RouteField::build(&grid, &clearance, &[]);
        assert!(!field.is_passable(0));
    }
}
