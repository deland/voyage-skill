from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from voyage_skill.core import (
    VoyageError,
    append_event,
    atomic_write_json,
    current_state,
    initialize_project,
    load_events,
    recovery_snapshot,
    register_resource,
    validate_project,
)
from tests.support import operational_project, typed_artifact_anchor, typed_command_evidence


class VoyageCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "example")
        self.anchor = typed_artifact_anchor(self.paths, name="default-delivery")
        self.execution_evidence = typed_command_evidence(self.paths, name="execution", producer="dev")
        self.quality_evidence = typed_command_evidence(self.paths, name="quality", producer="qa")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def event(self, event_type: str, subject: str, *, actor: str, loop: str, risk: str = "standard", payload=None, evidence=None, anchor=None, authorization=None):
        return append_event(
            self.paths,
            actor=actor,
            loop=loop,
            event_type=event_type,
            subject=subject,
            risk=risk,
            payload=payload,
            evidence=evidence,
            anchor=anchor,
            authorization=authorization,
        )

    def create_work(self, work_id: str = "W-1", *, risk: str = "standard", resources=None) -> None:
        self.event(
            "work.created",
            work_id,
            actor="gov",
            loop="governance",
            risk=risk,
            payload={"title": "Example", "scope": "temporary test project", "acceptance": ["verified"], "dependencies": [], "required_resources": resources or []},
        )

    def deliver(self, work_id: str = "W-1", *, anchor: str | None = None) -> None:
        self.event("work.started", work_id, actor="dev", loop="execution")
        self.event("work.delivered", work_id, actor="dev", loop="execution", anchor=anchor or self.anchor, evidence=[self.execution_evidence])

    def quality_pass(self, work_id: str = "W-1", *, anchor: str | None = None) -> None:
        self.event(
            "quality.passed",
            work_id,
            actor="qa",
            loop="quality",
            anchor=anchor or self.anchor,
            evidence=[self.quality_evidence],
            payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )

    def test_init_is_valid_and_recoverable(self) -> None:
        self.assertEqual(validate_project(self.paths), [])
        snapshot = recovery_snapshot(self.paths)
        self.assertEqual(snapshot["work"], [])
        self.assertIsNotNone(snapshot["ledger_head"])

    def test_init_can_adopt_existing_truth_registry(self) -> None:
        other = self.root / "adopted"
        source = other / "docs" / "truth.json"
        source.parent.mkdir(parents=True)
        contract = other / "docs" / "product.md"
        contract.write_text("# Product\n", encoding="utf-8")
        source.write_text(
            json.dumps({
                "schema_version": "0.1.0",
                "project": "adopted",
                "sources": [{"id": "product", "domain": "product", "path": "docs/product.md", "version": "1", "status": "active"}],
            }),
            encoding="utf-8",
        )
        paths = initialize_project(other, "adopted", "docs/truth.json")
        self.assertEqual(validate_project(paths), [])
        self.assertFalse((other / "docs" / "voyage").exists())

    def test_complete_work_lifecycle(self) -> None:
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.deliver()
        self.quality_pass()
        self.event("work.accepted", "W-1", actor="gov", loop="governance")
        self.event("work.closed", "W-1", actor="gov", loop="governance")
        state = current_state(self.paths)
        self.assertEqual(state["works"]["W-1"]["status"], "closed")
        self.assertEqual(validate_project(self.paths), [])

    def test_work_rejects_dangling_internal_dependency(self) -> None:
        with self.assertRaisesRegex(VoyageError, "unknown internal dependencies"):
            self.event(
                "work.created",
                "W-2",
                actor="gov",
                loop="governance",
                payload={"title": "Dependent", "scope": "test", "acceptance": ["done"], "dependencies": ["W-MISSING"]},
            )
        self.event(
            "work.created",
            "W-2",
            actor="gov",
            loop="governance",
            payload={"title": "External", "scope": "test", "acceptance": ["done"], "dependencies": ["external:contract-v2"]},
        )
        self.assertEqual(current_state(self.paths)["works"]["W-2"]["dependencies"], ["external:contract-v2"])

    def test_executor_cannot_approve_own_delivery(self) -> None:
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.deliver()
        with self.assertRaisesRegex(VoyageError, "executor cannot issue final quality verdict"):
            self.event(
                "quality.passed",
                "W-1",
                actor="dev",
                loop="quality",
                anchor=self.anchor,
                evidence=[self.execution_evidence],
            )

    def test_quality_must_target_current_anchor(self) -> None:
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        current_anchor = typed_artifact_anchor(self.paths, name="current")
        stale_anchor = typed_artifact_anchor(self.paths, name="stale")
        self.deliver(anchor=current_anchor)
        with self.assertRaisesRegex(VoyageError, "quality anchor does not match"):
            self.event("quality.passed", "W-1", actor="qa", loop="quality", anchor=stale_anchor, evidence=[self.quality_evidence])

    def test_strict_work_requires_user_authorization(self) -> None:
        self.create_work(risk="strict")
        with self.assertRaisesRegex(VoyageError, "requires User authorization"):
            self.event("work.authorized", "W-1", actor="gov", loop="governance")
        with self.assertRaisesRegex(VoyageError, "recorded User decision"):
            self.event("work.authorized", "W-1", actor="gov", loop="governance", authorization="USER-1")
        self.event("decision.recorded", "USER-1", actor="user", loop="user", risk="strict", payload={"decision": "authorize W-1"})
        self.event("work.authorized", "W-1", actor="gov", loop="governance", authorization="USER-1")
        self.assertEqual(current_state(self.paths)["works"]["W-1"]["status"], "authorized")

    def test_awaiting_user_requires_recorded_decision_to_resume(self) -> None:
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.event("work.awaiting-user", "W-1", actor="gov", loop="governance", payload={"decision": "approve external write"})
        with self.assertRaisesRegex(VoyageError, "recorded User decision"):
            self.event("work.user-authorized", "W-1", actor="gov", loop="governance", authorization="USER-2")
        self.event("decision.recorded", "USER-2", actor="user", loop="user", risk="strict", payload={"decision": "approved"})
        self.event("work.user-authorized", "W-1", actor="gov", loop="governance", authorization="USER-2")
        self.assertEqual(current_state(self.paths)["works"]["W-1"]["status"], "authorized")

    def test_resource_claim_is_required_and_conflicts(self) -> None:
        register_resource(
            self.paths,
            actor="gov",
            resource_id="file:shared",
            resource_type="file",
            mode="exclusive",
            conflict_key="shared.txt",
        )
        self.create_work("W-1", resources=["file:shared"])
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        with self.assertRaisesRegex(VoyageError, "unclaimed resources"):
            self.event("work.started", "W-1", actor="dev", loop="execution")
        self.event(
            "resource.claimed",
            "file:shared",
            actor="dev",
            loop="execution",
            payload={"resource_id": "file:shared", "lease_id": "lease-1", "work_id": "W-1", "expires_at": "2099-01-01T00:00:00Z"},
        )
        self.event("work.started", "W-1", actor="dev", loop="execution")
        self.create_work("W-2")
        with self.assertRaisesRegex(VoyageError, "resource conflict"):
            self.event(
                "resource.claimed",
                "file:shared",
                actor="dev-2",
                loop="execution",
                payload={"resource_id": "file:shared", "lease_id": "lease-2", "work_id": "W-2", "expires_at": "2099-01-01T00:00:00Z"},
            )

    def test_stateful_resource_requires_probe_evidence(self) -> None:
        atomic_write_json(
            self.paths.resources,
            {
                "schema_version": "0.1.0",
                "resources": [{"id": "account:test", "type": "account", "mode": "serialized"}],
            },
        )
        self.create_work(resources=["account:test"])
        with self.assertRaisesRegex(VoyageError, "fresh probe evidence"):
            self.event(
                "resource.claimed",
                "account:test",
                actor="dev",
                loop="execution",
                payload={"resource_id": "account:test", "lease_id": "lease-a", "work_id": "W-1", "expires_at": "2099-01-01T00:00:00Z"},
            )

    def test_rule_separation_and_retirement(self) -> None:
        self.event(
            "rule.proposed",
            "R-1",
            actor="auditor",
            loop="audit",
            payload={"scope": "tests", "source": "incident-1", "cost": "low", "verification": "next delivery", "retirement": "risk removed"},
        )
        with self.assertRaisesRegex(VoyageError, "proposer cannot approve"):
            self.event("rule.approved", "R-1", actor="auditor", loop="governance")
        self.event("rule.approved", "R-1", actor="gov", loop="governance")
        self.event("rule.applied", "R-1", actor="operator", loop="governance", evidence=["diff:rule"])
        with self.assertRaisesRegex(VoyageError, "applier cannot verify"):
            self.event("rule.verified", "R-1", actor="operator", loop="quality", evidence=["test"])
        self.event("rule.verified", "R-1", actor="qa", loop="quality", evidence=["test:rule"])
        self.event("rule.retired", "R-1", actor="gov", loop="governance", evidence=["review:retirement"])
        self.assertEqual(current_state(self.paths)["rules"]["R-1"]["status"], "retired")

    def test_active_rule_can_be_superseded_by_verified_replacement(self) -> None:
        for rule_id, proposer, approver, applier, verifier in (
            ("R-1", "audit-1", "gov-1", "ops-1", "qa-1"),
            ("R-2", "audit-2", "gov-2", "ops-2", "qa-2"),
        ):
            self.event(
                "rule.proposed",
                rule_id,
                actor=proposer,
                loop="audit",
                payload={"scope": "tests", "source": "incident", "cost": "low", "verification": "delivery", "retirement": "replacement"},
            )
            self.event("rule.approved", rule_id, actor=approver, loop="governance")
            self.event("rule.applied", rule_id, actor=applier, loop="governance", evidence=[f"diff:{rule_id}"])
            self.event("rule.verified", rule_id, actor=verifier, loop="quality", evidence=[f"test:{rule_id}"])
        self.event("rule.superseded", "R-1", actor="gov-3", loop="governance", payload={"replacement": "R-2"}, evidence=["decision:replace"])
        rules = current_state(self.paths)["rules"]
        self.assertEqual(rules["R-1"]["status"], "superseded")
        self.assertEqual(rules["R-1"]["superseded_by"], "R-2")

    def test_audit_block_cannot_self_resolve(self) -> None:
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.event(
            "work.blocked",
            "W-1",
            actor="audit-1",
            loop="audit",
            evidence=["finding:1"],
            payload={"block_id": "B-1", "reason": "bad gate", "scope": "W-1", "unblock_condition": "replace gate", "appeal_to": "user"},
        )
        with self.assertRaisesRegex(VoyageError, "cannot resolve its own"):
            self.event("work.unblocked", "W-1", actor="audit-1", loop="audit", evidence=["claim:fixed"])
        self.event("work.unblocked", "W-1", actor="user", loop="user", evidence=["decision:appeal"])
        self.assertEqual(current_state(self.paths)["works"]["W-1"]["status"], "authorized")

    def test_gate_skip_blocks_acceptance(self) -> None:
        atomic_write_json(
            self.paths.gates,
            {
                "schema_version": "0.1.0",
                "gates": [
                    {"id": "independent-quality", "mandatory": True, "allow_skips": False, "required_loop": "quality"},
                    {"id": "e2e", "mandatory": True, "allow_skips": False, "required_loop": "quality"},
                ],
            },
        )
        self.create_work()
        self.event("work.authorized", "W-1", actor="gov", loop="governance")
        self.deliver()
        self.event(
            "gate.recorded",
            "W-1",
            actor="qa",
            loop="quality",
            anchor=self.anchor,
            evidence=[self.quality_evidence],
            payload={"gate_id": "e2e", "counts": {"total": 1, "passed": 0, "failed": 0, "skipped": 1, "unknown": 0}},
        )
        self.quality_pass()
        with self.assertRaisesRegex(VoyageError, "mandatory gate failed: e2e"):
            self.event("work.accepted", "W-1", actor="gov", loop="governance")

    def test_hash_tampering_is_detected(self) -> None:
        events = load_events(self.paths.ledger)
        events[0]["actor"] = "tampered"
        with self.paths.ledger.open("w", encoding="utf-8") as handle:
            for event in events:
                handle.write(json.dumps(event) + "\n")
        errors = validate_project(self.paths)
        self.assertTrue(any("hash mismatch" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
