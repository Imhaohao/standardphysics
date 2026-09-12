"""Every contract model as one JSON Schema, for generating the web's types.

    python -m standardphysics_contracts.json_schema > contracts.schema.json

Two choices make the TypeScript honest. Fields with a default are required,
because the server always sends them, so `Scan.artifacts` is `Artifact[]`
rather than optional. And fields carry no generated title, because the
TypeScript generator names types after titles and a dozen fields called `kind`
would come out as `Kind1`, `Kind2`, numbered by position.
"""

from __future__ import annotations

import inspect
import json
import sys

from pydantic import BaseModel
from pydantic.json_schema import GenerateJsonSchema, models_json_schema

import standardphysics_contracts


class WireSchema(GenerateJsonSchema):
    def field_is_required(self, field, total: bool) -> bool:
        return field.get("serialization_exclude_if") is None

    def field_title_should_be_set(self, schema) -> bool:
        return False


def contract_models() -> list[type[BaseModel]]:
    exported = (getattr(standardphysics_contracts, name) for name in standardphysics_contracts.__all__)
    return [item for item in exported if inspect.isclass(item) and issubclass(item, BaseModel)]


def bundle() -> dict:
    _, schema = models_json_schema(
        [(model, "serialization") for model in contract_models()],
        title="StandardPhysicsContracts",
        schema_generator=WireSchema,
    )
    for definition in schema["$defs"].values():
        definition.setdefault("additionalProperties", False)
    return schema


if __name__ == "__main__":
    json.dump(bundle(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
