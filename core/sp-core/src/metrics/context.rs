use super::subject::{Subject, SubjectRef};
use super::Catalog;
use crate::analysis::{AnalysisOptions, RouteRecord, StoreyAnalysis};
use crate::scene::{Object, Observation, Opening, Room, Scene, Wall};
use std::collections::{BTreeSet, HashMap};

/// Outcome of the rules already evaluated for a subject, for site metrics that count compliant
/// elements (e.g. accessible entrances).
#[derive(Debug, Clone, Copy, Default, PartialEq, Eq)]
pub struct SubjectOutcome {
    pub any_fail: bool,
    pub any_unresolved: bool,
    pub any_pass: bool,
}

/// Everything an extractor can read.
pub struct EvalContext<'a> {
    pub scene: &'a Scene,
    pub catalog: &'a Catalog,
    pub analyses: &'a HashMap<i32, StoreyAnalysis>,
    pub options: &'a AnalysisOptions,
    observations: HashMap<(&'a str, &'a str), &'a Observation>,
    pub outcomes: Option<&'a HashMap<String, SubjectOutcome>>,
    /// Categories that need a clear floor space (from the catalog).
    pub clear_floor_categories: BTreeSet<String>,
}

impl<'a> EvalContext<'a> {
    pub fn new(scene: &'a Scene, catalog: &'a Catalog, analyses: &'a HashMap<i32, StoreyAnalysis>, options: &'a AnalysisOptions) -> Self {
        let observations = latest_observations(scene);
        let clear_floor_categories = catalog.categories_for_element("clear_floor_space");
        Self { scene, catalog, analyses, options, observations, outcomes: None, clear_floor_categories }
    }

    pub fn with_outcomes(mut self, outcomes: &'a HashMap<String, SubjectOutcome>) -> Self {
        self.outcomes = Some(outcomes);
        self
    }

    pub fn observation(&self, subject_id: &str, metric: &str) -> Option<&'a Observation> {
        self.observations.get(&(subject_id, metric)).copied()
    }

    pub fn room(&self, subject: &Subject) -> Option<&'a Room> {
        let index = match subject.reference {
            SubjectRef::Room { room } | SubjectRef::Floor { room } => room,
            SubjectRef::Wall { room, .. } | SubjectRef::Opening { room, .. } | SubjectRef::Object { room, .. } => room,
            SubjectRef::Site | SubjectRef::Route { .. } => return subject.room_id.as_deref().and_then(|id| self.scene.room(id)),
        };
        self.scene.rooms.get(index)
    }

    pub fn object(&self, subject: &Subject) -> Option<&'a Object> {
        match subject.reference {
            SubjectRef::Object { room, object } => self.scene.rooms.get(room)?.objects.get(object),
            _ => None,
        }
    }

    pub fn opening(&self, subject: &Subject) -> Option<&'a Opening> {
        match subject.reference {
            SubjectRef::Opening { room, opening } => self.scene.rooms.get(room)?.openings.get(opening),
            _ => None,
        }
    }

    pub fn wall(&self, subject: &Subject) -> Option<&'a Wall> {
        match subject.reference {
            SubjectRef::Wall { room, wall } => self.scene.rooms.get(room)?.walls.get(wall),
            _ => None,
        }
    }

    pub fn route(&self, subject: &Subject) -> Option<(&'a StoreyAnalysis, &'a RouteRecord)> {
        match subject.reference {
            SubjectRef::Route { storey, route } => {
                let analysis = self.analyses.get(&storey)?;
                Some((analysis, analysis.routes.get(route)?))
            }
            _ => None,
        }
    }

    pub fn analysis(&self, storey: i32) -> Option<&'a StoreyAnalysis> {
        self.analyses.get(&storey)
    }

    pub fn objects(&self) -> impl Iterator<Item = (&'a Room, &'a Object)> + 'a {
        self.scene.rooms.iter().flat_map(|r| r.objects.iter().map(move |o| (r, o)))
    }

    pub fn objects_of(&self, categories: &'a [&'a str]) -> impl Iterator<Item = (&'a Room, &'a Object)> + 'a {
        self.objects().filter(move |(_, o)| categories.contains(&o.category.as_str()))
    }

    pub fn outcome(&self, subject_id: &str) -> Option<SubjectOutcome> {
        self.outcomes.and_then(|o| o.get(subject_id).copied())
    }
}

/// The last observation for each (subject, metric) wins, so a later correction replaces an earlier one.
fn latest_observations(scene: &Scene) -> HashMap<(&str, &str), &Observation> {
    scene.observations.iter().map(|o| ((o.subject_id.as_str(), o.metric.as_str()), o)).collect()
}
