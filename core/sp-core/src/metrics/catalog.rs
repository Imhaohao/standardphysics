//! `rules/metrics.json`: every metric a rule may use, its unit, element and evidence kind.

use crate::units::Unit;
use serde::Deserialize;
use std::collections::{BTreeSet, HashMap};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Evidence {
    Measured,
    Photo,
    Owner,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ValueType {
    Number,
    Integer,
    Boolean,
    Enum,
    #[serde(other)]
    Other,
}

#[derive(Debug, Clone, Deserialize)]
pub struct MetricDef {
    pub id: String,
    #[serde(rename = "unit")]
    pub raw_unit: String,
    pub value_type: ValueType,
    pub element: String,
    #[serde(default)]
    pub applies_to: Vec<String>,
    pub evidence: Evidence,
    #[serde(default)]
    pub fallback_evidence: Vec<Evidence>,
    #[serde(default)]
    pub derivation: String,
    #[serde(default)]
    pub enum_values: Vec<String>,
}

impl MetricDef {
    pub fn unit(&self) -> Unit {
        match self.value_type {
            ValueType::Boolean => Unit::Boolean,
            ValueType::Enum => Unit::Text,
            _ => Unit::parse(&self.raw_unit),
        }
    }

    /// True when the metric can only come from a photo label or an owner answer.
    pub fn needs_observation(&self) -> bool {
        self.evidence != Evidence::Measured
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct CategoryDef {
    pub id: String,
    #[serde(default)]
    pub origin: Option<String>,
    #[serde(default)]
    pub roomplan_class: Option<String>,
    #[serde(default)]
    pub canonical: Option<String>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ElementDef {
    pub id: String,
}

#[derive(Debug, Clone, Deserialize)]
struct RawCatalog {
    #[serde(default)]
    version: String,
    #[serde(default)]
    elements: Vec<ElementDef>,
    #[serde(default)]
    object_categories: Vec<CategoryDef>,
    metrics: Vec<MetricDef>,
}

#[derive(Debug, Clone)]
pub struct Catalog {
    pub version: String,
    pub elements: Vec<ElementDef>,
    pub object_categories: Vec<CategoryDef>,
    pub metrics: Vec<MetricDef>,
    by_id: HashMap<String, usize>,
}

impl Catalog {
    pub fn from_json(json: &str) -> serde_json::Result<Catalog> {
        let raw: RawCatalog = serde_json::from_str(json)?;
        let by_id = raw.metrics.iter().enumerate().map(|(i, m)| (m.id.clone(), i)).collect();
        Ok(Catalog {
            version: raw.version,
            elements: raw.elements,
            object_categories: raw.object_categories,
            metrics: raw.metrics,
            by_id,
        })
    }

    pub fn metric(&self, id: &str) -> Option<&MetricDef> {
        self.by_id.get(id).map(|&i| &self.metrics[i])
    }

    pub fn canonical_category(&self, category: &str) -> Option<&str> {
        self.object_categories.iter().find(|c| c.id == category).and_then(|c| c.canonical.as_deref())
    }

    pub fn is_known_category(&self, category: &str) -> bool {
        self.object_categories.iter().any(|c| c.id == category)
    }

    /// Object categories listed by metrics measured on `element` (e.g. every category that has a
    /// clear floor space or an operable part).
    pub fn categories_for_element(&self, element: &str) -> BTreeSet<String> {
        self.metrics
            .iter()
            .filter(|m| m.element == element)
            .flat_map(|m| m.applies_to.iter())
            .filter(|c| self.is_known_category(c))
            .cloned()
            .collect()
    }

    /// Categories an accessible route must reach: those with a clear floor space or operable part,
    /// plus the elements `route.connects_entrance` is asked of.
    pub fn destination_categories(&self) -> BTreeSet<String> {
        let mut set = self.categories_for_element("clear_floor_space");
        set.extend(self.categories_for_element("operable_part"));
        if let Some(metric) = self.metric("route.connects_entrance") {
            set.extend(metric.applies_to.iter().filter(|c| self.is_known_category(c)).cloned());
        }
        set
    }
}

#[cfg(test)]
pub(crate) mod tests {
    use super::*;

    pub fn repo_catalog() -> Option<Catalog> {
        let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../rules/metrics.json");
        std::fs::read_to_string(path).ok().map(|json| Catalog::from_json(&json).expect("rules/metrics.json parses"))
    }

    #[test]
    fn parses_repo_catalog() {
        let Some(catalog) = repo_catalog() else {
            eprintln!("rules/metrics.json not present yet; skipping");
            return;
        };
        assert!(catalog.metrics.len() > 100);
        assert_eq!(catalog.canonical_category("toilet"), Some("water_closet"));
        assert!(catalog.destination_categories().contains("lavatory"));
        let width = catalog.metric("route.min_clear_width").unwrap();
        assert_eq!(width.unit(), Unit::Inch);
    }
}
