from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import voyage_skill.cli as cli
import voyage_skill.core as core

from tests.support import operational_project, typed_artifact_anchor, typed_command_evidence
from tests.test_contracts import schema_errors


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
GRAPH = REPOSITORY / "docs" / "system" / "graph.md"
SKILL = REPOSITORY / "SKILL.md"
CATALOG_IDS = {
    "advanced-audit", "channel-tracking", "environment-control",
    "quota-cost", "advanced-rules", "derived-graph",
}
AVAILABLE_IDS = {"advanced-audit", "channel-tracking", "environment-control", "derived-graph"}
RESERVED_IDS = CATALOG_IDS - AVAILABLE_IDS
EVENT_EXTENSION_IDS = {"advanced-audit", "channel-tracking", "environment-control"}
EXPECTED_KERNEL_NODES = {
    "project", "principal", "loop-binding", "truth-source", "decision",
    "work-item", "delivery", "immutable-anchor", "evidence", "gate",
    "resource", "lease", "rule", "block", "external-anchor",
}
EXPECTED_KERNEL_EDGES = {
    "governs", "depends-on", "authorized-by", "bound-to-loop", "assigned-to",
    "delivered-via", "claims", "releases", "produces", "anchored-at",
    "validated-by", "rejects", "blocks", "unblocks", "supersedes", "retires",
    "escalates-to",
}
EXPECTED_LOOPS = {"execution", "quality", "governance", "audit"}


class ExtensionTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "extension-example")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def event(
        self,
        event_type: str,
        subject: str,
        *,
        actor: str,
        loop: str,
        payload: dict | None = None,
        evidence: list[str] | None = None,
        authorization: str | None = None,
    ) -> dict:
        return core.append_event(
            self.paths,
            actor=actor,
            loop=loop,
            event_type=event_type,
            subject=subject,
            risk="standard",
            payload=payload,
            evidence=evidence,
            authorization=authorization,
        )

    def decision(
        self,
        decision_id: str,
        *,
        action: str,
        extension_id: str,
        version: str = "1.0.0",
        project_id: str = "extension-example",
    ) -> None:
        self.event(
            "decision.recorded",
            decision_id,
            actor="user",
            loop="user",
            payload={
                "decision": action,
                "scope": {
                    "actions": [action],
                    "project_id": project_id,
                    "extensions": [extension_id],
                    "extension_versions": {extension_id: version},
                },
            },
        )

    def enable(self, extension_id: str, *, decision_id: str | None = None, version: str = "1.0.0") -> dict:
        decision_id = decision_id or f"USER-ENABLE-{extension_id}"
        self.decision(decision_id, action="extension.enable", extension_id=extension_id, version=version)
        return core.enable_extension(
            self.paths,
            actor="gov",
            extension_id=extension_id,
            version=version,
            decision_id=decision_id,
        )

    def disable(self, extension_id: str, *, decision_id: str | None = None, version: str = "1.0.0") -> dict:
        decision_id = decision_id or f"USER-DISABLE-{extension_id}"
        self.decision(decision_id, action="extension.disable", extension_id=extension_id, version=version)
        return core.disable_extension(
            self.paths,
            actor="gov",
            extension_id=extension_id,
            version=version,
            decision_id=decision_id,
        )

    def extension_event(self, extension_id: str, *, suffix: str = "1") -> dict:
        if extension_id == "channel-tracking":
            return self.event("channel.sent", f"channel:{suffix}", actor="dev", loop="execution", payload={"message": suffix})
        if extension_id == "environment-control":
            return self.event("environment.readback", f"environment:{suffix}", actor="dev", loop="execution", evidence=[f"legacy:runtime-{suffix}"])
        if extension_id == "advanced-audit":
            return self.event("audit.finding", f"finding:{suffix}", actor="auditor", loop="audit", evidence=[f"legacy:audit-{suffix}"])
        raise AssertionError(extension_id)


