from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from pathlib import Path

import voyage_skill.core as core

from tests.support import operational_project, record_scoped_decision, reviewed_contracts


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"


def timestamp(delta: timedelta = timedelta()) -> str:
    return (datetime.now(timezone.utc) + delta).isoformat(timespec="seconds").replace("+00:00", "Z")


def evidence_document(kind: str, locator: dict, *, claim: str = "test-observation", observed_at: str | None = None) -> dict:
    return {
        "kind": kind,
        "version": 1,
        "claim": claim,
        "locator": locator,
        "observed_at": observed_at or timestamp(),
        "producer": "tester",
    }


class EvidenceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "evidence-example")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initialize_git(self) -> str:
        subprocess.run(["git", "init", "-q", str(self.root)], check=True)
        subprocess.run(["git", "-C", str(self.root), "add", "."], check=True)
        subprocess.run(
            ["git", "-C", str(self.root), "-c", "user.name=Voyage Test", "-c", "user.email=voyage@example.invalid", "commit", "-qm", "fixture"],
            check=True,
        )
        return subprocess.run(
            ["git", "-C", str(self.root), "rev-parse", "HEAD"],
            check=True,
            text=True,
            capture_output=True,
        ).stdout.strip()

    def raw_artifact(self, relative: str, content: bytes) -> dict:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return {"path": relative, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}

    def command_document(self, *, producer: str = "tester", passed: bool = True) -> dict:
        stdout = self.raw_artifact("artifacts/stdout.txt", b"98 passed\n")
        stderr = self.raw_artifact("artifacts/stderr.txt", b"")
        failed = 0 if passed else 1
        counts = {"total": 1, "passed": 1 if passed else 0, "failed": failed, "skipped": 0, "unknown": 0}
        document = evidence_document(
            "command-result",
            {
                "argv": ["python3", "-m", "unittest"],
                "cwd": ".",
                "exit_code": 0 if passed else 1,
                "stdout": stdout,
                "stderr": stderr,
                "counts": counts,
            },
            claim="command-passed" if passed else "command-failed",
        )
        document["producer"] = producer
        return document

    def git_document(self, revision: str, repository: str = ".") -> dict:
        return evidence_document(
            "git-commit",
            {"repository": repository, "revision": revision},
            claim="delivery-source",
        )

    def record(self, document: dict, actor: str = "tester") -> dict:
        return core.record_evidence(self.paths, document, actor=actor)

    def prepare_work(self, work_id: str = "W-1") -> None:
        core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject=work_id,
            risk="standard",
            payload={"title": "Typed evidence", "scope": "test", "acceptance": ["verified"]},
        )
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject=work_id, risk="standard")
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.started", subject=work_id, risk="standard")


class EvidenceStorageTests(EvidenceTestCase):
    def test_evidence_is_stored_by_canonical_sha256_and_deduplicated(self) -> None:
        document = evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300})
        first = self.record(document)
        second = self.record(document)
        expected = hashlib.sha256(core.canonical_json(document).encode("utf-8")).hexdigest()
        self.assertEqual(first["evidence_id"], f"sha256:{expected}")
        self.assertEqual(second["evidence_id"], first["evidence_id"])
        self.assertEqual(len(list((self.paths.evidence / "sha256").glob("*.json"))), 1)

    def test_tampered_evidence_document_is_rejected_by_digest_readback(self) -> None:
        recorded = self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}))
        digest = recorded["evidence_id"].split(":", 1)[1]
        stored = self.paths.evidence / "sha256" / f"{digest}.json"
        body = json.loads(stored.read_text(encoding="utf-8"))
        body["claim"] = "tampered"
        stored.write_text(json.dumps(body), encoding="utf-8")
        result = core.verify_evidence(self.paths, recorded["evidence_id"])
        self.assertEqual(result["status"], "invalid")
        self.assertTrue(any("digest" in reason for reason in result["reasons"]))

    def test_evidence_requires_versioned_common_fields(self) -> None:
        valid = evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300})
        for field in ("kind", "version", "claim", "locator", "observed_at", "producer"):
            with self.subTest(field=field):
                invalid = deepcopy(valid)
                invalid.pop(field)
                with self.assertRaisesRegex(core.VoyageError, field):
                    self.record(invalid)
        invalid = deepcopy(valid)
        invalid["version"] = "1"
        with self.assertRaisesRegex(core.VoyageError, "version"):
            self.record(invalid)

    def test_evidence_verification_appends_versioned_ledger_record(self) -> None:
        result = self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}))
        event = core.load_events(self.paths.ledger)[-1]
        self.assertEqual(event["type"], "evidence.verified")
        self.assertEqual(event["subject"], result["evidence_id"])
        self.assertEqual(event["payload"]["validator_version"], 1)
        self.assertEqual(event["payload"]["status"], "valid")
        self.assertIn("verified_at", event["payload"])
        self.assertIsInstance(event["payload"]["reasons"], list)


