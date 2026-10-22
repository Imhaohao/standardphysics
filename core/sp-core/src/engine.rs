//! The engine: a scene, a catalog and rulepacks, with full and incremental evaluation.

use crate::analysis::{AnalysisOptions, StoreyAnalysis};
use crate::mesh::ScanMesh;
use crate::metrics::subject::{
    SITE_ID, Subject, SubjectRef, Tagging, enumerate_subjects, room_subjects, route_subjects, site_subject,
};
use crate::metrics::{Catalog, EvalContext, SubjectOutcome};
use crate::overrides::{apply_category_overrides, apply_to_room};
use crate::roomplan::detect_connections;
use crate::rules::{Evaluator, Finding, Report, Rule, RuleLoadError, RulePack, Status};
use crate::scene::{Room, Scene};
use crate::split_rooms::drop_split_room_duplicates;
use std::collections::{BTreeMap, HashMap};

#[derive(Debug, thiserror::Error)]
pub enum EngineError {
    #[error("metric catalog did not parse: {0}")]
    Catalog(serde_json::Error),
    #[error(transparent)]
    Rules(#[from] RuleLoadError),
}

pub struct Engine {
    catalog: Catalog,
    packs: Vec<RulePack>,
    tagging: Tagging,
    options: AnalysisOptions,
    scene: Scene,
    analyses: HashMap<i32, StoreyAnalysis>,
    /// Scan meshes by the id of the room they were captured with.
    meshes: HashMap<String, ScanMesh>,
    /// Findings per subject id, from the last evaluation that touched the subject.
    findings: BTreeMap<String, Vec<Finding>>,
    /// Storey of each subject in `findings` (the site is not tied to one).
    finding_storeys: HashMap<String, i32>,
}

impl Engine {
    pub fn new(catalog_json: &str, rulepack_jsons: &[&str]) -> Result<Engine, EngineError> {
        let catalog = Catalog::from_json(catalog_json).map_err(EngineError::Catalog)?;
        let packs = rulepack_jsons.iter().map(|json| RulePack::from_json(json)).collect::<Result<Vec<_>, _>>()?;
        let options =
            AnalysisOptions { destination_categories: catalog.destination_categories(), ..AnalysisOptions::default() };
        Ok(Engine {
            tagging: Tagging::from_catalog(&catalog),
            catalog,
            packs,
            options,
            scene: Scene::default(),
            analyses: HashMap::new(),
            meshes: HashMap::new(),
            findings: BTreeMap::new(),
            finding_storeys: HashMap::new(),
        })
    }

    pub fn catalog(&self) -> &Catalog {
        &self.catalog
    }

    pub fn rulepacks(&self) -> &[RulePack] {
        &self.packs
    }

    pub fn scene(&self) -> &Scene {
        &self.scene
    }

    pub fn options_mut(&mut self) -> &mut AnalysisOptions {
        &mut self.options
    }

    pub fn analysis(&self, storey: i32) -> Option<&StoreyAnalysis> {
        self.analyses.get(&storey)
    }

    /// Replace the scene; nothing is evaluated until [`Engine::evaluate_all`].
    pub fn set_scene(&mut self, mut scene: Scene) {
        apply_category_overrides(&mut scene, &|c| self.catalog.is_known_category(c));
        self.scene = scene;
        self.analyses.clear();
        self.findings.clear();
        self.finding_storeys.clear();
    }

    /// Analyse every storey and evaluate every rule on every applicable subject.
    pub fn evaluate_all(&mut self) -> Report {
        self.analyses = self.scene.storeys().into_iter().map(|s| (s, self.analyse(s))).collect();
        let subjects = enumerate_subjects(&self.scene, &self.analyses, &self.tagging);
        self.findings.clear();
        self.finding_storeys.clear();
        self.evaluate_subjects(&subjects);
        self.report()
    }

    /// Add or replace one room (live scanning) and re-evaluate only its storey and the site.
    /// Returns the findings of the re-evaluated subjects.
    pub fn update_room(&mut self, mut room: Room) -> Vec<Finding> {
        apply_to_room(&mut room, &self.scene.observations, &|c| self.catalog.is_known_category(c));
        let storey = room.storey;
        let previous_storey = self.scene.room(&room.id).map(|r| r.storey);
        self.scene.upsert_room(room);
        self.scene.connections = detect_connections(&self.scene.rooms);
        let mut storeys = vec![storey];
        storeys.extend(previous_storey.filter(|s| *s != storey));
        let mut subjects = Vec::new();
        for s in storeys {
            self.drop_storey_findings(s);
            self.analyses.insert(s, self.analyse(s));
            subjects.extend(self.storey_subjects(s));
        }
        self.evaluate_subjects(&subjects);
        let mut touched: Vec<Finding> =
            subjects.iter().flat_map(|s| self.findings.get(&s.id).cloned().unwrap_or_default()).collect();
        touched.extend(self.findings.get(SITE_ID).cloned().unwrap_or_default());
        touched
    }