class KernelInitializationTests(ExtensionTestCase):
    def test_new_init_graph_matches_exact_kernel_contract(self) -> None:
        graph = core.load_json(self.paths.graph)
        self.assertEqual(set(core.KERNEL_NODE_TYPES), EXPECTED_KERNEL_NODES)
        self.assertEqual(set(core.KERNEL_EDGE_TYPES), EXPECTED_KERNEL_EDGES)
        self.assertEqual(set(core.KERNEL_LOOPS), EXPECTED_LOOPS)
        self.assertEqual(set(graph["node_types"]), EXPECTED_KERNEL_NODES)
        self.assertEqual(set(graph["edge_types"]), EXPECTED_KERNEL_EDGES)
        self.assertEqual(set(graph["loops"]), EXPECTED_LOOPS)
        self.assertNotIn("channel", graph["node_types"])
        self.assertNotIn("environment", graph["node_types"])

    def test_new_init_creates_no_extension_specific_files_or_enabled_state(self) -> None:
        self.assertFalse((self.paths.control / "extensions").exists())
        self.assertFalse((self.paths.control / "extensions.json").exists())
        self.assertNotIn("extensions", core.load_json(self.paths.manifest))
        state = core.current_state(self.paths)
        self.assertEqual(state["extension_mode"], "explicit")
        self.assertEqual(state["extensions"], {})

    def test_kernel_init_still_supports_complete_core_work_lifecycle(self) -> None:
        self.event("work.created", "W-1", actor="gov", loop="governance", payload={"title": "Core", "scope": "test", "acceptance": ["done"]})
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.event("work.started", "W-1", actor="dev", loop="execution")
        anchor = typed_artifact_anchor(self.paths, name="kernel-delivery")
        execution = typed_command_evidence(self.paths, name="kernel-execution", producer="dev")
        quality = typed_command_evidence(self.paths, name="kernel-quality", producer="qa")
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(
            self.paths, actor="qa", loop="quality", event_type="quality.passed", subject="W-1", risk="standard",
            anchor=anchor, evidence=[quality], payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )
        self.event("work.accepted", "W-1", actor="gov", loop="governance")
        self.event("work.closed", "W-1", actor="gov", loop="governance")
        self.assertEqual(core.current_state(self.paths)["works"]["W-1"]["status"], "closed")

    def test_kernel_contract_keeps_audit_authority_and_environment_resources(self) -> None:
        self.assertIn("audit", core.KERNEL_LOOPS)
        self.assertIn("environment", core.ALLOWED_RESOURCE_TYPES)
        core.register_resource(self.paths, actor="gov", resource_id="environment:test", resource_type="environment", mode="exclusive")
        self.assertEqual(core.load_json(self.paths.resources)["resources"][0]["type"], "environment")

    def test_minimal_init_artifact_contract_is_smaller_than_v01_baseline(self) -> None:
        graph = core.load_json(self.paths.graph)
        self.assertLess(len(graph["node_types"]), 17)
        self.assertLess(len(graph["edge_types"]), 19)
        self.assertFalse(any("extension" in path.name for path in self.paths.control.iterdir()))


