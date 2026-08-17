from __future__ import annotations

import copy
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from voyage_skill.core import initialize_project, load_events, load_json, project_paths, validate_project


REPOSITORY = Path(__file__).resolve().parents[1]
SCHEMAS = REPOSITORY / "schemas"
BASELINE = "e971047c99ceeded8d7bfadf47cd1427711bf5e0"


def schema_errors(schema_name: str, instance: object) -> list[str]:
    from voyage_skill.schema import validate_instance

    schema = load_json(SCHEMAS / f"{schema_name}.schema.json")
    return validate_instance(instance, schema)


class SchemaContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = initialize_project(self.root, "schema-example")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def assert_schema_valid(self, schema_name: str, instance: object) -> None:
        self.assertEqual(schema_errors(schema_name, instance), [])

    def test_schema_manifest_accepts_initialized_project(self) -> None:
        self.assert_schema_valid("manifest", load_json(self.paths.manifest))

    def test_schema_graph_accepts_initialized_project(self) -> None:
        graph = load_json(self.paths.graph)
        self.assert_schema_valid("graph", graph)
        self.assertEqual(set(graph["loops"]), {"execution", "quality", "governance", "audit"})

    def test_schema_resources_accepts_initialized_project(self) -> None:
        self.assert_schema_valid("resources", load_json(self.paths.resources))

    def test_schema_gates_accepts_initialized_project(self) -> None:
        self.assert_schema_valid("gates", load_json(self.paths.gates))

    def test_schema_events_accept_all_initialized_ledger_events(self) -> None:
        events = load_events(self.paths.ledger)
        self.assertGreater(len(events), 0)
        for event in events:
            with self.subTest(event_id=event["event_id"]):
                self.assert_schema_valid("event", event)

    def test_schema_truth_registry_accepts_dogfood_registry(self) -> None:
        self.assert_schema_valid("truth-registry", load_json(REPOSITORY / "docs" / "truth-registry.json"))

    def test_schema_rejects_unknown_top_level_property(self) -> None:
        manifest = load_json(self.paths.manifest)
        manifest["unexpected"] = True
        errors = schema_errors("manifest", manifest)
        self.assertTrue(any("$" in error and "unexpected" in error for error in errors), errors)

    def test_schema_rejects_missing_required_field(self) -> None:
        manifest = load_json(self.paths.manifest)
        del manifest["project_id"]
        errors = schema_errors("manifest", manifest)
        self.assertTrue(any("$.project_id" in error and "required" in error for error in errors), errors)

    def test_schema_rejects_invalid_enum_pattern_and_const(self) -> None:
        graph = load_json(self.paths.graph)
        graph["loops"][0] = "delivery"
        self.assertTrue(any("enum" in error for error in schema_errors("graph", graph)))

        manifest = load_json(self.paths.manifest)
        manifest["project_id"] = "contains whitespace"
        self.assertTrue(any("pattern" in error for error in schema_errors("manifest", manifest)))

        manifest = load_json(self.paths.manifest)
        manifest["schema_version"] = "9.9.9"
        self.assertTrue(any("const" in error for error in schema_errors("manifest", manifest)))

    def test_schema_unique_and_contains_are_enforced(self) -> None:
        graph = load_json(self.paths.graph)
        graph["node_types"].append(graph["node_types"][0])
        self.assertTrue(any("uniqueItems" in error for error in schema_errors("graph", graph)))

        graph = load_json(self.paths.graph)
        graph["loops"].remove("audit")
        errors = schema_errors("graph", graph)
        self.assertTrue(any("contains" in error and "audit" in error for error in errors), errors)


