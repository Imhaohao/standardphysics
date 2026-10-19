use super::{PASSING_WIDTH, ROUTE_MIN_CLEAR_WIDTH, RouteField, WidestTree};
use crate::geometry::Vec2;
use crate::grid::{CellIndex, ClearanceField};

/// Where a route narrows below 36 in.
#[derive(Debug, Clone, PartialEq)]
pub struct Pinch {
    pub location: Vec2,
    pub clear_width: f64,
    /// Length of the narrow stretch around the pinch, metres.
    pub run_length: f64,
}

/// A 180-degree turn around an element (403.5.2).
#[derive(Debug, Clone, PartialEq)]
pub struct Turn180 {
    pub apex: Vec2,
    pub approach_width: f64,
    pub turn_width: f64,
    pub leaving_width: f64,
    pub element_width: f64,
}

/// One accessible-route leg: the widest path from an entrance to a destination.
#[derive(Debug, Clone, PartialEq)]
pub struct RouteLeg {
    pub points: Vec<Vec2>,
    /// Clear width at each point; `None` inside a door throat (judged by door rules).
    pub widths: Vec<Option<f64>>,
    /// Distance along the leg at each point, metres.
    pub distances: Vec<f64>,
    pub length: f64,
    pub min_clear_width: Option<f64>,
    pub pinches: Vec<Pinch>,
    /// (start, end) distances along the leg where the width is below 36 in.
    pub reduced_width_runs: Vec<(f64, f64)>,
    pub max_distance_between_passing_spaces: f64,
    pub turn: Option<Turn180>,
}

pub fn trace_leg(tree: &WidestTree, field: &RouteField, clearance: &ClearanceField, target: CellIndex) -> Option<RouteLeg> {
    let cells = tree.path_to(target);
    if cells.is_empty() {
        return None;
    }
    let spec = &clearance.spec;
    let points: Vec<Vec2> = cells.iter().map(|&c| spec.center(c)).collect();
    let widths: Vec<Option<f64>> =
        cells.iter().map(|&c| (!field.is_exempt(c)).then(|| clearance.clear_width_at(c))).collect();
    let distances = cumulative_distances(&points);
    let reduced_width_runs = runs_where(&widths, &distances, |w| w < ROUTE_MIN_CLEAR_WIDTH - 1e-9);
    Some(RouteLeg {
        length: *distances.last().unwrap_or(&0.0),
        min_clear_width: widths.iter().flatten().copied().reduce(f64::min),
        pinches: pinches(&points, &widths, &distances, &reduced_width_runs),
        max_distance_between_passing_spaces: longest_without_passing_space(&widths, &distances),
        turn: find_turn(&points, &widths, &distances),
        reduced_width_runs,
        points,
        widths,
        distances,
    })
}

fn cumulative_distances(points: &[Vec2]) -> Vec<f64> {
    let mut total = 0.0;
    let mut out = Vec::with_capacity(points.len());
    for (i, p) in points.iter().enumerate() {
        if i > 0 {
            total += p.distance(points[i - 1]);
        }
        out.push(total);
    }
    out
}

/// Contiguous stretches where `narrow(width)` holds; exempt points end a stretch.
fn runs_where(widths: &[Option<f64>], distances: &[f64], narrow: impl Fn(f64) -> bool) -> Vec<(f64, f64)> {
    let mut runs = Vec::new();
    let mut start: Option<usize> = None;
    for (i, width) in widths.iter().enumerate() {
        let is_narrow = width.is_some_and(&narrow);
        match (is_narrow, start) {
            (true, None) => start = Some(i),
            (false, Some(s)) => {
                runs.push((distances[s], distances[i - 1]));
                start = None;
            }
            _ => {}
        }
    }
    if let Some(s) = start {
        runs.push((distances[s], *distances.last().unwrap_or(&0.0)));
    }
    runs
}

fn pinches(points: &[Vec2], widths: &[Option<f64>], distances: &[f64], runs: &[(f64, f64)]) -> Vec<Pinch> {
    runs.iter()
        .filter_map(|&(start, end)| {
            let within = (0..points.len()).filter(|&i| distances[i] >= start && distances[i] <= end);
            let narrowest = within.filter_map(|i| widths[i].map(|w| (i, w))).min_by(|a, b| a.1.total_cmp(&b.1))?;
            Some(Pinch { location: points[narrowest.0], clear_width: narrowest.1, run_length: end - start })
        })
        .collect()
}

/// Longest distance travelled at under 60 in wide without reaching a spot 60 in wide.
fn longest_without_passing_space(widths: &[Option<f64>], distances: &[f64]) -> f64 {
    let mut longest: f64 = 0.0;
    let mut since: Option<f64> = None;
    for (width, distance) in widths.iter().zip(distances) {
        let is_passing = width.is_some_and(|w| w >= PASSING_WIDTH - 1e-9);
        since = if is_passing { None } else { Some(since.unwrap_or(*distance)) };
        if let Some(start) = since {
            longest = longest.max(distance - start);
        }
    }
    longest
}