class GitCommitEvidenceTests(EvidenceTestCase):
    def test_git_commit_accepts_existing_full_commit_sha(self) -> None:
        revision = self.initialize_git()
        result = self.record(self.git_document(revision))
        self.assertEqual(result["status"], "valid")

    def test_git_commit_rejects_short_or_missing_revision(self) -> None:
        revision = self.initialize_git()
        self.assertEqual(self.record(self.git_document(revision[:8]))["status"], "invalid")
        self.assertEqual(self.record(self.git_document("f" * 40))["status"], "invalid")

    def test_git_commit_rejects_repository_escape_or_non_repository(self) -> None:
        revision = self.initialize_git()
        self.assertEqual(self.record(self.git_document(revision, "../outside"))["status"], "invalid")
        (self.root / "plain").mkdir()
        self.assertEqual(self.record(self.git_document(revision, "plain"))["status"], "invalid")

    def test_new_delivery_rejects_legacy_or_nonexistent_commit_anchor(self) -> None:
        self.initialize_git()
        evidence_id = self.record(self.command_document())["evidence_id"]
        self.prepare_work()
        with self.assertRaisesRegex(core.VoyageError, "typed evidence ID"):
            core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor="commit:abc", evidence=[evidence_id])
        bad_anchor = self.record(self.git_document("f" * 40))["evidence_id"]
        with self.assertRaisesRegex(core.VoyageError, "anchor.*invalid"):
            core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=bad_anchor, evidence=[evidence_id])


class ArtifactDigestEvidenceTests(EvidenceTestCase):
    def artifact_document(self, path: str, digest: str, algorithm: str = "sha256") -> dict:
        return evidence_document("artifact-digest", {"path": path, "algorithm": algorithm, "digest": digest}, claim="delivery-artifact")

    def test_artifact_digest_recomputes_sha256(self) -> None:
        content = b"immutable artifact\n"
        (self.root / "artifact.bin").write_bytes(content)
        result = self.record(self.artifact_document("artifact.bin", hashlib.sha256(content).hexdigest()))
        self.assertEqual(result["status"], "valid")

    def test_artifact_digest_detects_changed_artifact(self) -> None:
        target = self.root / "artifact.bin"
        target.write_bytes(b"v1")
        result = self.record(self.artifact_document("artifact.bin", hashlib.sha256(b"v1").hexdigest()))
        target.write_bytes(b"v2")
        self.assertEqual(core.verify_evidence(self.paths, result["evidence_id"])["status"], "invalid")

    def test_artifact_digest_rejects_escape_directory_and_unsupported_algorithm(self) -> None:
        (self.root / "folder").mkdir()
        for document in (
            self.artifact_document("../outside", "0" * 64),
            self.artifact_document("folder", "0" * 64),
            self.artifact_document("missing", "0" * 64, algorithm="md5"),
        ):
            with self.subTest(locator=document["locator"]):
                self.assertEqual(self.record(document)["status"], "invalid")