class DogfoodContractTests(unittest.TestCase):
    def test_repository_root_is_a_valid_voyage_project(self) -> None:
        self.assertEqual(validate_project(project_paths(REPOSITORY)), [])

    def test_all_active_truth_sources_exist(self) -> None:
        registry = load_json(REPOSITORY / "docs" / "truth-registry.json")
        for source in registry["sources"]:
            if source["status"] == "active":
                with self.subTest(source=source["id"]):
                    self.assertTrue((REPOSITORY / source["path"]).is_file())

    def test_one_active_truth_source_per_domain(self) -> None:
        registry = load_json(REPOSITORY / "docs" / "truth-registry.json")
        domains = [source["domain"] for source in registry["sources"] if source["status"] == "active"]
        self.assertEqual(len(domains), len(set(domains)))

    def test_schema_files_are_exercised_by_tests(self) -> None:
        paths = project_paths(REPOSITORY)
        valid_instances = {
            "evidence": {
                "kind": "runtime-readback",
                "version": 1,
                "claim": "schema-fixture",
                "locator": {"environment_id": "fixture", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 60},
                "observed_at": "2026-08-17T00:00:00Z",
                "producer": "schema-test",
            },
            "manifest": load_json(paths.manifest),
            "graph": load_json(paths.graph),
            "resources": load_json(paths.resources),
            "gates": load_json(paths.gates),
            "truth-registry": load_json(paths.truth_registry),
            "event": load_events(paths.ledger)[0],
        }
        self.assertEqual(set(valid_instances), {path.name.removesuffix(".schema.json") for path in SCHEMAS.glob("*.schema.json")})
        for name, valid in valid_instances.items():
            with self.subTest(schema=name, case="valid"):
                self.assertEqual(schema_errors(name, valid), [])
            invalid = copy.deepcopy(valid)
            invalid["__unknown_contract_field__"] = True
            with self.subTest(schema=name, case="invalid"):
                self.assertTrue(schema_errors(name, invalid))

    def test_skill_frontmatter_and_openai_metadata_agree(self) -> None:
        skill = (REPOSITORY / "SKILL.md").read_text(encoding="utf-8")
        metadata = (REPOSITORY / "agents" / "openai.yaml").read_text(encoding="utf-8")
        name_match = re.search(r"^name:\s*([^\s]+)\s*$", skill, flags=re.MULTILINE)
        prompt_match = re.search(r"^\s*default_prompt:\s*[\"'](.*)[\"']\s*$", metadata, flags=re.MULTILINE)
        self.assertIsNotNone(name_match)
        self.assertIsNotNone(prompt_match)
        self.assertIn(f"${name_match.group(1)}", prompt_match.group(1))
        self.assertIn('display_name: "VoyageSkill"', metadata)

    def test_planning_is_registered_as_active_truth(self) -> None:
        registry = load_json(REPOSITORY / "docs" / "truth-registry.json")
        matches = [
            source for source in registry["sources"]
            if source.get("domain") == "planning" and source.get("status") == "active"
        ]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["path"], "docs/planning.md")


class DecisionContractTests(unittest.TestCase):
    def test_decision_d0002_is_registered_and_active(self) -> None:
        decision = REPOSITORY / "docs" / "decisions" / "D-0002-contract-authority.md"
        self.assertTrue(decision.is_file())
        self.assertIn("- Status: active", decision.read_text(encoding="utf-8"))

        registry = load_json(REPOSITORY / "docs" / "truth-registry.json")
        active = [source for source in registry["sources"] if source.get("domain") == "decisions" and source.get("status") == "active"]
        self.assertEqual(len(active), 1)
        decision_source = (REPOSITORY / active[0]["path"]).read_text(encoding="utf-8")
        self.assertIn("D-0002", decision_source)

    def test_authority_documents_tamper_evident_boundary(self) -> None:
        authority = (REPOSITORY / "docs" / "governance" / "authority.md").read_text(encoding="utf-8").lower()
        self.assertIn("tamper-evident", authority)
        self.assertIn("not cryptographically authenticated", authority)

    def test_system_contract_names_runtime_contract_authority(self) -> None:
        system = (REPOSITORY / "docs" / "system" / "graph.md").read_text(encoding="utf-8")
        self.assertIn("Python core validator", system)
        self.assertIn("JSON Schema", system)
        self.assertIn("exchange contract", system)

    def test_planning_history_remains_append_only(self) -> None:
        baseline = subprocess.run(
            ["git", "show", f"{BASELINE}:docs/planning.md"],
            cwd=REPOSITORY,
            check=True,
            text=True,
            capture_output=True,
        ).stdout
        current = (REPOSITORY / "docs" / "planning.md").read_text(encoding="utf-8")
        self.assertTrue(current.startswith(baseline))
        self.assertEqual(current.count("DEV-0001 · MK-000 · START"), 1)


if __name__ == "__main__":
    unittest.main()