class ExtensionCatalogAndEnableTests(ExtensionTestCase):
    def test_extension_catalog_has_six_stable_versioned_entries(self) -> None:
        self.assertEqual(set(core.EXTENSION_CATALOG), CATALOG_IDS)
        for extension_id, contract in core.EXTENSION_CATALOG.items():
            self.assertEqual(contract["id"], extension_id)
            self.assertEqual(contract["version"], "1.0.0")
            self.assertIn(contract["availability"], {"available", "reserved"})
            for field in ("event_types", "node_types", "edge_types", "gates"):
                self.assertIsInstance(contract[field], tuple)
            json.dumps(core.extension_catalog_view(), sort_keys=True)
        self.assertEqual({key for key, value in core.EXTENSION_CATALOG.items() if value["availability"] == "available"}, AVAILABLE_IDS)
        self.assertEqual({key for key, value in core.EXTENSION_CATALOG.items() if value["availability"] == "reserved"}, RESERVED_IDS)

    def test_available_extension_enable_requires_exact_user_scope(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "decision"):
            core.enable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id="missing")

        cases = [
            ("wrong-action", "extension.disable", "channel-tracking", "1.0.0", "extension-example"),
            ("wrong-extension", "extension.enable", "advanced-audit", "1.0.0", "extension-example"),
            ("wrong-version", "extension.enable", "channel-tracking", "2.0.0", "extension-example"),
            ("wrong-project", "extension.enable", "channel-tracking", "1.0.0", "other"),
        ]
        for decision_id, action, extension_id, version, project_id in cases:
            with self.subTest(decision_id=decision_id):
                self.decision(decision_id, action=action, extension_id=extension_id, version=version, project_id=project_id)
                with self.assertRaises(core.VoyageError):
                    core.enable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id=decision_id)

        self.decision("revoked", action="extension.enable", extension_id="channel-tracking")
        self.event("decision.revoked", "revoked", actor="user", loop="user", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            core.enable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id="revoked")

    def test_extension_enable_records_catalog_contract_and_state(self) -> None:
        event = self.enable("channel-tracking")
        self.assertEqual(event["type"], "extension.enabled")
        self.assertEqual(event["payload"]["contract"], core.extension_catalog_view()["channel-tracking"])
        state = core.current_state(self.paths)["extensions"]["channel-tracking"]
        self.assertEqual(state["status"], "enabled")
        self.assertEqual(state["version"], "1.0.0")
        self.assertEqual(state["enabled_event"], event["event_id"])
        self.assertEqual(state["enabled_decision"], "USER-ENABLE-channel-tracking")

    def test_reserved_or_unknown_extension_cannot_enable(self) -> None:
        for extension_id in (*sorted(RESERVED_IDS), "unknown-extension"):
            with self.subTest(extension_id=extension_id):
                self.decision(f"USER-{extension_id}", action="extension.enable", extension_id=extension_id)
                with self.assertRaisesRegex(core.VoyageError, "reserved|unknown"):
                    core.enable_extension(self.paths, actor="gov", extension_id=extension_id, version="1.0.0", decision_id=f"USER-{extension_id}")

    def test_duplicate_or_version_mismatched_enable_is_rejected(self) -> None:
        self.enable("channel-tracking")
        self.decision("USER-ENABLE-AGAIN", action="extension.enable", extension_id="channel-tracking")
        with self.assertRaisesRegex(core.VoyageError, "already enabled"):
            core.enable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id="USER-ENABLE-AGAIN")
        self.decision("USER-BAD-VERSION", action="extension.enable", extension_id="advanced-audit", version="2.0.0")
        with self.assertRaisesRegex(core.VoyageError, "version"):
            core.enable_extension(self.paths, actor="gov", extension_id="advanced-audit", version="2.0.0", decision_id="USER-BAD-VERSION")


class ExtensionDisableTests(ExtensionTestCase):
    def test_extension_disable_requires_exact_user_scope_and_enabled_version(self) -> None:
        self.enable("channel-tracking")
        self.decision("USER-WRONG-DISABLE", action="extension.enable", extension_id="channel-tracking")
        with self.assertRaises(core.VoyageError):
            core.disable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id="USER-WRONG-DISABLE")
        self.decision("USER-WRONG-DISABLE-VERSION", action="extension.disable", extension_id="channel-tracking", version="2.0.0")
        with self.assertRaisesRegex(core.VoyageError, "version"):
            core.disable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="2.0.0", decision_id="USER-WRONG-DISABLE-VERSION")

    def test_extension_disable_preserves_history_and_marks_disabled(self) -> None:
        enabled = self.enable("channel-tracking")
        disabled = self.disable("channel-tracking")
        state = core.current_state(self.paths)["extensions"]["channel-tracking"]
        self.assertEqual(state["status"], "disabled")
        self.assertEqual(state["enabled_event"], enabled["event_id"])
        self.assertEqual(state["disabled_event"], disabled["event_id"])
        self.assertEqual([item["type"] for item in state["history"]], ["extension.enabled", "extension.disabled"])
        status = core.extension_status(self.paths)["extensions"]["channel-tracking"]
        self.assertEqual(status["next_safe_action"], "enable with a new scoped User decision")

    def test_disable_without_decision_or_with_active_mismatch_is_atomic(self) -> None:
        self.enable("channel-tracking")
        before = self.paths.ledger.read_bytes()
        head = core.current_state(self.paths)["last_event"]
        with self.assertRaises(core.VoyageError):
            core.disable_extension(self.paths, actor="gov", extension_id="channel-tracking", version="1.0.0", decision_id="missing")
        self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.assertEqual(core.current_state(self.paths)["last_event"], head)

    def test_extension_contract_cannot_remove_core_gate(self) -> None:
        self.enable("environment-control")
        effective = core.effective_contract(self.paths)
        independent = next(item for item in effective["gates"] if item["id"] == "independent-quality")
        self.assertTrue(independent["mandatory"])
        self.disable("environment-control")
        after = core.effective_contract(self.paths)
        self.assertEqual(next(item for item in after["gates"] if item["id"] == "independent-quality"), independent)