class CommandResultEvidenceTests(EvidenceTestCase):
    def test_command_result_requires_argv_cwd_exit_code_counts_and_time(self) -> None:
        valid = self.command_document()
        for field in ("argv", "cwd", "exit_code", "counts"):
            with self.subTest(field=field):
                invalid = deepcopy(valid)
                invalid["locator"].pop(field)
                self.assertEqual(self.record(invalid)["status"], "invalid")
        missing_time = deepcopy(valid)
        missing_time.pop("observed_at")
        with self.assertRaisesRegex(core.VoyageError, "observed_at"):
            self.record(missing_time)

    def test_command_result_verifies_raw_stdout_and_stderr_artifacts(self) -> None:
        self.assertEqual(self.record(self.command_document())["status"], "valid")
        missing = self.command_document()
        missing["locator"].pop("stderr")
        self.assertEqual(self.record(missing)["status"], "invalid")

    def test_command_result_rejects_inconsistent_counts_or_passing_claim(self) -> None:
        inconsistent = self.command_document()
        inconsistent["locator"]["counts"]["total"] = 2
        self.assertEqual(self.record(inconsistent)["status"], "invalid")
        false_pass = self.command_document()
        false_pass["locator"]["counts"] = {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "unknown": 0}
        self.assertEqual(self.record(false_pass)["status"], "invalid")

    def test_command_result_detects_raw_output_tampering(self) -> None:
        result = self.record(self.command_document())
        (self.root / "artifacts" / "stdout.txt").write_text("changed\n", encoding="utf-8")
        self.assertEqual(core.verify_evidence(self.paths, result["evidence_id"])["status"], "invalid")


class RuntimeReadbackEvidenceTests(EvidenceTestCase):
    def runtime_document(self, *, observed_at: str | None = None, fields: dict | None = None) -> dict:
        return evidence_document(
            "runtime-readback",
            {"environment_id": "prod", "target_version": "v1", "fields": fields if fields is not None else {"version": "v1"}, "max_age_seconds": 300},
            claim="runtime-state",
            observed_at=observed_at,
        )

    def test_runtime_readback_accepts_fresh_complete_observation(self) -> None:
        self.assertEqual(self.record(self.runtime_document())["status"], "valid")

    def test_runtime_readback_expires_to_unknown(self) -> None:
        document = self.runtime_document(observed_at="2026-01-01T00:00:00Z")
        result = self.record(document)
        checked = core.verify_evidence(self.paths, result["evidence_id"], now=datetime(2026, 1, 1, 0, 5, 1, tzinfo=timezone.utc))
        self.assertEqual(checked["status"], "unknown")

    def test_runtime_readback_rejects_missing_identity_future_time_or_empty_fields(self) -> None:
        documents = [self.runtime_document(fields={}), self.runtime_document(observed_at=timestamp(timedelta(minutes=10)))]
        missing_identity = self.runtime_document()
        missing_identity["locator"].pop("environment_id")
        documents.append(missing_identity)
        for document in documents:
            with self.subTest(document=document):
                self.assertEqual(self.record(document)["status"], "invalid")


class UserDecisionEvidenceTests(EvidenceTestCase):
    def decision_document(self, decision_id: str, *, action: str = "deploy", project_id: str = "evidence-example", source_id: str = "release") -> dict:
        return evidence_document(
            "user-decision",
            {"decision_id": decision_id, "action": action, "project_id": project_id, "source_id": source_id},
            claim="user-authorization",
        )

    def test_user_decision_evidence_validates_exact_action_project_and_source_scope(self) -> None:
        record_scoped_decision(self.paths, "USER-DEPLOY", action="deploy", sources=["release"])
        self.assertEqual(self.record(self.decision_document("USER-DEPLOY"))["status"], "valid")

    def test_user_decision_evidence_rejects_missing_non_user_or_scope_mismatch(self) -> None:
        record_scoped_decision(self.paths, "USER-DEPLOY", action="deploy", sources=["release"])
        documents = [
            self.decision_document("MISSING"),
            self.decision_document("USER-DEPLOY", action="delete"),
            self.decision_document("USER-DEPLOY", project_id="other"),
            self.decision_document("USER-DEPLOY", source_id="other"),
        ]
        for document in documents:
            with self.subTest(locator=document["locator"]):
                self.assertEqual(self.record(document)["status"], "invalid")

    def test_revoked_user_decision_evidence_becomes_invalid(self) -> None:
        record_scoped_decision(self.paths, "USER-DEPLOY", action="deploy", sources=["release"])
        result = self.record(self.decision_document("USER-DEPLOY"))
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.revoked", subject="USER-DEPLOY", risk="standard", payload={"reason": "withdrawn"})
        self.assertEqual(core.verify_evidence(self.paths, result["evidence_id"])["status"], "invalid")