const TURN_LEG: f64 = 0.5;
const TURN_SPAN: f64 = 1.5;
const TURN_ANGLE_COS: f64 = -0.866;

/// The first place the route doubles back (heading change of 150 degrees or more within 1.5 m).
fn find_turn(points: &[Vec2], widths: &[Option<f64>], distances: &[f64]) -> Option<Turn180> {
    let at = |d: f64| index_at(distances, d);
    let total = *distances.last()?;
    let mut d_in = TURN_LEG;
    while d_in + TURN_LEG < total {
        let i = at(d_in);
        let heading_in = (points[i] - points[at(d_in - TURN_LEG)]).normalized();
        if let Some(j) = doubling_back(points, distances, i, heading_in) {
            return Some(describe_turn(points, widths, distances, i, j, heading_in));
        }
        d_in += 0.1;
    }
    None
}

fn doubling_back(points: &[Vec2], distances: &[f64], i: usize, heading_in: Vec2) -> Option<usize> {
    let total = *distances.last()?;
    let mut d_out = distances[i];
    while d_out <= distances[i] + TURN_SPAN && d_out + TURN_LEG <= total {
        let j = index_at(distances, d_out);
        let heading_out = (points[index_at(distances, d_out + TURN_LEG)] - points[j]).normalized();
        if heading_in.dot(heading_out) <= TURN_ANGLE_COS {
            return Some(j);
        }
        d_out += 0.1;
    }
    None
}

fn describe_turn(points: &[Vec2], widths: &[Option<f64>], distances: &[f64], i: usize, j: usize, heading_in: Vec2) -> Turn180 {
    let min_between = |a: f64, b: f64| {
        (0..points.len())
            .filter(|&k| distances[k] >= a && distances[k] <= b)
            .filter_map(|k| widths[k])
            .reduce(f64::min)
            .unwrap_or(f64::INFINITY)
    };
    let (di, dj) = (distances[i], distances[j]);
    let approach_width = min_between(di - 1.0, di);
    let leaving_width = min_between(dj, dj + 1.0);
    let before = points[index_at(distances, di - TURN_LEG)];
    let after = points[index_at(distances, dj + TURN_LEG)];
    let separation = (after - before).dot(heading_in.perpendicular()).abs();
    Turn180 {
        apex: points[(i + j) / 2],
        approach_width,
        turn_width: min_between(di, dj),
        leaving_width,
        element_width: (separation - (approach_width + leaving_width) / 2.0).max(0.0),
    }
}

fn index_at(distances: &[f64], d: f64) -> usize {
    distances.partition_point(|&x| x < d).min(distances.len().saturating_sub(1))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn straight(widths: &[f64]) -> (Vec<Vec2>, Vec<Option<f64>>, Vec<f64>) {
        let points: Vec<Vec2> = (0..widths.len()).map(|i| Vec2::new(i as f64 * 0.1, 0.0)).collect();
        let distances = cumulative_distances(&points);
        (points, widths.iter().map(|w| Some(*w)).collect(), distances)
    }

    #[test]
    fn narrow_runs_and_pinch() {
        let (points, widths, distances) = straight(&[1.2, 1.2, 0.8, 0.76, 0.8, 1.2, 1.2]);
        let runs = runs_where(&widths, &distances, |w| w < ROUTE_MIN_CLEAR_WIDTH);
        assert_eq!(runs.len(), 1);
        assert!((runs[0].1 - runs[0].0 - 0.2).abs() < 1e-9);
        let found = pinches(&points, &widths, &distances, &runs);
        assert_eq!(found[0].clear_width, 0.76);
        assert!((found[0].location.x - 0.3).abs() < 1e-9);
    }

    #[test]
    fn passing_space_resets_the_count() {
        let mut ws = vec![1.0; 30];
        ws[15] = 1.6;
        let (_, widths, distances) = straight(&ws);
        assert!((longest_without_passing_space(&widths, &distances) - 1.4).abs() < 1e-9);
    }

    #[test]
    fn u_turn_is_found() {
        let mut points: Vec<Vec2> = (0..=20).map(|i| Vec2::new(i as f64 * 0.1, 0.0)).collect();
        points.extend((1..=10).map(|i| Vec2::new(2.0, i as f64 * 0.1)));
        points.extend((1..=20).map(|i| Vec2::new(2.0 - i as f64 * 0.1, 1.0)));
        let distances = cumulative_distances(&points);
        let widths = vec![Some(0.6); points.len()];
        let turn = find_turn(&points, &widths, &distances).expect("turn");
        assert!((turn.element_width - 0.4).abs() < 0.05, "{turn:?}");
    }
}
