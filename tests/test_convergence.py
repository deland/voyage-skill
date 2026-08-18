from __future__ import annotations

import copy
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import voyage_skill.cli as cli
import voyage_skill.core as core

from tests.support import (
    activate_all_truth,
    operational_project,
    reviewed_contracts,
    typed_artifact_anchor,
    typed_command_evidence,
)
from tests.test_contracts import schema_errors


REPOSITORY = Path(__file__).resolve().parents[1]
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
GRAPH = REPOSITORY / "docs" / "system" / "graph.md"
AUTHORITY = REPOSITORY / "docs" / "governance" / "authority.md"
SKILL = REPOSITORY / "SKILL.md"
REFERENCE_SCRIPT = REPOSITORY / "scripts" / "voyage-reference.py"

EXPECTED_WORK_DURABLE = {"draft", "authorized", "active", "delivered", "quality-passed", "accepted", "closed"}
EXPECTED_WORK_SIDE = {"rejected", "blocked", "awaiting-user"}
EXPECTED_RULE_STATES = {"proposed", "approved", "applied", "active", "retired", "superseded"}
EXPECTED_EVENTS = {
    "project.initialized", "truth.activated", "project.migrated", "evidence.verified", "audit.checked",
    "extension.enabled", "extension.disabled",
    "decision.recorded", "decision.revoked", "observation.recorded", "environment.readback",
    "channel.sent", "channel.acknowledged", "channel.started", "audit.finding",
    "work.created", "work.authorized", "work.started", "work.delivered",
    "quality.passed", "quality.rejected", "gate.recorded", "work.accepted", "work.closed",
    "work.blocked", "work.unblocked", "work.awaiting-user", "work.user-authorized",
    "resource.registered", "resource.claimed", "resource.released", "resource.recovered",
    "rule.proposed", "rule.approved", "rule.applied", "rule.verified",
    "rule.verification-failed", "rule.rolled-back", "rule.superseded", "rule.retired",
}


def event(
    paths: core.ProjectPaths,
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
        paths,
        actor=actor,
        loop=loop,
        event_type=event_type,
        subject=subject,
        risk="standard",
        payload=payload,
        evidence=evidence,
        authorization=authorization,
    )


class ConvergenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "convergence")
        self.resource_probe = typed_command_evidence(self.paths, name="resource-probe", producer="probe")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def create_authorized_work(self, work_id: str = "W-1") -> None:
        event(self.paths, "work.created", work_id, actor="gov", loop="governance", payload={"title": "Converge", "scope": "test", "acceptance": ["done"]})
        event(self.paths, "work.authorized", work_id, actor="gov", loop="governance")

    def quality_passed_work(self, work_id: str = "W-1") -> None:
        self.create_authorized_work(work_id)
        anchor = typed_artifact_anchor(self.paths, name=f"{work_id}-delivery")
        execution = typed_command_evidence(self.paths, name=f"{work_id}-execution", producer="dev")
        quality = typed_command_evidence(self.paths, name=f"{work_id}-quality", producer="qa")
        event(self.paths, "work.started", work_id, actor="dev", loop="execution")
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject=work_id, risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(
            self.paths,
            actor="qa",
            loop="quality",
            event_type="quality.passed",
            subject=work_id,
            risk="standard",
            anchor=anchor,
            evidence=[quality],
            payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )

    def propose_approved_applied_rule(self, rule_id: str = "R-1") -> None:
        event(self.paths, "rule.proposed", rule_id, actor="audit", loop="audit", payload={"scope": "test", "source": "incident", "cost": "low", "verification": "fixture", "retirement": "obsolete"})
        event(self.paths, "rule.approved", rule_id, actor="gov", loop="governance")
        event(self.paths, "rule.applied", rule_id, actor="operator", loop="governance", evidence=["diff:rule"])