    /// Attach the scan mesh captured with a room; it is used from the next evaluation or update.
    pub fn set_room_mesh(&mut self, room_id: &str, mesh: ScanMesh) {
        self.meshes.insert(room_id.to_string(), mesh);
    }

    fn analyse(&self, storey: i32) -> StoreyAnalysis {
        let on_storey = |id: &String| self.scene.room(id).is_some_and(|r| r.storey == storey);
        let meshes: Vec<&ScanMesh> = self.meshes.iter().filter(|(id, _)| on_storey(id)).map(|(_, m)| m).collect();
        StoreyAnalysis::build_with_meshes(&self.scene, storey, &self.options, &meshes)
    }

    fn storey_subjects(&self, storey: i32) -> Vec<Subject> {
        let rooms = (0..self.scene.rooms.len()).filter(|&i| self.scene.rooms[i].storey == storey);
        let mut subjects: Vec<Subject> = rooms.flat_map(|i| room_subjects(&self.scene, i, &self.tagging)).collect();
        if let Some(analysis) = self.analyses.get(&storey) {
            subjects.extend(route_subjects(&self.scene, analysis));
        }
        subjects
    }

    fn drop_storey_findings(&mut self, storey: i32) {
        let stale: Vec<String> =
            self.finding_storeys.iter().filter(|(_, s)| **s == storey).map(|(id, _)| id.clone()).collect();
        for id in stale {
            self.finding_storeys.remove(&id);
            self.findings.remove(&id);
        }
    }

    /// Evaluate the given subjects, then the site (whose counts read the subjects' outcomes).
    fn evaluate_subjects(&mut self, subjects: &[Subject]) {
        let site = site_subject();
        let rules = rule_index(&self.packs);
        let element_subjects = || subjects.iter().filter(|s| s.reference != SubjectRef::Site);
        self.finding_storeys.extend(element_subjects().map(|s| (s.id.clone(), s.storey)));
        let element_findings = {
            let ctx = EvalContext::new(&self.scene, &self.catalog, &self.analyses, &self.options);
            let evaluator = Evaluator::new(&ctx, &site);
            evaluate_each(&evaluator, &rules, element_subjects())
        };
        self.findings.extend(element_findings);
        let outcomes = self.outcomes();
        let ctx = EvalContext::new(&self.scene, &self.catalog, &self.analyses, &self.options).with_outcomes(&outcomes);
        let evaluator = Evaluator::new(&ctx, &site);
        let site_findings = evaluate_each(&evaluator, &rules, std::iter::once(&site));
        self.findings.extend(site_findings);
    }

    fn outcomes(&self) -> HashMap<String, SubjectOutcome> {
        self.findings
            .iter()
            .map(|(id, findings)| {
                let outcome = SubjectOutcome {
                    any_fail: findings.iter().any(|f| f.status == Status::Fail),
                    any_unresolved: findings.iter().any(|f| f.status == Status::NeedsInfo),
                    any_pass: findings.iter().any(|f| f.status == Status::Pass),
                };
                (id.clone(), outcome)
            })
            .collect()
    }

    /// The current findings of every subject, per jurisdiction and governing.
    pub fn report(&self) -> Report {
        let rules: HashMap<String, &Rule> =
            self.packs.iter().flat_map(|p| &p.rules).map(|r| (r.id.clone(), r)).collect();
        Report::build(self.findings(), &rules)
    }

    pub fn findings(&self) -> Vec<Finding> {
        drop_split_room_duplicates(self.findings.values().flatten().cloned().collect(), &self.scene)
    }
}

fn rule_index(packs: &[RulePack]) -> HashMap<&str, Vec<&Rule>> {
    let mut index: HashMap<&str, Vec<&Rule>> = HashMap::new();
    for rule in packs.iter().flat_map(|p| &p.rules) {
        for tag in &rule.applies_to {
            index.entry(tag.as_str()).or_default().push(rule);
        }
    }
    index
}

fn evaluate_each<'s>(
    evaluator: &Evaluator,
    rules: &HashMap<&str, Vec<&Rule>>,
    subjects: impl Iterator<Item = &'s Subject>,
) -> Vec<(String, Vec<Finding>)> {
    subjects.map(|subject| (subject.id.clone(), evaluate_subject(evaluator, rules, subject))).collect()
}

/// Every rule whose `applies_to` names one of the subject's tags, each rule once.
fn evaluate_subject(evaluator: &Evaluator, rules: &HashMap<&str, Vec<&Rule>>, subject: &Subject) -> Vec<Finding> {
    let mut seen = std::collections::HashSet::new();
    let applicable =
        subject.tags.iter().filter_map(|t| rules.get(t.as_str())).flatten().filter(|r| seen.insert(r.id.as_str()));
    applicable.map(|rule| evaluator.evaluate(rule, subject)).collect()
}
