from __future__ import annotations

import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import voyage_skill.cli as cli
import voyage_skill.core as core

from tests.support import operational_project, typed_artifact_anchor, typed_command_evidence
from tests.test_contracts import schema_errors


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"
SKILL = REPOSITORY / "SKILL.md"
AUTHORITY = REPOSITORY / "docs" / "governance" / "authority.md"
GRAPH = REPOSITORY / "docs" / "system" / "graph.md"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
STRICT_DOMAINS = {
    "production", "persistent-data", "security", "credentials", "permissions",
    "material-cost", "public-external-write", "gate-relaxation", "irreversible",
}


class RiskPolicyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "risk-example")
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.anchor = typed_artifact_anchor(self.paths, name="risk-delivery")
        self.execution = typed_command_evidence(self.paths, name="risk-execution", producer="dev")
        self.quality = typed_command_evidence(self.paths, name="risk-quality", producer="qa")
        self.classification = typed_command_evidence(self.paths, name="risk-classification", producer="gov")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def event(
        self,
        event_type: str,
        subject: str,
        *,
        actor: str,
        loop: str,
        risk: str = "standard",
        payload: dict | None = None,
        evidence: list[str] | None = None,
        anchor: str | None = None,
        authorization: str | None = None,
    ) -> dict:
        return core.append_event(
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

    def runtime_readback(
        self,
        name: str,
        *,
        observed_at: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> str:
        result = core.record_evidence(
            self.paths,
            {
                "kind": "runtime-readback",
                "version": 1,
                "claim": f"runtime-{name}",
                "locator": {
                    "environment_id": "staging",
                    "target_version": name,
                    "fields": {"healthy": True, "version": name},
                    "max_age_seconds": max_age_seconds,
                },
                "observed_at": (observed_at or datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
                "producer": "probe",
            },
            actor="probe",
        )
        return result["evidence_id"]

    def create_work(
        self,
        work_id: str,
        *,
        risk: str = "standard",
        domains: list[str] | None = None,
        unknown: bool = False,
        disputed: bool = False,
        environment_change: bool = False,
        resources: list[str] | None = None,
        evidence: list[str] | None = None,
    ) -> dict:
        return self.event(
            "work.created",
            work_id,
            actor="gov",
            loop="governance",
            risk=risk,
            evidence=evidence,
            payload={
                "title": work_id,
                "scope": "risk policy test",
                "acceptance": ["policy satisfied"],
                "required_resources": resources or [],
                "risk_assessment": {
                    "version": 1,
                    "domains": domains or [],
                    "unknown": unknown,
                    "disputed": disputed,
                    "environment_change": environment_change,
                },
            },
        )

    def decision(
        self,
        decision_id: str,
        *,
        action: str,
        work_id: str,
        resources: list[str] | None = None,
        project_id: str = "risk-example",
        loop: str = "user",
    ) -> None:
        scope = {"actions": [action], "project_id": project_id, "works": [work_id]}
        if resources is not None:
            scope["resources"] = resources
        self.event(
            "decision.recorded",
            decision_id,
            actor="user",
            loop=loop,
            risk="strict",
            payload={"decision": action, "scope": scope},
        )

    def authorize(self, work_id: str, *, decision_id: str | None = None) -> None:
        state = core.current_state(self.paths)["works"][work_id]
        authorization = None
        if state["risk"] == "strict":
            authorization = decision_id or f"USER-AUTH-{work_id}"
            self.decision(authorization, action="work.authorize", work_id=work_id)
        self.event("work.authorized", work_id, actor="gov", loop="governance", authorization=authorization)

    def start(self, work_id: str, *, pre_readback: str | None = None) -> None:
        work = core.current_state(self.paths)["works"][work_id]
        authorization = None
        evidence: list[str] = []
        if work["risk"] == "strict":
            authorization = f"USER-START-{work_id}"
            self.decision(authorization, action="work.start", work_id=work_id)
            evidence = [pre_readback or self.runtime_readback(f"pre-{work_id}")]
        self.event(
            "work.started", work_id, actor="dev", loop="execution",
            evidence=evidence, authorization=authorization,
        )

    def deliver_and_quality(self, work_id: str) -> None:
        self.event(
            "work.delivered", work_id, actor="dev", loop="execution",
            anchor=self.anchor, evidence=[self.execution],
        )
        self.event(
            "quality.passed", work_id, actor="qa", loop="quality",
            anchor=self.anchor, evidence=[self.quality],
            payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )

    def audit(self, work_id: str, *, anchor: str | None = None, actor: str = "auditor") -> None:
        self.event(
            "audit.checked", work_id, actor=actor, loop="audit",
            anchor=anchor or self.anchor, evidence=[self.quality],
            payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )

    def add_gate(
        self,
        gate_id: str,
        *,
        mandatory: bool = False,
        risk_modes: list[str] | None = None,
        risk_domains: list[str] | None = None,
    ) -> None:
        data = core.load_json(self.paths.gates)
        gate = {"id": gate_id, "mandatory": mandatory, "allow_skips": False, "required_loop": "quality"}
        if risk_modes is not None:
            gate["risk_modes"] = risk_modes
        if risk_domains is not None:
            gate["risk_domains"] = risk_domains
        data["gates"].append(gate)
        core.atomic_write_json(self.paths.gates, data)

    def pass_gate(self, work_id: str, gate_id: str) -> None:
        self.event(
            "gate.recorded", work_id, actor="qa", loop="quality",
            anchor=self.anchor, evidence=[self.quality],
            payload={"gate_id": gate_id, "counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )

    def run_cli(self, *args: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, expected, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        return json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}


class RiskAssessmentTests(RiskPolicyTestCase):
    def test_invalid_requested_mode_is_rejected_atomically(self) -> None:
        before = self.paths.ledger.read_bytes()
        with self.assertRaisesRegex(core.VoyageError, "invalid risk"):
            self.create_work("W-INVALID", risk="unknown", evidence=[self.classification])
        self.assertEqual(self.paths.ledger.read_bytes(), before)

    def test_risk_policy_matrix_has_three_ordered_modes_and_kernel_invariants(self) -> None:
        self.assertEqual(tuple(core.RISK_MODE_ORDER), ("light", "standard", "strict"))
        self.assertEqual(core.RISK_POLICY_VERSION, 1)
        view = core.risk_policy_view()
        self.assertEqual(list(view["modes"]), ["light", "standard", "strict"])
        for mode in core.RISK_MODE_ORDER:
            controls = view["modes"][mode]
            self.assertTrue(controls["immutable_anchor"])
            self.assertTrue(controls["independent_quality"])
            self.assertTrue(controls["append_only_ledger"])
        json.dumps(view, sort_keys=True)

    def test_light_with_valid_typed_classification_evidence_remains_light(self) -> None:
        event = self.create_work("W-LIGHT", risk="light", evidence=[self.classification])
        work = core.current_state(self.paths)["works"]["W-LIGHT"]
        self.assertEqual(event["risk"], "light")
        self.assertEqual(work["declared_risk"], "light")
        self.assertEqual(work["risk"], "light")
        self.assertEqual(work["risk_assessment"]["reasons"], [])

    def test_light_without_valid_classification_evidence_escalates_to_standard(self) -> None:
        for work_id, evidence in (("W-NONE", []), ("W-LEGACY", ["self-report"])):
            with self.subTest(work_id=work_id):
                event = self.create_work(work_id, risk="light", evidence=evidence)
                self.assertEqual(event["risk"], "standard")
                assessment = core.current_state(self.paths)["works"][work_id]["risk_assessment"]
                self.assertEqual(assessment["requested"], "light")
                self.assertEqual(assessment["effective"], "standard")
                self.assertIn("missing-valid-classification-evidence", assessment["reasons"])

    def test_unknown_disputed_or_strict_domain_escalates_to_strict(self) -> None:
        cases = [("unknown", [], True, False), ("disputed", [], False, True)]
        cases.extend((domain, [domain], False, False) for domain in sorted(STRICT_DOMAINS))
        for label, domains, unknown, disputed in cases:
            with self.subTest(case=label):
                work_id = f"W-{label}"
                self.create_work(
                    work_id, risk="standard", domains=domains,
                    unknown=unknown, disputed=disputed, evidence=[self.classification],
                )
                work = core.current_state(self.paths)["works"][work_id]
                self.assertEqual(work["risk"], "strict")
                self.assertTrue(work["risk_assessment"]["reasons"])

    def test_resource_risk_and_requested_mode_are_monotonic(self) -> None:
        core.register_resource(self.paths, actor="gov", resource_id="file:standard", resource_type="file", mode="rebuildable", risk="standard")
        core.register_resource(self.paths, actor="gov", resource_id="account:strict", resource_type="account", mode="serialized", risk="strict")
        self.create_work("W-STANDARD", risk="light", resources=["file:standard"], evidence=[self.classification])
        self.create_work("W-STRICT", risk="light", resources=["account:strict"], evidence=[self.classification])
        self.create_work("W-REQUESTED", risk="strict", evidence=[self.classification])
        state = core.current_state(self.paths)["works"]
        self.assertEqual(state["W-STANDARD"]["risk"], "standard")
        self.assertEqual(state["W-STRICT"]["risk"], "strict")
        self.assertEqual(state["W-REQUESTED"]["risk"], "strict")

    def test_risk_assessment_is_canonical_in_event_state_status_and_recovery(self) -> None:
        event = self.create_work("W-CANON", risk="light", evidence=[])
        assessment = event["payload"]["risk_assessment"]
        self.assertEqual(core.current_state(self.paths)["works"]["W-CANON"]["risk_assessment"], assessment)
        self.assertEqual(core.risk_status(self.paths, "W-CANON")["assessment"], assessment)
        recovered = next(item for item in core.recovery_snapshot(self.paths)["work"] if item["id"] == "W-CANON")
        self.assertEqual(recovered["risk_assessment"], assessment)


class RiskGateTests(RiskPolicyTestCase):
    def _ready(self, work_id: str, *, risk: str, domains: list[str] | None = None) -> list[str]:
        self.create_work(work_id, risk=risk, domains=domains, evidence=[self.classification])
        self.authorize(work_id)
        self.start(work_id)
        self.deliver_and_quality(work_id)
        if core.current_state(self.paths)["works"][work_id]["risk"] == "strict":
            self.audit(work_id)
            return [self.runtime_readback(f"post-{work_id}")]
        return []

    def test_all_modes_keep_immutable_anchor_and_independent_quality(self) -> None:
        for mode in ("light", "standard", "strict"):
            with self.subTest(mode=mode):
                work_id = f"W-{mode}"
                self.create_work(work_id, risk=mode, evidence=[self.classification])
                self.authorize(work_id)
                self.start(work_id)
                with self.assertRaises(core.VoyageError):
                    self.event("work.delivered", work_id, actor="dev", loop="execution", evidence=[self.execution])

    def test_mandatory_gate_applies_to_every_mode(self) -> None:
        self.add_gate("slow-loop", mandatory=True)
        for mode in ("light", "standard", "strict"):
            with self.subTest(mode=mode):
                work_id = f"W-MAND-{mode}"
                evidence = self._ready(work_id, risk=mode)
                with self.assertRaisesRegex(core.VoyageError, "mandatory gate missing"):
                    self.event("work.accepted", work_id, actor="gov", loop="governance", evidence=evidence)

    def test_mode_gate_applies_only_to_named_modes(self) -> None:
        self.add_gate("standard-review", risk_modes=["standard", "strict"])
        light_evidence = self._ready("W-L", risk="light")
        self.event("work.accepted", "W-L", actor="gov", loop="governance", evidence=light_evidence)
        for mode in ("standard", "strict"):
            work_id = f"W-{mode}"
            evidence = self._ready(work_id, risk=mode)
            with self.assertRaisesRegex(core.VoyageError, "required gate missing"):
                self.event("work.accepted", work_id, actor="gov", loop="governance", evidence=evidence)

    def test_strict_domain_gate_applies_only_to_matching_domain(self) -> None:
        self.add_gate("security-review", risk_domains=["security"])
        matching = self._ready("W-SEC", risk="standard", domains=["security"])
        with self.assertRaisesRegex(core.VoyageError, "required gate missing"):
            self.event("work.accepted", "W-SEC", actor="gov", loop="governance", evidence=matching)
        other = self._ready("W-PROD", risk="standard", domains=["production"])
        self.event("work.accepted", "W-PROD", actor="gov", loop="governance", evidence=other)

    def test_gate_policy_fields_are_schema_and_runtime_validated(self) -> None:
        valid = core.load_json(self.paths.gates)
        valid["gates"].append({
            "id": "risk-review", "mandatory": False, "allow_skips": False,
            "required_loop": "quality", "risk_modes": ["standard", "strict"],
            "risk_domains": ["security"],
        })
        self.assertEqual(schema_errors("gates", valid), [])
        for field, value in (("risk_modes", ["unknown"]), ("risk_domains", ["unknown"]), ("risk_modes", ["strict", "strict"])):
            damaged = json.loads(json.dumps(valid))
            damaged["gates"][-1][field] = value
            self.assertTrue(schema_errors("gates", damaged), (field, value))
            self.assertTrue(core._validate_gate_definition_data(damaged), (field, value))


class StrictControlTests(RiskPolicyTestCase):
    def test_strict_authorize_requires_exact_user_decision_scope(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        cases = [
            ("wrong-project", "work.authorize", "W-STRICT", "other"),
            ("wrong-work", "work.authorize", "W-OTHER", "risk-example"),
            ("wrong-action", "work.start", "W-STRICT", "risk-example"),
        ]
        for decision_id, action, work_id, project_id in cases:
            self.decision(decision_id, action=action, work_id=work_id, project_id=project_id)
            before = self.paths.ledger.read_bytes()
            with self.assertRaises(core.VoyageError):
                self.event("work.authorized", "W-STRICT", actor="gov", loop="governance", authorization=decision_id)
            self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.decision("revoked", action="work.authorize", work_id="W-STRICT")
        self.event("decision.revoked", "revoked", actor="user", loop="user", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            self.event("work.authorized", "W-STRICT", actor="gov", loop="governance", authorization="revoked")

    def test_strict_start_requires_separate_exact_action_decision(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT", decision_id="USER-AUTH")
        pre = self.runtime_readback("pre")
        with self.assertRaises(core.VoyageError):
            self.event("work.started", "W-STRICT", actor="dev", loop="execution", authorization="USER-AUTH", evidence=[pre])
        self.decision("USER-START", action="work.start", work_id="W-STRICT")
        event = self.event("work.started", "W-STRICT", actor="dev", loop="execution", authorization="USER-START", evidence=[pre])
        self.assertEqual(core.current_state(self.paths)["works"]["W-STRICT"]["start_authorization"], "USER-START")
        self.assertEqual(event["authorization"], "USER-START")

    def test_strict_start_rejects_missing_invalid_expired_or_wrong_kind_readback(self) -> None:
        cases = {
            "missing": [],
            "legacy": ["self-report"],
            "wrong-kind": [self.execution],
            "expired": [self.runtime_readback("expired", observed_at=self.now - timedelta(hours=2), max_age_seconds=1)],
        }
        for label, evidence in cases.items():
            with self.subTest(case=label):
                work_id = f"W-{label}"
                self.create_work(work_id, risk="strict", evidence=[self.classification])
                self.authorize(work_id)
                decision_id = f"USER-START-{label}"
                self.decision(decision_id, action="work.start", work_id=work_id)
                with self.assertRaises(core.VoyageError):
                    self.event("work.started", work_id, actor="dev", loop="execution", authorization=decision_id, evidence=evidence)

    def test_strict_start_accepts_fresh_runtime_readback(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT")
        pre = self.runtime_readback("pre")
        self.start("W-STRICT", pre_readback=pre)
        work = core.current_state(self.paths)["works"]["W-STRICT"]
        self.assertEqual(work["status"], "active")
        self.assertEqual(work["pre_readback"], pre)

    def test_strict_accept_requires_fresh_post_action_readback(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT")
        pre = self.runtime_readback("pre")
        self.start("W-STRICT", pre_readback=pre)
        self.deliver_and_quality("W-STRICT")
        self.audit("W-STRICT")
        with self.assertRaises(core.VoyageError):
            self.event("work.accepted", "W-STRICT", actor="gov", loop="governance", evidence=[pre])
        post = self.runtime_readback("post")
        self.event("work.accepted", "W-STRICT", actor="gov", loop="governance", evidence=[post])
        self.assertEqual(core.current_state(self.paths)["works"]["W-STRICT"]["post_readback"], post)

    def test_environment_change_requires_post_readback_in_light_and_standard(self) -> None:
        for mode in ("light", "standard"):
            work_id = f"W-ENV-{mode}"
            self.create_work(work_id, risk=mode, environment_change=True, evidence=[self.classification])
            self.authorize(work_id)
            self.start(work_id)
            self.deliver_and_quality(work_id)
            with self.assertRaisesRegex(core.VoyageError, "runtime readback"):
                self.event("work.accepted", work_id, actor="gov", loop="governance")
            self.event("work.accepted", work_id, actor="gov", loop="governance", evidence=[self.runtime_readback(f"post-{mode}")])
        self.create_work("W-NORMAL", risk="standard", evidence=[self.classification])
        self.authorize("W-NORMAL")
        self.start("W-NORMAL")
        self.deliver_and_quality("W-NORMAL")
        self.event("work.accepted", "W-NORMAL", actor="gov", loop="governance")


class ResourceAndAuditPolicyTests(RiskPolicyTestCase):
    def _resource_work(self, work_id: str, *, risk: str, mode: str, resource_risk: str = "light") -> str:
        resource_id = f"file:{work_id}"
        core.register_resource(self.paths, actor="gov", resource_id=resource_id, resource_type="file", mode=mode, risk=resource_risk)
        self.create_work(work_id, risk=risk, resources=[resource_id], evidence=[self.classification])
        self.authorize(work_id)
        return resource_id

    def test_light_probes_conflict_resources_but_not_rebuildable_nonconflict_resources(self) -> None:
        conflict = self._resource_work("W-CONFLICT", risk="light", mode="exclusive")
        with self.assertRaisesRegex(core.VoyageError, "probe"):
            self.event("resource.claimed", conflict, actor="dev", loop="execution", payload={"resource_id": conflict, "lease_id": "L-1", "work_id": "W-CONFLICT", "expires_at": "2099-01-01T00:00:00Z"})
        rebuildable = self._resource_work("W-REBUILD", risk="light", mode="rebuildable")
        self.event("resource.claimed", rebuildable, actor="dev", loop="execution", payload={"resource_id": rebuildable, "lease_id": "L-2", "work_id": "W-REBUILD", "expires_at": "2099-01-01T00:00:00Z"})

    def test_standard_claim_requires_valid_typed_probe_for_every_resource(self) -> None:
        resource_id = self._resource_work("W-STANDARD", risk="standard", mode="rebuildable")
        for evidence in ([], ["self-report"]):
            with self.assertRaisesRegex(core.VoyageError, "typed probe"):
                self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=evidence, payload={"resource_id": resource_id, "lease_id": f"L-{len(evidence)}", "work_id": "W-STANDARD", "expires_at": "2099-01-01T00:00:00Z"})
        self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=[self.execution], payload={"resource_id": resource_id, "lease_id": "L-OK", "work_id": "W-STANDARD", "expires_at": "2099-01-01T00:00:00Z"})

    def test_strict_claim_requires_probe_and_exact_user_scope(self) -> None:
        resource_id = self._resource_work("W-STRICT", risk="strict", mode="serialized", resource_risk="strict")
        payload = {"resource_id": resource_id, "lease_id": "L-STRICT", "work_id": "W-STRICT", "expires_at": "2099-01-01T00:00:00Z"}
        self.decision("USER-WRONG", action="resource.claim", work_id="W-STRICT", resources=["file:other"])
        with self.assertRaises(core.VoyageError):
            self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=[self.execution], authorization="USER-WRONG", payload=payload)
        self.decision("USER-CLAIM", action="resource.claim", work_id="W-STRICT", resources=[resource_id])
        self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=[self.execution], authorization="USER-CLAIM", payload=payload)

    def test_lease_retains_probe_evidence_and_recovery_exposes_it(self) -> None:
        resource_id = self._resource_work("W-STANDARD", risk="standard", mode="rebuildable")
        self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=[self.execution], payload={"resource_id": resource_id, "lease_id": "L-1", "work_id": "W-STANDARD", "expires_at": "2099-01-01T00:00:00Z"})
        lease = core.current_state(self.paths)["leases"]["L-1"]
        self.assertEqual(lease["probe_evidence"], [self.execution])
        recovered = next(item for item in core.recovery_snapshot(self.paths)["active_leases"] if item["lease_id"] == "L-1")
        self.assertEqual(recovered["probe_evidence"], [self.execution])

    def test_strict_accept_requires_independent_audit_checkpoint_on_current_anchor(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT")
        self.start("W-STRICT")
        self.deliver_and_quality("W-STRICT")
        post = self.runtime_readback("post")
        with self.assertRaisesRegex(core.VoyageError, "audit checkpoint"):
            self.event("work.accepted", "W-STRICT", actor="gov", loop="governance", evidence=[post])
        with self.assertRaisesRegex(core.VoyageError, "executor"):
            self.audit("W-STRICT", actor="dev")
        stale = typed_artifact_anchor(self.paths, name="stale-audit")
        with self.assertRaisesRegex(core.VoyageError, "anchor"):
            self.audit("W-STRICT", anchor=stale)
        self.audit("W-STRICT")
        self.event("work.accepted", "W-STRICT", actor="gov", loop="governance", evidence=[post])

    def test_strict_accept_revalidates_current_audit_checkpoint_evidence(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT")
        self.start("W-STRICT")
        self.deliver_and_quality("W-STRICT")
        audit_evidence = typed_command_evidence(self.paths, name="risk-audit", producer="auditor")
        self.event(
            "audit.checked", "W-STRICT", actor="auditor", loop="audit",
            anchor=self.anchor, evidence=[audit_evidence],
            payload={"counts": {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}},
        )
        evidence_path = self.paths.evidence / "sha256" / f"{audit_evidence.removeprefix('sha256:')}.json"
        evidence_path.write_text("{}\n", encoding="utf-8")
        with self.assertRaisesRegex(core.VoyageError, "audit checkpoint evidence"):
            self.event(
                "work.accepted", "W-STRICT", actor="gov", loop="governance",
                evidence=[self.runtime_readback("post")],
            )


class RiskCliRecoveryTests(RiskPolicyTestCase):
    def test_risk_cli_policy_and_status_emit_stable_json(self) -> None:
        self.create_work("W-1", risk="light", evidence=[])
        policy = self.run_cli("risk", "policy")
        status = self.run_cli("risk", "status", "W-1")
        self.assertEqual(policy, core.risk_policy_view())
        self.assertEqual(status, core.risk_status(self.paths, "W-1"))
        self.assertEqual(status["effective"], "standard")

    def test_work_cli_risk_inputs_drive_automatic_escalation(self) -> None:
        result = self.run_cli(
            "work", "create", "W-CLI", "--title", "CLI", "--scope", "test",
            "--acceptance", "safe", "--risk", "light", "--risk-domain", "security",
            "--risk-unknown", "--environment-change", "--evidence", self.classification,
            "--actor", "gov",
        )
        self.assertEqual(result["type"], "work.created")
        work = core.current_state(self.paths)["works"]["W-CLI"]
        self.assertEqual(work["risk"], "strict")
        self.assertTrue(work["risk_assessment"]["unknown"])
        self.assertTrue(work["risk_assessment"]["environment_change"])

    def test_strict_cli_round_trip_enforces_authorize_start_claim_audit_accept(self) -> None:
        parser = cli.build_parser()
        start = parser.parse_args(["work", "start", "W", "--authorization", "USER", "--evidence", "sha256:" + "0" * 64, "--actor", "dev"])
        claim = parser.parse_args(["resource", "claim", "R", "--work", "W", "--authorization", "USER", "--evidence", "sha256:" + "0" * 64, "--actor", "dev"])
        audit = parser.parse_args(["audit", "check", "W", "--anchor", "sha256:" + "0" * 64, "--evidence", "sha256:" + "1" * 64, "--actor", "auditor"])
        accept = parser.parse_args(["work", "accept", "W", "--evidence", "sha256:" + "2" * 64, "--actor", "gov"])
        self.assertEqual((start.authorization, claim.authorization, audit.audit_command, accept.work_command), ("USER", "USER", "check", "accept"))

    def test_audit_checked_matches_runtime_schema_cli_and_replay_sets(self) -> None:
        self.assertIn("audit.checked", core.SUPPORTED_EVENT_TYPES)
        self.assertIn("audit.checked", cli.CLI_EVENT_TYPES)
        self.assertIn("audit.checked", core.load_json(REPOSITORY / "schemas" / "event.schema.json")["properties"]["type"]["enum"])
        source = inspect.getsource(core.replay_events)
        self.assertIn('event_type == "audit.checked"', source)
        instance = core.make_event(None, actor="auditor", loop="audit", event_type="audit.checked", subject="W", risk="strict", payload={})
        self.assertEqual(schema_errors("event", instance), [])

    def test_failed_policy_transition_is_atomic(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        before = self.paths.ledger.read_bytes()
        head = core.current_state(self.paths)["last_event"]
        with self.assertRaises(core.VoyageError):
            self.event("work.authorized", "W-STRICT", actor="gov", loop="governance")
        self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.assertEqual(core.current_state(self.paths)["last_event"], head)

    def test_recovery_reports_effective_risk_requirements_and_probe_refs(self) -> None:
        resource_id = "file:recovery"
        core.register_resource(self.paths, actor="gov", resource_id=resource_id, resource_type="file", mode="rebuildable")
        self.create_work("W-1", risk="standard", resources=[resource_id], evidence=[self.classification])
        self.authorize("W-1")
        self.event("resource.claimed", resource_id, actor="dev", loop="execution", evidence=[self.execution], payload={"resource_id": resource_id, "lease_id": "L-1", "work_id": "W-1", "expires_at": "2099-01-01T00:00:00Z"})
        snapshot = core.recovery_snapshot(self.paths)
        self.assertEqual(snapshot["risk_policy"], core.risk_policy_view())
        work = next(item for item in snapshot["work"] if item["id"] == "W-1")
        self.assertEqual(work["effective_risk"], "standard")
        self.assertIn("requirements", work)
        self.assertEqual(snapshot["active_leases"][0]["probe_evidence"], [self.execution])

    def test_risk_status_names_missing_strict_controls(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.assertIn("user-decision:work.authorize", core.risk_status(self.paths, "W-STRICT")["missing_controls"])
        self.authorize("W-STRICT")
        missing = core.risk_status(self.paths, "W-STRICT")["missing_controls"]
        self.assertIn("user-decision:work.start", missing)
        self.assertIn("runtime-readback:pre-action", missing)
        self.start("W-STRICT")
        self.deliver_and_quality("W-STRICT")
        missing = core.risk_status(self.paths, "W-STRICT")["missing_controls"]
        self.assertIn("audit.checked:current-anchor", missing)
        self.assertIn("runtime-readback:post-action", missing)

    def test_validate_rechecks_policy_evidence_kind_at_action_time(self) -> None:
        self.create_work("W-STRICT", risk="strict", evidence=[self.classification])
        self.authorize("W-STRICT")
        self.start("W-STRICT")
        events = core.load_events(self.paths.ledger)
        for event in events:
            if event["type"] == "work.started" and event["subject"] == "W-STRICT":
                event["evidence"] = [self.execution]
            previous = events[events.index(event) - 1]["hash"] if events.index(event) else None
            event["prev_hash"] = previous
            event["hash"] = core.content_hash({key: value for key, value in event.items() if key != "hash"})
        self.paths.ledger.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")
        errors = core.validate_project(self.paths)
        self.assertTrue(any("runtime-readback" in error and "work.started" in error for error in errors), errors)

    def test_validate_rechecks_light_classification_evidence_at_event_time(self) -> None:
        self.create_work("W-LIGHT", risk="light", evidence=[self.classification])
        events = core.load_events(self.paths.ledger)
        for event in events:
            if event["type"] == "work.created" and event["subject"] == "W-LIGHT":
                event["evidence"] = ["declared:low-risk"]
            previous = events[events.index(event) - 1]["hash"] if events.index(event) else None
            event["prev_hash"] = previous
            event["hash"] = core.content_hash({key: value for key, value in event.items() if key != "hash"})
        self.paths.ledger.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")
        errors = core.validate_project(self.paths)
        self.assertTrue(any("work.created" in error and "classification evidence" in error for error in errors), errors)


class RiskDocsLegacyTests(RiskPolicyTestCase):
    def test_authority_documents_exact_executable_policy_matrix(self) -> None:
        text = AUTHORITY.read_text(encoding="utf-8")
        section = text[text.index("<!-- executable-risk-policy:start -->"):text.index("<!-- executable-risk-policy:end -->")]
        for mode in core.RISK_MODE_ORDER:
            self.assertIn(f"`{mode}`", section)
        for domain in core.STRICT_RISK_DOMAINS:
            self.assertIn(f"`{domain}`", section)

    def test_system_and_runbook_document_assessment_scopes_and_checkpoints(self) -> None:
        for path, start, end in (
            (GRAPH, "<!-- risk-enforcement:start -->", "<!-- risk-enforcement:end -->"),
            (RUNBOOK, "<!-- risk-operations:start -->", "<!-- risk-operations:end -->"),
        ):
            text = path.read_text(encoding="utf-8")
            section = text[text.index(start):text.index(end)]
            for phrase in ("risk_assessment", "work.authorize", "work.start", "resource.claim", "runtime-readback", "audit.checked", "legacy"):
                self.assertIn(phrase, section)

    def test_skill_preserves_kernel_and_loads_risk_detail_progressively(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        section = text[text.index("<!-- risk-loading:start -->"):text.index("<!-- risk-loading:end -->")]
        for phrase in ("risk policy", "active governance", "immutable", "independent quality", "only"):
            self.assertIn(phrase, section.lower())

    def test_cli_reference_contains_risk_and_audit_leaf_commands(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        reference = text[text.index("<!-- voyage-cli-reference:start -->"):text.index("<!-- voyage-cli-reference:end -->")]
        for command in ("voyage risk policy", "voyage risk status", "voyage audit check"):
            self.assertEqual(reference.count(f"`{command}`"), 1)

    def test_legacy_work_without_policy_marker_replays_historical_behavior(self) -> None:
        self.event("work.created", "W-LEGACY", actor="gov", loop="governance", risk="strict", payload={"title": "Legacy", "scope": "test", "acceptance": ["old"]})
        events = core.load_events(self.paths.ledger)
        for event in events:
            if event["type"] == "work.created" and event["subject"] == "W-LEGACY":
                event["payload"].pop("risk_assessment", None)
            previous = events[events.index(event) - 1]["hash"] if events.index(event) else None
            event["prev_hash"] = previous
            event["hash"] = core.content_hash({key: value for key, value in event.items() if key != "hash"})
        self.paths.ledger.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")
        self.event("decision.recorded", "USER-LEGACY", actor="user", loop="user", risk="strict", payload={"decision": "legacy authorize"})
        self.event("work.authorized", "W-LEGACY", actor="gov", loop="governance", authorization="USER-LEGACY")
        self.event("work.started", "W-LEGACY", actor="dev", loop="execution")
        self.assertEqual(core.current_state(self.paths)["works"]["W-LEGACY"]["status"], "active")

    def test_dogfood_project_remains_valid_recoverable_and_policy_visible(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.validate_project(paths), [])
        snapshot = core.recovery_snapshot(paths)
        self.assertEqual(snapshot["risk_policy"], core.risk_policy_view())
        self.assertEqual(snapshot["work"], [])


if __name__ == "__main__":
    unittest.main()