class WorkStateConvergenceTests(ConvergenceTestCase):
    def test_work_state_contract_matches_exact_runtime_sets(self) -> None:
        self.assertEqual(set(core.WORK_DURABLE_STATES), EXPECTED_WORK_DURABLE)
        self.assertEqual(set(core.WORK_SIDE_STATES), EXPECTED_WORK_SIDE)

    def test_system_graph_documents_only_reachable_work_states(self) -> None:
        text = GRAPH.read_text(encoding="utf-8")
        match = re.search(r"<!-- work-states:start -->(.*?)<!-- work-states:end -->", text, flags=re.DOTALL)
        self.assertIsNotNone(match)
        documented = set(re.findall(r"`([a-z-]+)`", match.group(1)))
        self.assertEqual(documented, EXPECTED_WORK_DURABLE | EXPECTED_WORK_SIDE)
        for removed in ("ready", "canceled"):
            self.assertNotIn(removed, match.group(1))
        self.assertNotIn("work `superseded`", match.group(1))

    def test_next_safe_action_covers_only_reachable_work_states(self) -> None:
        expected = EXPECTED_WORK_DURABLE | EXPECTED_WORK_SIDE
        self.assertEqual(set(core.NEXT_SAFE_ACTIONS), expected)
        for state in expected:
            action = core.next_safe_action({"status": state})
            self.assertNotEqual(action, "inspect unknown state")

    def test_blocked_and_awaiting_user_restore_exact_previous_state(self) -> None:
        self.quality_passed_work("W-BLOCK")
        event(self.paths, "work.blocked", "W-BLOCK", actor="audit", loop="audit", evidence=["finding"], payload={"block_id": "B-1", "reason": "check", "scope": "W-BLOCK", "unblock_condition": "clear", "appeal_to": "user"})
        event(self.paths, "work.unblocked", "W-BLOCK", actor="user", loop="user", evidence=["appeal"])
        self.assertEqual(core.current_state(self.paths)["works"]["W-BLOCK"]["status"], "quality-passed")

        self.quality_passed_work("W-USER")
        event(self.paths, "work.awaiting-user", "W-USER", actor="gov", loop="governance", payload={"decision": "continue"})
        event(self.paths, "decision.recorded", "USER-CONTINUE", actor="user", loop="user", payload={"decision": "continue"})
        event(self.paths, "work.user-authorized", "W-USER", actor="gov", loop="governance", authorization="USER-CONTINUE")
        self.assertEqual(core.current_state(self.paths)["works"]["W-USER"]["status"], "quality-passed")


class RuleStateConvergenceTests(ConvergenceTestCase):
    def test_rule_state_contract_matches_exact_runtime_sets(self) -> None:
        self.assertEqual(set(core.RULE_DURABLE_STATES), EXPECTED_RULE_STATES)

    def test_failed_rule_verification_remains_applied_and_records_failure(self) -> None:
        self.propose_approved_applied_rule()
        failed = event(self.paths, "rule.verification-failed", "R-1", actor="qa", loop="quality", evidence=["test:failed"], payload={"reason": "did not prevent recurrence"})
        rule = core.current_state(self.paths)["rules"]["R-1"]
        self.assertEqual(rule["status"], "applied")
        self.assertEqual(rule["verification_status"], "failed")
        self.assertEqual(rule["verification_event"], failed["event_id"])
        self.assertEqual(rule["verifier"], "qa")

    def test_rule_rollback_requires_failure_governance_and_evidence(self) -> None:
        self.propose_approved_applied_rule()
        with self.assertRaisesRegex(core.VoyageError, "failed verification"):
            event(self.paths, "rule.rolled-back", "R-1", actor="gov", loop="governance", evidence=["rollback"])
        event(self.paths, "rule.verification-failed", "R-1", actor="qa", loop="quality", evidence=["failed"], payload={"reason": "bad"})
        with self.assertRaisesRegex(core.VoyageError, "governance"):
            event(self.paths, "rule.rolled-back", "R-1", actor="qa", loop="quality", evidence=["rollback"])
        with self.assertRaisesRegex(core.VoyageError, "evidence"):
            event(self.paths, "rule.rolled-back", "R-1", actor="gov", loop="governance")

    def test_successful_rule_rollback_returns_to_approved_and_can_reapply(self) -> None:
        self.propose_approved_applied_rule()
        event(self.paths, "rule.verification-failed", "R-1", actor="qa", loop="quality", evidence=["failed"], payload={"reason": "bad"})
        rollback = event(self.paths, "rule.rolled-back", "R-1", actor="gov", loop="governance", evidence=["rollback"])
        rule = core.current_state(self.paths)["rules"]["R-1"]
        self.assertEqual(rule["status"], "approved")
        self.assertEqual(rule["rollback_event"], rollback["event_id"])
        event(self.paths, "rule.applied", "R-1", actor="operator-2", loop="governance", evidence=["diff:v2"])
        event(self.paths, "rule.verified", "R-1", actor="qa-2", loop="quality", evidence=["pass:v2"])
        self.assertEqual(core.current_state(self.paths)["rules"]["R-1"]["status"], "active")

    def test_rule_cli_exposes_verify_fail_and_rollback(self) -> None:
        parser = cli.build_parser()
        fail_args = parser.parse_args(["--root", str(self.root), "rule", "verify-fail", "R-1", "--reason", "bad", "--evidence", "test", "--actor", "qa", "--loop", "quality"])
        rollback_args = parser.parse_args(["--root", str(self.root), "rule", "rollback", "R-1", "--evidence", "rollback", "--actor", "gov"])
        self.assertEqual(fail_args.rule_command, "verify-fail")
        self.assertEqual(rollback_args.rule_command, "rollback")

    def test_governance_and_graph_document_only_real_rule_states_and_failure_path(self) -> None:
        authority = AUTHORITY.read_text(encoding="utf-8")
        graph = GRAPH.read_text(encoding="utf-8")
        for text in (authority, graph):
            match = re.search(r"<!-- rule-states:start -->(.*?)<!-- rule-states:end -->", text, flags=re.DOTALL)
            self.assertIsNotNone(match)
            documented = set(re.findall(r"`([a-z-]+)`", match.group(1)))
            self.assertEqual(documented & EXPECTED_RULE_STATES, EXPECTED_RULE_STATES)
            self.assertNotIn("`verified`", match.group(1))
            self.assertNotIn("`deprecated`", match.group(1))
            self.assertIn("verification-failed", match.group(1))
            self.assertIn("rolled-back", match.group(1))