class ExtensionEventGateTests(ExtensionTestCase):
    def test_explicit_project_rejects_extension_events_before_enable(self) -> None:
        self.assertEqual(
            {
                extension_id
                for extension_id, contract in core.EXTENSION_CATALOG.items()
                if contract["availability"] == "available" and contract["event_types"]
            },
            EVENT_EXTENSION_IDS,
        )
        for extension_id in sorted(EVENT_EXTENSION_IDS):
            with self.subTest(extension_id=extension_id), self.assertRaisesRegex(core.VoyageError, "extension .* is not enabled"):
                self.extension_event(extension_id)

    def test_enabled_extension_allows_only_its_mapped_events(self) -> None:
        self.enable("channel-tracking")
        self.extension_event("channel-tracking")
        with self.assertRaisesRegex(core.VoyageError, "environment-control"):
            self.extension_event("environment-control")
        with self.assertRaisesRegex(core.VoyageError, "advanced-audit"):
            self.extension_event("advanced-audit")
        self.enable("environment-control")
        self.enable("advanced-audit")
        self.extension_event("environment-control")
        self.extension_event("advanced-audit")

    def test_disabled_extension_rejects_later_events(self) -> None:
        self.enable("channel-tracking")
        first = self.extension_event("channel-tracking")
        self.disable("channel-tracking")
        with self.assertRaisesRegex(core.VoyageError, "not enabled"):
            self.extension_event("channel-tracking", suffix="2")
        observations = core.current_state(self.paths)["observations"]
        self.assertIn(first["event_id"], {item["event_id"] for item in observations})
        self.assertNotIn("channel:2", {item["subject"] for item in observations})

    def test_core_events_and_minimal_audit_block_work_without_extensions(self) -> None:
        self.event("work.created", "W-1", actor="gov", loop="governance", payload={"title": "Core", "scope": "test", "acceptance": ["done"]})
        self.event(
            "work.blocked", "W-1", actor="auditor", loop="audit", evidence=["legacy:block"],
            payload={"reason": "risk", "scope": "work:W-1", "unblock_condition": "prove safe", "appeal_to": "user"},
        )
        self.event(
            "rule.proposed", "R-1", actor="auditor", loop="audit",
            payload={"scope": "core", "source": "finding", "cost": "low", "verification": "test", "retirement": "obsolete"},
        )
        state = core.current_state(self.paths)
        self.assertEqual(state["works"]["W-1"]["status"], "blocked")
        self.assertEqual(state["rules"]["R-1"]["status"], "proposed")

    def test_legacy_project_replays_pre_layer_extension_events(self) -> None:
        events = core.load_events(self.paths.ledger)
        for item in events:
            if item["type"] == "project.initialized":
                item["payload"].pop("extension_mode", None)
            item["prev_hash"] = events[events.index(item) - 1]["hash"] if events.index(item) else None
            body = {key: value for key, value in item.items() if key != "hash"}
            item["hash"] = core.content_hash(body)
        self.paths.ledger.write_text("".join(core.canonical_json(item) + "\n" for item in events), encoding="utf-8")
        self.extension_event("channel-tracking")
        self.extension_event("environment-control")
        self.extension_event("advanced-audit")
        state = core.current_state(self.paths)
        self.assertEqual(state["extension_mode"], "legacy-compatible")
        self.assertEqual(state["extensions"], {})


