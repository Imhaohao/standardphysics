"""Validate the rulepack. Stdlib only; run with `python3 -I rules/tools/validate.py`.

Checks every rule file against schema/rule.schema.json and metrics.json against
schema/metrics.schema.json, then the cross-references a schema cannot express:
unique ids, metrics and units that exist, evidence that matches the test,
counterparts and stricter_than links, applies_to categories, coverage entries
and precedent rule references.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

RULES_DIR = Path(__file__).resolve().parent.parent
RULE_FILES = {"ADA2010": "ada2010.json", "CBC11B": "cbc11b.json"}
TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}
COVERAGE_STATUSES = {"covered", "not_applicable_to_scope", "deferred"}


class SchemaValidator:
    """A small JSON Schema (2020-12 subset) validator for the keywords our schemas use."""

    def __init__(self, schema: dict):
        self.root = schema

    def errors(self, value, schema=None, path="$") -> list[str]:
        schema = self.root if schema is None else schema
        if "$ref" in schema:
            return self.errors(value, self._resolve(schema["$ref"]), path)
        found: list[str] = []
        for keyword, check in self._checks():
            if keyword in schema:
                found.extend(check(value, schema, path))
        return found

    def _checks(self):
        return (
            ("type", self._check_type),
            ("enum", self._check_enum),
            ("const", self._check_const),
            ("pattern", self._check_pattern),
            ("minLength", self._check_min_length),
            ("minimum", self._check_minimum),
            ("maximum", self._check_maximum),
            ("required", self._check_required),
            ("properties", self._check_properties),
            ("additionalProperties", self._check_additional),
            ("items", self._check_items),
            ("minItems", self._check_min_items),
            ("oneOf", self._check_one_of),
            ("anyOf", self._check_any_of),
        )

    def _resolve(self, ref: str) -> dict:
        node = self.root
        for part in ref.lstrip("#/").split("/"):
            node = node[part]
        return node

    def _check_type(self, value, schema, path):
        types = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        return [] if any(TYPE_CHECKS[t](value) for t in types) else [f"{path}: expected {types}, got {type(value).__name__}"]

    def _check_enum(self, value, schema, path):
        return [] if value in schema["enum"] else [f"{path}: {value!r} not in {schema['enum']}"]

    def _check_const(self, value, schema, path):
        return [] if value == schema["const"] else [f"{path}: expected {schema['const']!r}"]

    def _check_pattern(self, value, schema, path):
        if isinstance(value, str) and not re.search(schema["pattern"], value):
            return [f"{path}: {value!r} does not match {schema['pattern']}"]
        return []

    def _check_min_length(self, value, schema, path):
        return [f"{path}: shorter than {schema['minLength']}"] if isinstance(value, str) and len(value) < schema["minLength"] else []

    def _check_minimum(self, value, schema, path):
        return [f"{path}: below {schema['minimum']}"] if TYPE_CHECKS["number"](value) and value < schema["minimum"] else []

    def _check_maximum(self, value, schema, path):
        return [f"{path}: above {schema['maximum']}"] if TYPE_CHECKS["number"](value) and value > schema["maximum"] else []

    def _check_required(self, value, schema, path):
        if not isinstance(value, dict):
            return []
        return [f"{path}: missing {key}" for key in schema["required"] if key not in value]

    def _check_properties(self, value, schema, path):
        if not isinstance(value, dict):
            return []
        found = []
        for key, sub in schema["properties"].items():
            if key in value:
                found.extend(self.errors(value[key], sub, f"{path}.{key}"))
        return found

    def _check_additional(self, value, schema, path):
        if not isinstance(value, dict):
            return []
        extra = schema["additionalProperties"]
        allowed = set(schema.get("properties", {}))
        unknown = [k for k in value if k not in allowed]
        if extra is False:
            return [f"{path}: unexpected property {k}" for k in unknown]
        if isinstance(extra, dict):
            return [e for k in unknown for e in self.errors(value[k], extra, f"{path}.{k}")]
        return []

    def _check_items(self, value, schema, path):
        if not isinstance(value, list):
            return []
        return [e for i, item in enumerate(value) for e in self.errors(item, schema["items"], f"{path}[{i}]")]

    def _check_min_items(self, value, schema, path):
        return [f"{path}: fewer than {schema['minItems']} items"] if isinstance(value, list) and len(value) < schema["minItems"] else []

    def _check_one_of(self, value, schema, path):
        matches = [option for option in schema["oneOf"] if not self.errors(value, option, path)]
        if len(matches) == 1:
            return []
        return [f"{path}: matches {len(matches)} of oneOf options (need exactly 1)"]

    def _check_any_of(self, value, schema, path):
        if any(not self.errors(value, option, path) for option in schema["anyOf"]):
            return []
        return [f"{path}: matches no anyOf option"]


def load(name: str):
    return json.loads((RULES_DIR / name).read_text())


def walk_tests(test: dict):
    kind = next(iter(test))
    if kind in ("all_of", "any_of"):
        for sub in test[kind]:
            yield from walk_tests(sub)
        return
    yield kind, test[kind]


def walk_conditions(condition):
    if not condition:
        return
    for key in ("all", "any"):
        if key in condition:
            for sub in condition[key]:
                yield from walk_conditions(sub)
            return
    if "not" in condition:
        yield from walk_conditions(condition["not"])
        return
    yield condition


def referenced_metric(value):
    return value["metric"] if isinstance(value, dict) and "metric" in value else None


class RulepackChecker:
    def __init__(self):
        self.problems: list[str] = []
        self.metrics_doc = load("metrics.json")
        self.metrics = {m["id"]: m for m in self.metrics_doc["metrics"]}
        self.categories = {c["id"] for c in self.metrics_doc["object_categories"]} | {e["id"] for e in self.metrics_doc["elements"]}
        self.packs = {jur: load(f) for jur, f in RULE_FILES.items()}
        self.rules = {}

    def fail(self, message: str):
        self.problems.append(message)

    def run(self) -> list[str]:
        self.check_schemas()
        self.check_metrics_catalog()
        self.index_rules()
        for rule in self.rules.values():
            self.check_rule(rule)
        self.check_coverage()
        self.check_precedents()
        return self.problems

    def check_schemas(self):
        metric_errors = SchemaValidator(load("schema/metrics.schema.json")).errors(self.metrics_doc)
        self.problems.extend(f"metrics.json {e}" for e in metric_errors)
        rule_schema = SchemaValidator(load("schema/rule.schema.json"))
        for jur, pack in self.packs.items():
            self.problems.extend(f"{RULE_FILES[jur]} {e}" for e in rule_schema.errors(pack))
            if pack.get("jurisdiction") != jur:
                self.fail(f"{RULE_FILES[jur]}: jurisdiction should be {jur}")

    def check_metrics_catalog(self):
        ids = [m["id"] for m in self.metrics_doc["metrics"]]
        for dup in {i for i in ids if ids.count(i) > 1}:
            self.fail(f"metrics.json: duplicate metric {dup}")
        for metric in self.metrics_doc["metrics"]:
            for category in metric["applies_to"] + [metric["element"]]:
                if category not in self.categories:
                    self.fail(f"metric {metric['id']}: unknown category or element {category}")
            if metric["value_type"] == "enum" and "enum_values" not in metric:
                self.fail(f"metric {metric['id']}: enum metric without enum_values")
        canon = {c["canonical"] for c in self.metrics_doc["object_categories"]}
        for c in canon - self.categories:
            self.fail(f"object category canonical {c} is not itself a category")

    def index_rules(self):
        for jur, pack in self.packs.items():
            for rule in pack["rules"]:
                if rule["id"] in self.rules:
                    self.fail(f"duplicate rule id {rule['id']}")
                if rule["jurisdiction"] != jur:
                    self.fail(f"{rule['id']}: in {RULE_FILES[jur]} but jurisdiction {rule['jurisdiction']}")
                self.rules[rule["id"]] = rule

    def check_rule(self, rule: dict):
        rid = rule["id"]
        expected_prefix = "ADA-" if rule["jurisdiction"] == "ADA2010" else "CBC-"
        if not rid.startswith(expected_prefix):
            self.fail(f"{rid}: id must start with {expected_prefix}")
        for category in rule["applies_to"]:
            if category not in self.categories:
                self.fail(f"{rid}: applies_to unknown category {category}")
        self.check_test(rid, rule["test"])
        self.check_condition(rid, rule["scoping"]["when"])
        self.check_subjects(rule)
        self.check_evidence(rule)
        self.check_links(rule)
        if rule["verified_by"] is not None and not rule["verified_at"]:
            self.fail(f"{rid}: verified_by set without verified_at")

    def test_metric_ids(self, rule: dict):
        for kind, body in walk_tests(rule["test"]):
            yield body["metric"]
            if kind in ("ratio", "table"):
                yield body["basis_metric"]
            other = referenced_metric(body.get("value"))
            if other:
                yield other

    def condition_metric_ids(self, rule: dict):
        for leaf in walk_conditions(rule["scoping"]["when"]):
            if "metric" in leaf:
                yield leaf["metric"]
            other = referenced_metric(leaf.get("value"))
            if other:
                yield other

    def subject_metric(self, metric_id: str):
        metric = self.metrics.get(metric_id)
        return None if metric is None or metric["element"] == "site" else metric

    def check_subjects(self, rule: dict):
        """Metrics are read off the rule's subject (site metrics are global).

        A test metric must be defined for every category in applies_to. A condition
        metric must be defined for at least one; for other subjects the leaf
        evaluates to false, which is how subject_category_in guards work.
        """
        applies = set(rule["applies_to"])
        for metric_id in set(self.test_metric_ids(rule)):
            metric = self.subject_metric(metric_id)
            if metric and applies - set(metric["applies_to"]):
                self.fail(f"{rule['id']}: test metric {metric_id} is not defined for {sorted(applies - set(metric['applies_to']))}")
        for metric_id in set(self.condition_metric_ids(rule)):
            metric = self.subject_metric(metric_id)
            if metric and not applies & set(metric["applies_to"]):
                self.fail(f"{rule['id']}: condition metric {metric_id} is defined for none of {sorted(applies)}")

    def check_metric(self, rid: str, metric: str | None):
        if metric is not None and metric not in self.metrics:
            self.fail(f"{rid}: unknown metric {metric}")
            return False
        return metric is not None

    def check_test(self, rid: str, test: dict):
        for kind, body in walk_tests(test):
            if not self.check_metric(rid, body["metric"]):
                continue
            metric = self.metrics[body["metric"]]
            if kind in ("ratio", "table"):
                self.check_metric(rid, body["basis_metric"])
            if kind == "measure":
                self.check_measure(rid, body, metric)
            if kind == "presence" and metric["value_type"] != "boolean":
                self.fail(f"{rid}: presence test on non-boolean metric {metric['id']}")

    def check_measure(self, rid: str, body: dict, metric: dict):
        if body["unit"] != metric["unit"]:
            self.fail(f"{rid}: unit {body['unit']} does not match {metric['id']} ({metric['unit']})")
        other = referenced_metric(body["value"])
        if other and self.check_metric(rid, other) and self.metrics[other]["unit"] != metric["unit"]:
            self.fail(f"{rid}: compares {metric['id']} with {other} in a different unit")
        if body["op"] == "between" and not (isinstance(body["value"], list) and len(body["value"]) == 2 and body["value"][0] <= body["value"][1]):
            self.fail(f"{rid}: between needs [lo, hi]")
        if metric["value_type"] == "enum" and isinstance(body["value"], str) and body["value"] not in metric.get("enum_values", []):
            self.fail(f"{rid}: {body['value']!r} is not a value of {metric['id']}")

    def check_condition(self, rid: str, condition):
        for leaf in walk_conditions(condition):
            if "metric" in leaf:
                self.check_metric(rid, leaf["metric"])
                self.check_metric(rid, referenced_metric(leaf["value"]))
                self.check_condition_enum(rid, leaf)
            for key in ("category_present",):
                if key in leaf and leaf[key] not in self.categories:
                    self.fail(f"{rid}: {key} unknown category {leaf[key]}")
            for category in leaf.get("subject_category_in", []):
                if category not in self.categories:
                    self.fail(f"{rid}: subject_category_in unknown category {category}")

    def check_condition_enum(self, rid: str, leaf: dict):
        metric = self.metrics.get(leaf["metric"])
        if not metric or metric["value_type"] != "enum":
            return
        values = leaf["value"] if isinstance(leaf["value"], list) else [leaf["value"]]
        for value in values:
            if isinstance(value, str) and value not in metric["enum_values"]:
                self.fail(f"{rid}: condition value {value!r} is not a value of {metric['id']}")

    def allowed_evidence(self, kind: str, body: dict) -> set[str]:
        if kind == "question":
            return {"owner"}
        if kind == "photo":
            return {"photo"}
        metric = self.metrics.get(body["metric"])
        return {metric["evidence"], *metric["fallback_evidence"]} if metric else set()

    def check_evidence(self, rule: dict):
        honest = set()
        for kind, body in walk_tests(rule["test"]):
            honest |= self.allowed_evidence(kind, body)
        if rule["evidence"] not in honest:
            self.fail(f"{rule['id']}: evidence {rule['evidence']} is not how its metrics are obtained ({sorted(honest)})")

    def check_links(self, rule: dict):
        rid = rule["id"]
        linked = ([rule["counterpart"]] if rule["counterpart"] else []) + rule["stricter_than"]
        for other_id in linked:
            other = self.rules.get(other_id) or self.find_rule(other_id)
            if other is None:
                self.fail(f"{rid}: links to unknown rule {other_id}")
            elif other["jurisdiction"] == rule["jurisdiction"]:
                self.fail(f"{rid}: link {other_id} must be in the other jurisdiction")

    def find_rule(self, rule_id: str):
        for pack in self.packs.values():
            for rule in pack["rules"]:
                if rule["id"] == rule_id:
                    return rule
        return None

    def check_coverage(self):
        coverage = load("coverage.json")
        covered_rule_ids = set()
        seen = set()
        for entry in coverage["entries"]:
            key = (entry["jurisdiction"], entry["section"])
            if key in seen:
                self.fail(f"coverage: duplicate entry {key}")
            seen.add(key)
            self.check_coverage_entry(entry)
            covered_rule_ids.update(entry["rule_ids"])
        for rid, rule in self.rules.items():
            if (rule["jurisdiction"], rule["section"]) not in seen:
                self.fail(f"coverage: section {rule['section']} of {rid} has no coverage entry")
        for rid in set(self.rules) - covered_rule_ids:
            self.fail(f"coverage: rule {rid} is not listed under any covered section")

    def check_coverage_entry(self, entry: dict):
        where = f"coverage {entry['jurisdiction']} {entry['section']}"
        if entry["status"] not in COVERAGE_STATUSES:
            self.fail(f"{where}: bad status {entry['status']}")
        if entry["status"] == "covered" and not entry["rule_ids"]:
            self.fail(f"{where}: covered but no rule_ids")
        if entry["status"] != "covered" and not entry.get("reason"):
            self.fail(f"{where}: {entry['status']} needs a reason")
        for rid in entry["rule_ids"]:
            rule = self.rules.get(rid)
            if rule is None:
                self.fail(f"{where}: unknown rule {rid}")
            elif rule["jurisdiction"] != entry["jurisdiction"]:
                self.fail(f"{where}: rule {rid} is from another jurisdiction")

    def check_precedents(self):
        doc = load("precedents.json")
        ids = set()
        for p in doc["precedents"]:
            if p["id"] in ids:
                self.fail(f"precedents: duplicate id {p['id']}")
            ids.add(p["id"])
            if not str(p.get("source_url", "")).startswith("https://"):
                self.fail(f"precedents {p['id']}: source_url must be https")
            for rid in p["informs_rule_ids"]:
                if rid not in self.rules:
                    self.fail(f"precedents {p['id']}: unknown rule {rid}")


def main() -> int:
    problems = RulepackChecker().run()
    for problem in problems:
        print(problem)
    if problems:
        print(f"FAILED: {len(problems)} problem(s)")
        return 1
    checker_counts = {jur: len(load(f)["rules"]) for jur, f in RULE_FILES.items()}
    print(f"OK: {checker_counts} rules, {len(load('metrics.json')['metrics'])} metrics")
    return 0


if __name__ == "__main__":
    sys.exit(main())