class CliReferenceConvergenceTests(unittest.TestCase):
    def reference_module(self):
        from voyage_skill import reference

        return reference

    def test_cli_reference_contains_every_leaf_command_exactly_once(self) -> None:
        reference = self.reference_module()
        expected = reference.cli_leaf_commands(cli.build_parser())
        documented = reference.documented_commands(RUNBOOK.read_text(encoding="utf-8"))
        self.assertEqual(documented, expected)
        self.assertEqual(len(documented), len(set(documented)))

    def test_cli_reference_render_is_deterministic(self) -> None:
        reference = self.reference_module()
        self.assertEqual(reference.render_cli_reference(), reference.render_cli_reference())

    def test_cli_reference_check_detects_drift(self) -> None:
        reference = self.reference_module()
        current = RUNBOOK.read_text(encoding="utf-8")
        self.assertEqual(reference.check_cli_reference(current), [])
        drifted = current.replace("voyage work create", "voyage work ghost", 1)
        self.assertTrue(reference.check_cli_reference(drifted))

    def test_cli_reference_script_supports_check_and_print(self) -> None:
        checked = subprocess.run([sys.executable, "-B", str(REFERENCE_SCRIPT), "--check", str(RUNBOOK)], cwd=REPOSITORY, text=True, capture_output=True)
        self.assertEqual(checked.returncode, 0, checked.stderr)
        printed = subprocess.run([sys.executable, "-B", str(REFERENCE_SCRIPT), "--print"], cwd=REPOSITORY, text=True, capture_output=True)
        self.assertEqual(printed.returncode, 0, printed.stderr)
        self.assertIn("voyage work create", printed.stdout)


