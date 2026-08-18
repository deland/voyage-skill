from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from voyage_skill.core import (
    VoyageError,
    append_event,
    atomic_write_json,
    canonical_json,
    content_hash,
    initialize_project,
    load_events,
    load_json,
    recovery_snapshot,
    register_resource,
    validate_project,
)
from tests.support import typed_command_evidence


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"


class DamagedInputTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = initialize_project(self.root, "damaged-input")
        self.resource_probe = typed_command_evidence(self.paths, name="damaged-resource-probe", producer="probe")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_events_with_valid_chain(self, events: list[dict]) -> None:
        previous = None
        for event in events:
            event["prev_hash"] = previous
            body = {key: value for key, value in event.items() if key != "hash"}
            event["hash"] = content_hash(body)
            previous = event["hash"]
        self.paths.ledger.write_text(
            "".join(canonical_json(event) + "\n" for event in events),
            encoding="utf-8",
        )

    def _create_claimed_resource(self, expires_at: str = "2099-01-01T00:00:00Z") -> None:
        register_resource(
            self.paths,
            actor="gov",
            resource_id="file:shared",
            resource_type="file",
            mode="exclusive",
        )
        append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject="W-1",
            risk="standard",
            payload={"title": "Damaged", "scope": "test", "acceptance": ["validates"], "required_resources": ["file:shared"]},
        )
        append_event(
            self.paths,
            actor="dev",
            loop="execution",
            event_type="resource.claimed",
            subject="file:shared",
            risk="standard",
            evidence=[self.resource_probe],
            payload={"resource_id": "file:shared", "lease_id": "lease-1", "work_id": "W-1", "expires_at": expires_at},
        )

    def test_validate_reports_missing_lease_expiry(self) -> None:
        self._create_claimed_resource()
        events = load_events(self.paths.ledger)
        del events[-1]["payload"]["expires_at"]
        self._write_events_with_valid_chain(events)
        errors = validate_project(self.paths)
        self.assertTrue(any("expires_at" in error for error in errors), errors)

    def test_validate_reports_invalid_lease_timestamp(self) -> None:
        self._create_claimed_resource(expires_at="not-a-timestamp")
        errors = validate_project(self.paths)
        self.assertTrue(any("expires_at" in error and "date-time" in error for error in errors), errors)
        with self.assertRaisesRegex(VoyageError, "expires_at.*date-time"):
            recovery_snapshot(self.paths)

    def test_validate_reports_wrong_event_payload_shape(self) -> None:
        events = load_events(self.paths.ledger)
        events[0]["payload"] = ["not", "an", "object"]
        self._write_events_with_valid_chain(events)
        errors = validate_project(self.paths)
        self.assertTrue(any("payload" in error and "object" in error for error in errors), errors)

    def test_validate_reports_wrong_truth_source_shape(self) -> None:
        registry = load_json(self.paths.truth_registry)
        registry["sources"][0] = "not-an-object"
        atomic_write_json(self.paths.truth_registry, registry)
        errors = validate_project(self.paths)
        self.assertTrue(any("$.sources[0]" in error and "object" in error for error in errors), errors)

    def test_validate_reports_bad_gate_definition(self) -> None:
        gates = load_json(self.paths.gates)
        del gates["gates"][0]["mandatory"]
        atomic_write_json(self.paths.gates, gates)
        errors = validate_project(self.paths)
        self.assertTrue(any("$.gates[0].mandatory" in error and "required" in error for error in errors), errors)

    def test_validate_reports_bad_graph_definition(self) -> None:
        graph = load_json(self.paths.graph)
        graph["loops"].remove("audit")
        graph["node_types"].append(graph["node_types"][0])
        atomic_write_json(self.paths.graph, graph)
        errors = validate_project(self.paths)
        self.assertTrue(any("audit" in error and "contains" in error for error in errors), errors)
        self.assertTrue(any("node_types" in error and "uniqueItems" in error for error in errors), errors)

    def test_cli_validate_never_prints_traceback_for_project_data_error(self) -> None:
        self._create_claimed_resource()
        events = load_events(self.paths.ledger)
        del events[-1]["payload"]["expires_at"]
        self._write_events_with_valid_chain(events)
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "validate"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["valid"])
        self.assertTrue(any("expires_at" in error for error in report["errors"]))


if __name__ == "__main__":
    unittest.main()