class ExtensionCliRecoverySchemaTests(ExtensionTestCase):
    def run_cli(self, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *args],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, expected, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        return json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}

    def test_extension_cli_lists_catalog_and_current_status(self) -> None:
        listed = self.run_cli("extension", "list")
        status = self.run_cli("extension", "status")
        self.assertEqual(set(listed["catalog"]), CATALOG_IDS)
        self.assertEqual(status["mode"], "explicit")
        self.assertEqual(status["enabled"], [])
        self.assertIn("independent-quality", {item["id"] for item in status["effective_contract"]["gates"]})

    def test_extension_cli_enable_disable_round_trip(self) -> None:
        self.decision("USER-CLI-ENABLE", action="extension.enable", extension_id="channel-tracking")
        enabled = self.run_cli("extension", "enable", "channel-tracking", "--version", "1.0.0", "--decision", "USER-CLI-ENABLE", "--actor", "gov")
        self.assertEqual(enabled["status"], "enabled")
        self.decision("USER-CLI-DISABLE", action="extension.disable", extension_id="channel-tracking")
        disabled = self.run_cli("extension", "disable", "channel-tracking", "--version", "1.0.0", "--decision", "USER-CLI-DISABLE", "--actor", "gov")
        self.assertEqual(disabled["status"], "disabled")
        self.assertEqual(self.run_cli("recover")["extensions"]["extensions"]["channel-tracking"]["status"], "disabled")

    def test_recovery_reports_extension_history_and_next_safe_action(self) -> None:
        self.enable("channel-tracking")
        self.disable("channel-tracking")
        snapshot = core.recovery_snapshot(self.paths)
        extensions = snapshot["extensions"]
        self.assertEqual(extensions["mode"], "explicit")
        self.assertEqual(extensions["extensions"]["channel-tracking"]["status"], "disabled")
        self.assertNotIn("derived-graph", extensions["reserved"])
        self.assertNotIn("derived-graph", extensions["enabled"])

    def test_extension_events_match_runtime_schema_and_replay(self) -> None:
        enabled = self.enable("channel-tracking")
        disabled = self.disable("channel-tracking")
        self.assertTrue({"extension.enabled", "extension.disabled"}.issubset(core.SUPPORTED_EVENT_TYPES))
        self.assertTrue({"extension.enabled", "extension.disabled"}.issubset(cli.CLI_EVENT_TYPES))
        event_schema = core.load_json(REPOSITORY / "schemas" / "event.schema.json")
        self.assertEqual(schema_errors("event", enabled), [])
        self.assertEqual(schema_errors("event", disabled), [])
        self.assertIn("extension.enabled", event_schema["properties"]["type"]["enum"])
        self.assertEqual(core.current_state(self.paths)["extensions"]["channel-tracking"]["status"], "disabled")

    def test_cli_reference_includes_all_extension_leaf_commands(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        text = text[text.index("<!-- voyage-cli-reference:start -->"):text.index("<!-- voyage-cli-reference:end -->")]
        for command in ("voyage extension list", "voyage extension status", "voyage extension enable", "voyage extension disable"):
            self.assertEqual(text.count(f"`{command}`"), 1)


class ExtensionDocsAndDogfoodTests(ExtensionTestCase):
    def test_system_graph_documents_exact_kernel_and_catalog_contract(self) -> None:
        text = GRAPH.read_text(encoding="utf-8")
        kernel = text[text.index("<!-- kernel-contract:start -->"):text.index("<!-- kernel-contract:end -->")]
        extension = text[text.index("<!-- extension-contract:start -->"):text.index("<!-- extension-contract:end -->")]
        for value in (*EXPECTED_KERNEL_NODES, *EXPECTED_KERNEL_EDGES, *EXPECTED_LOOPS):
            self.assertIn(f"`{value}`", kernel)
        for value in CATALOG_IDS:
            self.assertIn(f"`{value}`", extension)
        self.assertNotIn("`channel`", kernel)
        self.assertNotIn("`environment`", kernel)

    def test_skill_loads_extension_contract_only_for_extension_tasks(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        section = text[text.index("<!-- extension-loading:start -->"):text.index("<!-- extension-loading:end -->")]
        self.assertIn("extension status", section)
        self.assertIn("active system", section)
        self.assertIn("only", section.lower())
        self.assertNotIn("docs/extensions/", section)

    def test_runbook_documents_decision_bound_enable_disable_and_legacy_behavior(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        section = text[text.index("<!-- extension-operations:start -->"):text.index("<!-- extension-operations:end -->")]
        for value in ("extension.enable", "extension.disable", "project_id", "extensions", "extension_versions", "reserved", "legacy-compatible"):
            self.assertIn(f"`{value}`", section)

    def test_dogfood_project_remains_valid_and_reports_legacy_extension_mode(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.validate_project(paths), [])
        status = core.extension_status(paths)
        self.assertEqual(status["mode"], "legacy-compatible")
        self.assertEqual(status["enabled"], [])
        self.assertEqual(core.recovery_snapshot(paths)["extensions"], status)


if __name__ == "__main__":
    unittest.main()