class SkillDiscoveryConvergenceTests(unittest.TestCase):
    def test_skill_has_no_repository_specific_truth_paths(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for path in ("docs/product/contract.md", "docs/governance/authority.md", "docs/system/graph.md", "docs/operations/runbook.md", "docs/truth-registry.json"):
            self.assertNotIn(path, text)
        self.assertIn("manifest", text)
        self.assertIn("truth registry", text)

    def test_skill_names_the_same_required_domains_as_runtime(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        for domain in core.REQUIRED_TRUTH_DOMAINS:
            self.assertRegex(text, rf"\b{domain}\b")
        with tempfile.TemporaryDirectory() as directory:
            paths = core.initialize_project(Path(directory), "domains")
            init_domains = {item["domain"] for item in core.load_json(paths.truth_registry)["sources"]}
        dogfood_domains = {
            item["domain"] for item in core.load_json(REPOSITORY / "docs" / "truth-registry.json")["sources"]
            if item["domain"] in core.REQUIRED_TRUTH_DOMAINS
        }
        self.assertEqual(init_domains, set(core.REQUIRED_TRUTH_DOMAINS))
        self.assertEqual(dogfood_domains, set(core.REQUIRED_TRUTH_DOMAINS))

    def test_custom_registry_paths_are_discoverable_without_skill_change(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            sources = []
            for domain in core.REQUIRED_TRUTH_DOMAINS:
                path = f"custom/contracts/{domain}.txt"
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"{domain} contract\n", encoding="utf-8")
                sources.append({"id": f"custom-{domain}", "domain": domain, "path": path, "version": "1", "status": "active"})
            registry = root / "config" / "truth.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(json.dumps({"schema_version": "0.1.0", "project": "custom", "sources": sources}), encoding="utf-8")
            paths = core.initialize_project(root, "custom", "config/truth.json")
            status = core.truth_status(paths)
            self.assertEqual({item["path"] for item in status["sources"]}, {item["path"] for item in sources})

    def test_metadata_and_skill_identity_remain_consistent(self) -> None:
        skill = SKILL.read_text(encoding="utf-8")
        metadata = (REPOSITORY / "agents" / "openai.yaml").read_text(encoding="utf-8")
        name = re.search(r"^name:\s*([^\s]+)", skill, flags=re.MULTILINE).group(1)
        self.assertIn('display_name: "VoyageSkill"', metadata)
        self.assertIn(f"${name}", metadata)


class ResourceSubjectConvergenceTests(ConvergenceTestCase):
    def setUp(self) -> None:
        super().setUp()
        core.register_resource(self.paths, actor="gov", resource_id="file:shared", resource_type="file", mode="exclusive")
        self.create_authorized_work()

    def claim(self, lease_id: str) -> None:
        event(self.paths, "resource.claimed", "file:shared", actor="dev", loop="execution", evidence=[self.resource_probe], payload={"resource_id": "file:shared", "lease_id": lease_id, "work_id": "W-1", "expires_at": "2099-01-01T00:00:00Z"})

    def test_claim_release_and_recover_use_resource_subject_with_both_ids(self) -> None:
        self.claim("L-1")
        event(self.paths, "resource.released", "file:shared", actor="dev", loop="execution", payload={"resource_id": "file:shared", "lease_id": "L-1"})
        self.claim("L-2")
        event(self.paths, "resource.recovered", "file:shared", actor="gov", loop="governance", evidence=["probe"], payload={"resource_id": "file:shared", "lease_id": "L-2"})
        lease_events = [item for item in core.load_events(self.paths.ledger) if item["type"] in {"resource.claimed", "resource.released", "resource.recovered"}]
        self.assertEqual([item["subject"] for item in lease_events], ["file:shared"] * 4)
        for item in lease_events:
            self.assertEqual(item["payload"]["resource_id"], "file:shared")
            self.assertTrue(item["payload"]["lease_id"])

    def test_resource_event_rejects_subject_or_payload_identity_mismatch(self) -> None:
        self.claim("L-1")
        with self.assertRaisesRegex(core.VoyageError, "resource identity"):
            event(self.paths, "resource.released", "L-1", actor="dev", loop="execution", payload={"resource_id": "file:shared", "lease_id": "L-1"})
        with self.assertRaisesRegex(core.VoyageError, "resource identity"):
            event(self.paths, "resource.released", "file:shared", actor="dev", loop="execution", payload={"resource_id": "file:other", "lease_id": "L-1"})

    def test_resource_cli_resolves_resource_id_for_release_and_recovery(self) -> None:
        script = REPOSITORY / "scripts" / "voyage.py"
        self.claim("L-CLI-1")
        released = subprocess.run([sys.executable, "-B", str(script), "--root", str(self.root), "resource", "release", "L-CLI-1", "--actor", "dev", "--loop", "execution"], text=True, capture_output=True)
        self.assertEqual(released.returncode, 0, released.stderr)
        self.claim("L-CLI-2")
        recovered = subprocess.run([sys.executable, "-B", str(script), "--root", str(self.root), "resource", "recover", "L-CLI-2", "--evidence", "probe", "--actor", "gov", "--loop", "governance"], text=True, capture_output=True)
        self.assertEqual(recovered.returncode, 0, recovered.stderr)
        events = [item for item in core.load_events(self.paths.ledger) if item["type"] in {"resource.released", "resource.recovered"}]
        self.assertEqual([(item["subject"], item["payload"]["resource_id"]) for item in events], [("file:shared", "file:shared"), ("file:shared", "file:shared")])

    def test_event_data_validation_reports_legacy_ambiguous_resource_identity(self) -> None:
        bad = core.make_event(None, actor="dev", loop="execution", event_type="resource.released", subject="L-1", risk="standard", payload={"lease_id": "L-1"})
        errors = core._validate_event_data([bad])
        self.assertTrue(any("resource_id" in error for error in errors), errors)
        self.assertTrue(any("subject" in error for error in errors), errors)


class EventExchangeConvergenceTests(unittest.TestCase):
    def test_event_schema_enum_matches_runtime_supported_events(self) -> None:
        schema = core.load_json(REPOSITORY / "schemas" / "event.schema.json")
        self.assertEqual(set(core.SUPPORTED_EVENT_TYPES), EXPECTED_EVENTS)
        self.assertEqual(set(schema["properties"]["type"]["enum"]), EXPECTED_EVENTS)

    def test_all_runtime_event_types_have_replay_coverage(self) -> None:
        source = (REPOSITORY / "src" / "voyage_skill" / "core.py").read_text(encoding="utf-8")
        for event_type in core.SUPPORTED_EVENT_TYPES:
            with self.subTest(event_type=event_type):
                self.assertIn(f'"{event_type}"', source)

    def test_all_cli_transition_events_are_in_runtime_and_schema(self) -> None:
        schema = core.load_json(REPOSITORY / "schemas" / "event.schema.json")
        runtime = set(core.SUPPORTED_EVENT_TYPES)
        exchange = set(schema["properties"]["type"]["enum"])
        self.assertEqual(set(cli.CLI_EVENT_TYPES) - runtime, set())
        self.assertEqual(set(cli.CLI_EVENT_TYPES) - exchange, set())

    def test_new_rule_and_resource_events_validate_against_event_schema(self) -> None:
        previous = None
        for event_type, subject, payload in (
            ("rule.verification-failed", "R-1", {"reason": "bad"}),
            ("rule.rolled-back", "R-1", {}),
            ("resource.released", "file:shared", {"resource_id": "file:shared", "lease_id": "L-1"}),
        ):
            instance = core.make_event(previous, actor="tester", loop="governance", event_type=event_type, subject=subject, risk="standard", payload=payload)
            self.assertEqual(schema_errors("event", instance), [])
            previous = instance["hash"]
        bad = copy.deepcopy(instance)
        bad["type"] = "work.ready"
        self.assertTrue(any("enum" in error for error in schema_errors("event", bad)))


class ResearchIsolationConvergenceTests(unittest.TestCase):
    def research_documents(self) -> list[Path]:
        return sorted((REPOSITORY / "docs" / "research").glob("*"))

    def test_every_research_document_has_standard_non_authoritative_marker(self) -> None:
        for path in self.research_documents():
            with self.subTest(path=path.name):
                self.assertIn("Research input — non-authoritative and non-executable", path.read_text(encoding="utf-8"))

    def test_research_marker_explicitly_forbids_execution_and_truth_use(self) -> None:
        for path in self.research_documents():
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("must not be used as project truth", text)
                self.assertIn("must not be executed", text)

    def test_dogfood_registry_keeps_research_non_authoritative(self) -> None:
        registry = core.load_json(REPOSITORY / "docs" / "truth-registry.json")
        self.assertIn("docs/research/", registry["non_authoritative"])

    def test_dogfood_validate_recover_and_schema_coverage_remain_green(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.validate_project(paths), [])
        self.assertEqual(core.recovery_snapshot(paths)["project_stage"], "operational")
        schema_names = {path.name.removesuffix(".schema.json") for path in (REPOSITORY / "schemas").glob("*.schema.json")}
        self.assertIn("event", schema_names)
        self.assertIn("evidence", schema_names)


if __name__ == "__main__":
    unittest.main()