class DecisionRevocationIntegrationTests(EvidenceTestCase):
    def test_revoked_decision_cannot_authorize_strict_work(self) -> None:
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.created", subject="W-STRICT", risk="strict", payload={"title": "Strict", "scope": "test", "acceptance": ["safe"]})
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.recorded", subject="USER-STRICT", risk="strict", payload={"decision": "authorize"})
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.revoked", subject="USER-STRICT", risk="standard", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-STRICT", risk="standard", authorization="USER-STRICT")

    def test_revoked_scoped_decision_cannot_activate_truth(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            paths = core.initialize_project(Path(directory), "revoked-bootstrap")
            reviewed_contracts(paths)
            record_scoped_decision(paths, "USER-TRUTH", action="truth.activate", sources=["product"])
            core.append_event(paths, actor="user", loop="user", event_type="decision.revoked", subject="USER-TRUTH", risk="standard", payload={"reason": "withdrawn"})
            with self.assertRaisesRegex(core.VoyageError, "revoked"):
                core.activate_truth(paths, actor="gov", source_id="product", decision_id="USER-TRUTH")

    def test_revoked_decision_cannot_resume_or_claim_strict_resource(self) -> None:
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.created", subject="W-RESUME", risk="standard", payload={"title": "Resume", "scope": "test", "acceptance": ["safe"]})
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-RESUME", risk="standard")
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.awaiting-user", subject="W-RESUME", risk="standard", payload={"decision": "continue"})
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.recorded", subject="USER-RESUME", risk="strict", payload={"decision": "continue"})
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.revoked", subject="USER-RESUME", risk="standard", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            core.append_event(self.paths, actor="gov", loop="governance", event_type="work.user-authorized", subject="W-RESUME", risk="standard", authorization="USER-RESUME")

        core.register_resource(self.paths, actor="gov", resource_id="file:strict", resource_type="file", mode="exclusive", risk="strict")
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.created", subject="W-RESOURCE", risk="strict", payload={"title": "Resource", "scope": "test", "acceptance": ["safe"], "required_resources": ["file:strict"]})
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.recorded", subject="USER-RESOURCE", risk="strict", payload={"decision": "authorize resource"})
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-RESOURCE", risk="standard", authorization="USER-RESOURCE")
        core.append_event(self.paths, actor="user", loop="user", event_type="decision.revoked", subject="USER-RESOURCE", risk="standard", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            core.append_event(self.paths, actor="dev", loop="execution", event_type="resource.claimed", subject="file:strict", risk="strict", payload={"resource_id": "file:strict", "lease_id": "lease-strict", "work_id": "W-RESOURCE", "expires_at": "2099-01-01T00:00:00Z"})


class EvidenceGateIntegrationTests(EvidenceTestCase):
    def typed_refs(self) -> tuple[str, str, str]:
        revision = self.initialize_git()
        anchor = self.record(self.git_document(revision), actor="dev")["evidence_id"]
        execution = self.record(self.command_document(producer="dev"), actor="dev")["evidence_id"]
        quality_document = self.command_document(producer="qa")
        quality_document["locator"]["stdout"] = self.raw_artifact("artifacts/qa-stdout.txt", b"1 passed\n")
        quality_document["locator"]["stderr"] = self.raw_artifact("artifacts/qa-stderr.txt", b"")
        quality = self.record(quality_document, actor="qa")["evidence_id"]
        return anchor, execution, quality

    def test_typed_delivery_quality_and_gate_complete_lifecycle(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        counts = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
        core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.passed", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": counts})
        core.append_event(self.paths, actor="qa", loop="quality", event_type="gate.recorded", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"gate_id": "independent-quality", "counts": counts})
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.accepted", subject="W-1", risk="standard")
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.closed", subject="W-1", risk="standard")
        self.assertEqual(core.current_state(self.paths)["works"]["W-1"]["status"], "closed")

    def test_quality_and_gate_revalidate_evidence_at_consumption_time(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        (self.root / "artifacts" / "qa-stdout.txt").write_text("tampered", encoding="utf-8")
        counts = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
        with self.assertRaisesRegex(core.VoyageError, "evidence.*invalid"):
            core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.passed", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": counts})

    def test_repair_anchor_invalidates_old_quality_conclusion(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        counts = {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "unknown": 0}
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.rejected", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": counts})
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.started", subject="W-1", risk="standard")
        artifact = self.root / "repair.bin"
        artifact.write_bytes(b"repair")
        new_anchor = self.record(evidence_document("artifact-digest", {"path": "repair.bin", "algorithm": "sha256", "digest": hashlib.sha256(b"repair").hexdigest()}, claim="delivery-artifact"))["evidence_id"]
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=new_anchor, evidence=[execution])
        with self.assertRaisesRegex(core.VoyageError, "has not passed quality"):
            core.append_event(self.paths, actor="gov", loop="governance", event_type="work.accepted", subject="W-1", risk="standard")

    def test_executor_still_cannot_sign_final_quality_with_typed_evidence(self) -> None:
        anchor, execution, _quality = self.typed_refs()
        self.prepare_work()
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        counts = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
        with self.assertRaisesRegex(core.VoyageError, "executor cannot issue final quality verdict"):
            core.append_event(self.paths, actor="dev", loop="quality", event_type="quality.passed", subject="W-1", risk="standard", anchor=anchor, evidence=[execution], payload={"counts": counts})

    def test_legacy_ledger_replays_but_legacy_refs_cannot_satisfy_new_events(self) -> None:
        self.assertEqual(core.validate_project(core.project_paths(REPOSITORY)), [])
        self.prepare_work()
        with self.assertRaisesRegex(core.VoyageError, "typed evidence ID"):
            core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor="commit:abc", evidence=["self-test"])

    def test_acceptance_revalidates_current_delivery_and_gate_evidence(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        counts = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.passed", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": counts})
        (self.root / "artifacts" / "qa-stdout.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(core.VoyageError, "current gate evidence.*invalid"):
            core.append_event(self.paths, actor="gov", loop="governance", event_type="work.accepted", subject="W-1", risk="standard")

    def test_closure_revalidates_accepted_delivery_and_gate_evidence(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        counts = {"total": 1, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.passed", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": counts})
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.accepted", subject="W-1", risk="standard")
        (self.root / "artifacts" / "qa-stdout.txt").write_text("tampered", encoding="utf-8")
        with self.assertRaisesRegex(core.VoyageError, "current gate evidence.*invalid"):
            core.append_event(self.paths, actor="gov", loop="governance", event_type="work.closed", subject="W-1", risk="standard")

    def test_stale_historical_evidence_does_not_block_repair_with_new_anchor(self) -> None:
        anchor, execution, quality = self.typed_refs()
        self.prepare_work()
        rejected_counts = {"total": 1, "passed": 0, "failed": 1, "skipped": 0, "unknown": 0}
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        core.append_event(self.paths, actor="qa", loop="quality", event_type="quality.rejected", subject="W-1", risk="standard", anchor=anchor, evidence=[quality], payload={"counts": rejected_counts})
        (self.root / "artifacts" / "qa-stdout.txt").write_text("stale historical output", encoding="utf-8")
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.started", subject="W-1", risk="standard")
        artifact = self.root / "repair-v2.bin"
        artifact.write_bytes(b"repair-v2")
        new_anchor = self.record(evidence_document("artifact-digest", {"path": "repair-v2.bin", "algorithm": "sha256", "digest": hashlib.sha256(b"repair-v2").hexdigest()}, claim="delivery-artifact"))["evidence_id"]
        new_execution_document = self.command_document(producer="dev")
        new_execution_document["locator"]["stdout"] = self.raw_artifact("artifacts/repair-stdout.txt", b"repair passed\n")
        new_execution_document["locator"]["stderr"] = self.raw_artifact("artifacts/repair-stderr.txt", b"")
        new_execution = self.record(new_execution_document, actor="dev")["evidence_id"]
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=new_anchor, evidence=[new_execution])
        self.assertEqual(core.current_state(self.paths)["works"]["W-1"]["delivery"]["anchor"], new_anchor)


