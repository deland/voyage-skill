from __future__ import annotations

import inspect
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import voyage_skill.core as core

from tests.support import operational_project


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"
SKILL = REPOSITORY / "SKILL.md"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
GRAPH = REPOSITORY / "docs" / "system" / "graph.md"
FACT_BUCKETS = ("observed", "declared", "unknown", "conflicts")
FACT_FIELDS = {
    "subject", "claim", "source_event", "evidence_id", "evidence_kind",
    "verified_at", "freshness", "conclusion", "blocking_scope",
    "next_safe_action", "required_loop",
}


class RecoveryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "recovery-example")
        core.append_event(
            self.paths,
            actor="user",
            loop="user",
            event_type="decision.recorded",
            subject="USER-ENABLE-ENVIRONMENT-CONTROL",
            risk="standard",
            payload={
                "decision": "extension.enable",
                "scope": {
                    "actions": ["extension.enable"],
                    "project_id": "recovery-example",
                    "extensions": ["environment-control"],
                    "extension_versions": {"environment-control": "1.0.0"},
                },
            },
        )
        core.enable_extension(
            self.paths,
            actor="gov",
            extension_id="environment-control",
            version="1.0.0",
            decision_id="USER-ENABLE-ENVIRONMENT-CONTROL",
        )
        self.now = datetime.now(timezone.utc).replace(microsecond=0)

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
        )

    def recover(self, *, port_probe=lambda _port, _host="127.0.0.1": False) -> dict:
        parameters = inspect.signature(core.recovery_snapshot).parameters
        kwargs = {}
        if "now" in parameters:
            kwargs["now"] = self.now
        if "port_probe" in parameters:
            kwargs["port_probe"] = port_probe
        return core.recovery_snapshot(self.paths, **kwargs)

    def runtime_observation(
        self,
        *,
        subject: str = "environment:staging",
        environment_id: str = "staging",
        target_version: str = "v1",
        fields: dict | None = None,
        observed_at: datetime | None = None,
        max_age_seconds: int = 300,
    ) -> tuple[str, dict]:
        document = {
            "kind": "runtime-readback",
            "version": 1,
            "claim": "runtime-state",
            "locator": {
                "environment_id": environment_id,
                "target_version": target_version,
                "fields": fields or {"healthy": True},
                "max_age_seconds": max_age_seconds,
            },
            "observed_at": (observed_at or self.now - timedelta(seconds=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "producer": "probe",
        }
        result = core.record_evidence(self.paths, document, actor="probe")
        source = self.event(
            "environment.readback",
            subject,
            actor="probe",
            loop="execution",
            evidence=[result["evidence_id"]],
        )
        return result["evidence_id"], source

    def create_work(self, work_id: str = "W-1") -> None:
        self.event(
            "work.created",
            work_id,
            actor="gov",
            loop="governance",
            payload={"title": "Recovery fixture", "scope": "test", "acceptance": ["classified"]},
        )

    def register_port(self, resource_id: str = "port:test", port: int = 8401) -> None:
        core.register_resource(
            self.paths,
            actor="gov",
            resource_id=resource_id,
            resource_type="port",
            mode="exclusive",
            conflict_key=port,
        )

    def claim_resource(
        self,
        resource_id: str,
        *,
        lease_id: str = "lease-1",
        expires_at: datetime | None = None,
        evidence: list[str] | None = None,
    ) -> None:
        if "W-1" not in core.current_state(self.paths)["works"]:
            self.create_work()
        self.event(
            "resource.claimed",
            resource_id,
            actor="dev",
            loop="execution",
            payload={
                "resource_id": resource_id,
                "lease_id": lease_id,
                "work_id": "W-1",
                "expires_at": (expires_at or self.now + timedelta(hours=1)).isoformat(timespec="seconds").replace("+00:00", "Z"),
            },
            evidence=evidence,
        )

    def release_resource(self, resource_id: str, lease_id: str = "lease-1") -> None:
        self.event(
            "resource.released",
            resource_id,
            actor="dev",
            loop="execution",
            payload={"resource_id": resource_id, "lease_id": lease_id},
        )

    @staticmethod
    def all_facts(snapshot: dict) -> list[dict]:
        return [item for bucket in FACT_BUCKETS for item in snapshot[bucket]]


class RecoveryContractTests(RecoveryTestCase):
    def test_recovery_exposes_exact_fact_buckets_and_complete_item_contract(self) -> None:
        self.event("observation.recorded", "service:api", actor="dev", loop="execution", evidence=["legacy:self-report"])
        snapshot = self.recover()
        self.assertTrue(set(FACT_BUCKETS).issubset(snapshot))
        self.assertEqual(tuple(core.RECOVERY_FACT_BUCKETS), FACT_BUCKETS)
        self.assertEqual(set(core.RECOVERY_FACT_FIELDS), FACT_FIELDS)
        facts = self.all_facts(snapshot)
        self.assertTrue(facts)
        for item in facts:
            self.assertEqual(set(item), FACT_FIELDS)

    def test_recovery_preserves_existing_operational_context(self) -> None:
        self.create_work()
        snapshot = self.recover()
        for key in ("project_root", "project_stage", "bootstrap", "validated_at", "truth_registry", "ledger_head", "work", "active_leases", "active_blocks", "rules", "volatile_recheck_required"):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["work"][0]["id"], "W-1")

    def test_replayed_current_work_state_is_declared(self) -> None:
        self.create_work()
        snapshot = self.recover()
        item = next(
            item for item in snapshot["declared"]
            if item["subject"] == "W-1" and item["claim"] == "work.status:draft"
        )
        self.assertIsNotNone(item["source_event"])
        self.assertEqual(item["blocking_scope"], "work:W-1")
        self.assertEqual(item["next_safe_action"], core.NEXT_SAFE_ACTIONS["draft"])

    def test_recovery_fact_order_and_fixed_time_are_deterministic(self) -> None:
        self.assertIn("now", inspect.signature(core.recovery_snapshot).parameters)
        self.assertIn("port_probe", inspect.signature(core.recovery_snapshot).parameters)
        self.event("observation.recorded", "z", actor="dev", loop="execution", evidence=["legacy:z"])
        self.event("observation.recorded", "a", actor="dev", loop="execution", evidence=["legacy:a"])
        first = self.recover()
        second = self.recover()
        self.assertEqual(first["validated_at"], second["validated_at"])
        self.assertEqual({key: first[key] for key in FACT_BUCKETS}, {key: second[key] for key in FACT_BUCKETS})
        for bucket in FACT_BUCKETS:
            self.assertEqual(first[bucket], sorted(first[bucket], key=core.recovery_fact_sort_key))

    def test_recovery_is_read_only_and_does_not_append_events(self) -> None:
        self.runtime_observation()
        before = self.paths.ledger.read_bytes()
        head = core.current_state(self.paths)["last_event"]
        snapshot = self.recover()
        self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.assertEqual(snapshot["ledger_head"], head)


class EvidenceRecoveryTests(RecoveryTestCase):
    def test_valid_typed_evidence_is_observed_with_live_verification_metadata(self) -> None:
        evidence_id, source = self.runtime_observation()
        observed = [item for item in self.recover()["observed"] if item["evidence_id"] == evidence_id]
        self.assertEqual(len(observed), 1)
        item = observed[0]
        self.assertEqual(item["source_event"], source["event_id"])
        self.assertEqual(item["evidence_kind"], "runtime-readback")
        self.assertEqual(item["freshness"], "fresh")
        self.assertEqual(item["verified_at"], self.now.isoformat(timespec="seconds").replace("+00:00", "Z"))

    def test_expired_runtime_readback_is_unknown_not_observed(self) -> None:
        evidence_id, _ = self.runtime_observation(observed_at=self.now - timedelta(hours=2), max_age_seconds=60)
        snapshot = self.recover()
        self.assertFalse(any(item["evidence_id"] == evidence_id for item in snapshot["observed"]))
        item = next(item for item in snapshot["unknown"] if item["evidence_id"] == evidence_id)
        self.assertEqual(item["freshness"], "expired")
        self.assertIn("re-probe", item["next_safe_action"])

    def test_missing_or_tampered_typed_evidence_is_unknown(self) -> None:
        missing = "sha256:" + "a" * 64
        self.event("observation.recorded", "artifact:missing", actor="dev", loop="execution", evidence=[missing])
        snapshot = self.recover()
        item = next(item for item in snapshot["unknown"] if item["evidence_id"] == missing)
        self.assertIn(item["conclusion"], {"invalid", "unknown"})
        self.assertFalse(any(candidate["evidence_id"] == missing for candidate in snapshot["observed"]))

    def test_legacy_string_evidence_is_never_observed(self) -> None:
        legacy = "self-test-passed"
        self.event("observation.recorded", "service:legacy", actor="dev", loop="execution", evidence=[legacy])
        snapshot = self.recover()
        self.assertFalse(any(item["evidence_id"] == legacy for item in snapshot["observed"]))
        candidates = [item for bucket in ("declared", "unknown") for item in snapshot[bucket] if item["evidence_id"] == legacy]
        self.assertEqual(len(candidates), 1)
        self.assertIn("typed evidence", candidates[0]["next_safe_action"])


class ResourceRecoveryTests(RecoveryTestCase):
    def test_expired_active_lease_is_unknown_with_minimal_scope(self) -> None:
        self.register_port()
        self.claim_resource("port:test", expires_at=self.now - timedelta(seconds=1))
        item = next(item for item in self.recover()["unknown"] if item["claim"] == "resource.lease-active")
        self.assertEqual(item["blocking_scope"], "resource:port:test/lease:lease-1")
        self.assertIn("recover", item["next_safe_action"])

    def test_unprobed_stateful_resource_is_unknown(self) -> None:
        core.register_resource(self.paths, actor="gov", resource_id="account:ci", resource_type="account", mode="exclusive")
        self.claim_resource("account:ci", evidence=["legacy:login-ok"])
        item = next(item for item in self.recover()["unknown"] if item["subject"] == "account:ci")
        self.assertEqual(item["claim"], "resource.lease-active")
        self.assertIn("probe", item["next_safe_action"])

    def test_released_port_still_occupied_is_conflict(self) -> None:
        self.register_port(port=8401)
        self.claim_resource("port:test")
        self.release_resource("port:test")
        snapshot = self.recover(port_probe=lambda port, host="127.0.0.1": port == 8401)
        item = next(item for item in snapshot["conflicts"] if item["subject"] == "port:test")
        self.assertEqual(item["blocking_scope"], "resource:port:test")
        self.assertEqual(item["required_loop"], "governance")
        self.assertFalse(any(candidate["subject"] == "port:test" and candidate["claim"] == "resource.released" for candidate in snapshot["observed"]))

    def test_released_port_readback_free_is_observed_without_conflict(self) -> None:
        self.register_port(port=8401)
        self.claim_resource("port:test")
        self.release_resource("port:test")
        snapshot = self.recover(port_probe=lambda _port, _host="127.0.0.1": False)
        self.assertFalse(any(item["subject"] == "port:test" for item in snapshot["conflicts"]))
        item = next(item for item in snapshot["observed"] if item["subject"] == "port:test" and item["claim"] == "resource.released")
        self.assertEqual(item["evidence_kind"], "port-probe")
        self.assertEqual(item["conclusion"], "port-free")

    def test_probe_failure_is_unknown_not_conflict(self) -> None:
        self.register_port(port=8401)
        self.claim_resource("port:test")
        self.release_resource("port:test")

        def unavailable(_port: int, _host: str = "127.0.0.1") -> bool:
            raise OSError("probe unavailable")

        snapshot = self.recover(port_probe=unavailable)
        self.assertFalse(any(item["subject"] == "port:test" for item in snapshot["conflicts"]))
        item = next(item for item in snapshot["unknown"] if item["subject"] == "port:test")
        self.assertIn("probe", item["next_safe_action"])


class RuntimeConflictRecoveryTests(RecoveryTestCase):
    def test_contradictory_valid_runtime_fields_in_same_scope_conflict(self) -> None:
        first, _ = self.runtime_observation(fields={"healthy": True})
        second, _ = self.runtime_observation(fields={"healthy": False})
        snapshot = self.recover()
        conflicts = [item for item in snapshot["conflicts"] if item["claim"] == "runtime.field:healthy"]
        self.assertEqual(len(conflicts), 1)
        self.assertEqual(set(conflicts[0]["evidence_id"].split(",")), {first, second})

    def test_different_runtime_scopes_do_not_conflict(self) -> None:
        self.runtime_observation(subject="environment:a", environment_id="a", fields={"healthy": True})
        self.runtime_observation(subject="environment:b", environment_id="b", fields={"healthy": False})
        snapshot = self.recover()
        self.assertFalse(any(item["claim"] == "runtime.field:healthy" for item in snapshot["conflicts"]))
        subjects = {item["subject"] for item in snapshot["observed"] if item["evidence_kind"] == "runtime-readback"}
        self.assertTrue({"environment:a", "environment:b"}.issubset(subjects))

    def test_identical_runtime_observations_are_deduplicated_without_conflict(self) -> None:
        evidence_id, _ = self.runtime_observation(fields={"healthy": True})
        self.event("environment.readback", "environment:staging", actor="probe", loop="execution", evidence=[evidence_id])
        snapshot = self.recover()
        self.assertFalse(any(item["claim"] == "runtime.field:healthy" for item in snapshot["conflicts"]))
        observed = [item for item in snapshot["observed"] if item["evidence_id"] == evidence_id]
        self.assertEqual(len(observed), 1)

    def test_conflicted_observations_do_not_remain_in_observed_bucket(self) -> None:
        first, _ = self.runtime_observation(fields={"healthy": True})
        second, _ = self.runtime_observation(fields={"healthy": False})
        snapshot = self.recover()
        self.assertFalse(any(item["evidence_id"] in {first, second} for item in snapshot["observed"]))


class RecoveryCliAndDocsTests(RecoveryTestCase):
    def test_recover_cli_emits_four_bucket_json_and_is_repeatable_with_fixed_fixture(self) -> None:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "recover"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(set(FACT_BUCKETS).issubset(payload))
        for item in self.all_facts(payload):
            self.assertEqual(set(item), FACT_FIELDS)

    def test_skill_runbook_and_graph_define_same_recovery_contract(self) -> None:
        for path in (SKILL, RUNBOOK, GRAPH):
            text = path.read_text(encoding="utf-8")
            start = text.find("<!-- recovery-facts:start -->")
            end = text.find("<!-- recovery-facts:end -->")
            self.assertGreaterEqual(start, 0, msg=str(path))
            self.assertGreater(end, start, msg=str(path))
            contract = text[start:end]
            for value in (*FACT_BUCKETS, *FACT_FIELDS):
                self.assertIn(f"`{value}`", contract, msg=f"{path}: {value}")

    def test_dogfood_recovery_classifies_without_mutation(self) -> None:
        paths = core.project_paths(REPOSITORY)
        before = paths.ledger.read_bytes()
        snapshot = core.recovery_snapshot(paths)
        self.assertTrue(set(FACT_BUCKETS).issubset(snapshot))
        self.assertEqual(paths.ledger.read_bytes(), before)
        for item in self.all_facts(snapshot):
            self.assertEqual(set(item), FACT_FIELDS)

    def test_recovery_unknown_and_conflict_actions_name_required_permission(self) -> None:
        self.runtime_observation(observed_at=self.now - timedelta(hours=2), max_age_seconds=1)
        self.runtime_observation(fields={"healthy": True})
        self.runtime_observation(fields={"healthy": False})
        snapshot = self.recover()
        self.assertTrue(snapshot["unknown"])
        self.assertTrue(snapshot["conflicts"])
        for item in snapshot["unknown"] + snapshot["conflicts"]:
            self.assertTrue(item["next_safe_action"])
            self.assertIn(item["required_loop"], core.LOOPS)
            self.assertTrue(item["blocking_scope"])


if __name__ == "__main__":
    unittest.main()