class EvidenceColdStartValidationTests(EvidenceTestCase):
    def test_validate_detects_tampered_content_addressed_document(self) -> None:
        result = self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}))
        digest = result["evidence_id"].split(":", 1)[1]
        target = self.paths.evidence / "sha256" / f"{digest}.json"
        document = json.loads(target.read_text(encoding="utf-8"))
        document["claim"] = "tampered"
        target.write_text(json.dumps(document), encoding="utf-8")
        errors = core.validate_project(self.paths)
        self.assertTrue(any("evidence digest mismatch" in error for error in errors), errors)

    def test_validate_rechecks_evidence_consumed_by_historical_transition(self) -> None:
        revision = self.initialize_git()
        anchor = self.record(self.git_document(revision))["evidence_id"]
        execution = self.record(self.command_document(producer="dev"))["evidence_id"]
        self.prepare_work()
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.delivered", subject="W-1", risk="standard", anchor=anchor, evidence=[execution])
        (self.root / "artifacts" / "stdout.txt").write_text("tampered\n", encoding="utf-8")
        errors = core.validate_project(self.paths)
        self.assertTrue(any("consumed evidence" in error and "invalid" in error for error in errors), errors)

    def test_validate_allows_recorded_invalid_or_unknown_evidence_when_unused(self) -> None:
        self.initialize_git()
        self.record(self.git_document("f" * 40))
        self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 1}, observed_at="2026-01-01T00:00:00Z"))
        self.assertEqual(core.validate_project(self.paths), [])

    def test_validate_detects_missing_document_for_verification_event(self) -> None:
        result = self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}))
        digest = result["evidence_id"].split(":", 1)[1]
        (self.paths.evidence / "sha256" / f"{digest}.json").unlink()
        errors = core.validate_project(self.paths)
        self.assertTrue(any("missing required file" in error and "evidence" in error for error in errors), errors)


class EvidenceCliAndContractTests(EvidenceTestCase):
    def run_cli(self, *arguments: str, expected: int = 0) -> dict:
        result = subprocess.run([sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *arguments], check=False, text=True, capture_output=True)
        self.assertEqual(result.returncode, expected, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        return json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}

    def test_cli_evidence_record_show_and_verify_are_structured(self) -> None:
        document_path = self.root / "runtime.json"
        document_path.write_text(json.dumps(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300})), encoding="utf-8")
        recorded = self.run_cli("evidence", "record", "--file", str(document_path), "--actor", "observer")
        self.assertEqual(recorded["status"], "valid")
        shown = self.run_cli("evidence", "show", recorded["evidence_id"])
        self.assertEqual(shown["document"]["kind"], "runtime-readback")
        verified = self.run_cli("evidence", "verify", recorded["evidence_id"], "--actor", "auditor")
        self.assertEqual(verified["status"], "valid")
        self.assertIn("validator_version", verified)

    def test_evidence_schema_accepts_all_five_kinds_and_rejects_bad_common_contract(self) -> None:
        from tests.test_contracts import schema_errors

        revision = self.initialize_git()
        artifact = self.root / "artifact.bin"
        artifact.write_bytes(b"artifact")
        record_scoped_decision(self.paths, "USER-DEPLOY", action="deploy", sources=["release"])
        documents = [
            self.git_document(revision),
            evidence_document("artifact-digest", {"path": "artifact.bin", "algorithm": "sha256", "digest": hashlib.sha256(b"artifact").hexdigest()}),
            self.command_document(),
            evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}),
            evidence_document("user-decision", {"decision_id": "USER-DEPLOY", "action": "deploy", "project_id": "evidence-example", "source_id": "release"}),
        ]
        for document in documents:
            with self.subTest(kind=document["kind"]):
                self.assertEqual(schema_errors("evidence", document), [])
        invalid = deepcopy(documents[0])
        invalid.pop("producer")
        self.assertTrue(schema_errors("evidence", invalid))

    def test_event_schema_accepts_evidence_verification_events(self) -> None:
        from tests.test_contracts import schema_errors

        self.record(evidence_document("runtime-readback", {"environment_id": "dev", "target_version": "v1", "fields": {"healthy": True}, "max_age_seconds": 300}))
        self.assertEqual(schema_errors("event", core.load_events(self.paths.ledger)[-1]), [])

    def test_skill_and_runbook_document_typed_evidence_protocol(self) -> None:
        skill = (REPOSITORY / "SKILL.md").read_text(encoding="utf-8")
        runbook = (REPOSITORY / "docs" / "operations" / "runbook.md").read_text(encoding="utf-8")
        self.assertIn("evidence verify", skill)
        for phrase in ("sha256:", "runtime-readback", "legacy-unverified", "evidence record", "evidence verify"):
            self.assertIn(phrase, runbook)

    def test_dogfood_repository_remains_valid_with_legacy_history(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.validate_project(paths), [])
        self.assertEqual(core.recovery_snapshot(paths)["project_stage"], "operational")


if __name__ == "__main__":
    unittest.main()
