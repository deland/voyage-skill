from __future__ import annotations

import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import voyage_skill.core as core
import voyage_skill.cli as cli

from tests.support import operational_project, typed_command_evidence
from tests.test_contracts import schema_errors


REPOSITORY = Path(__file__).resolve().parents[1]
BENCHMARK_SCRIPT = REPOSITORY / "scripts" / "voyage-benchmark.py"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
SYSTEM = REPOSITORY / "docs" / "system" / "graph.md"
AUTHORITY = REPOSITORY / "docs" / "governance" / "authority.md"
PRODUCT = REPOSITORY / "docs" / "product" / "contract.md"
SKILL = REPOSITORY / "SKILL.md"
INIT_MARKER = Path(".voyage/init-state.json")


def benchmark_module():
    return importlib.import_module("voyage_skill.benchmark")


def synthetic_events(count: int) -> list[dict]:
    first = core.make_event(
        None,
        actor="voyage-system",
        loop="system",
        event_type="project.initialized",
        subject="long-ledger",
        risk="standard",
        payload={"project_stage": "bootstrap", "extension_mode": "explicit"},
    )
    events = [first]
    previous = first["hash"]
    for index in range(1, count):
        event = core.make_event(
            previous,
            actor="probe",
            loop="system",
            event_type="observation.recorded",
            subject=f"observation:{index}",
            risk="standard",
            payload={"sequence": index},
            evidence=["legacy:synthetic-benchmark"],
        )
        events.append(event)
        previous = event["hash"]
    return events


def control_digest(root: Path) -> str:
    rows = []
    control = root / ".voyage"
    for path in sorted(control.rglob("*")):
        if path.is_file():
            rows.append((str(path.relative_to(root)), hashlib.sha256(path.read_bytes()).hexdigest()))
    return core.content_hash(rows)


def write_events(path: Path, events: list[dict]) -> None:
    path.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")


class BenchmarkPolicyTests(unittest.TestCase):
    def test_benchmark_policy_is_versioned_and_quantitative(self) -> None:
        benchmark = benchmark_module()
        policy = benchmark.benchmark_policy_view()
        self.assertEqual(policy["schema_version"], 1)
        self.assertEqual(policy["default_event_counts"], [1_000, 10_000, 100_000])
        self.assertEqual(policy["snapshot_review"]["target_event_count"], 100_000)
        self.assertEqual(policy["snapshot_review"]["max_median_seconds"], 2.0)
        self.assertEqual(policy["snapshot_review"]["max_ledger_bytes"], 256 * 1024 * 1024)
        json.dumps(policy, sort_keys=True)

    def test_small_benchmark_measures_load_hash_and_replay_without_errors(self) -> None:
        report = benchmark_module().run_benchmark(event_counts=[25, 100], runs=2)
        self.assertEqual(report["schema_version"], 1)
        self.assertEqual([row["event_count"] for row in report["rows"]], [25, 100])
        for row in report["rows"]:
            self.assertGreater(row["ledger_bytes"], 0)
            self.assertEqual(row["runs"], 2)
            self.assertEqual(len(row["samples"]), 2)
            self.assertEqual(row["chain_errors"], 0)
            self.assertTrue(row["head_matches"])
            self.assertEqual(
                set(row["medians"]),
                {"load_seconds", "hash_seconds", "replay_seconds", "total_seconds"},
            )

    def test_below_threshold_retains_full_replay(self) -> None:
        benchmark = benchmark_module()
        decision = benchmark.assess_rows([
            {
                "event_count": 100_000,
                "ledger_bytes": 47_477_748,
                "medians": {"total_seconds": 0.9164},
                "chain_errors": 0,
                "head_matches": True,
            }
        ])
        self.assertEqual(decision["status"], "retain-full-replay")
        self.assertEqual(decision["reasons"], [])
        self.assertFalse(decision["creates_snapshot"])

    def test_time_or_size_threshold_requires_investigation_only(self) -> None:
        benchmark = benchmark_module()
        cases = [
            (2.0, 47_477_748, "time-threshold"),
            (0.5, 256 * 1024 * 1024, "size-threshold"),
        ]
        for seconds, byte_count, reason in cases:
            with self.subTest(reason=reason):
                decision = benchmark.assess_rows([
                    {
                        "event_count": 100_000,
                        "ledger_bytes": byte_count,
                        "medians": {"total_seconds": seconds},
                        "chain_errors": 0,
                        "head_matches": True,
                    }
                ])
                self.assertEqual(decision["status"], "investigate-snapshot")
                self.assertIn(reason, decision["reasons"])
                self.assertFalse(decision["creates_snapshot"])
                self.assertIn("User-approved", decision["next_safe_action"])

    def test_missing_target_sample_is_insufficient_data(self) -> None:
        decision = benchmark_module().assess_rows([
            {"event_count": 10_000, "ledger_bytes": 4_727_748, "medians": {"total_seconds": 0.0749}}
        ])
        self.assertEqual(decision["status"], "insufficient-data")
        self.assertFalse(decision["creates_snapshot"])
        self.assertIn("100000", decision["next_safe_action"].replace(",", ""))

    def test_invalid_target_sample_is_insufficient_data(self) -> None:
        base = {
            "event_count": 100_000,
            "ledger_bytes": 47_477_748,
            "medians": {"total_seconds": 0.9},
            "chain_errors": 0,
            "head_matches": True,
        }
        cases = []
        missing_seconds = dict(base)
        missing_seconds["medians"] = {}
        cases.append(missing_seconds)
        missing_bytes = dict(base)
        missing_bytes.pop("ledger_bytes")
        cases.append(missing_bytes)
        chain_error = dict(base, chain_errors=1)
        cases.append(chain_error)
        wrong_head = dict(base, head_matches=False)
        cases.append(wrong_head)
        for row in cases:
            with self.subTest(row=row):
                decision = benchmark_module().assess_rows([row])
                self.assertEqual(decision["status"], "insufficient-data")
                self.assertFalse(decision["creates_snapshot"])

    def test_benchmark_script_emits_json_and_mutates_no_project_file(self) -> None:
        before = control_digest(REPOSITORY)
        ledger_before = (REPOSITORY / ".voyage/ledger/events.jsonl").read_bytes()
        result = subprocess.run(
            [sys.executable, "-B", str(BENCHMARK_SCRIPT), "--events", "25", "--events", "100", "--runs", "2"],
            cwd=REPOSITORY,
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY / "src"), "PYTHONPYCACHEPREFIX": "/tmp/voyage-skill-pycache"},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["decision"]["status"], "insufficient-data")
        self.assertEqual(control_digest(REPOSITORY), before)
        self.assertEqual((REPOSITORY / ".voyage/ledger/events.jsonl").read_bytes(), ledger_before)


class LongLedgerAuthorityTests(unittest.TestCase):
    def test_ten_thousand_event_ledger_loads_validates_and_replays_exact_head(self) -> None:
        events = synthetic_events(10_000)
        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "events.jsonl"
            write_events(ledger, events)
            loaded = core.load_events(ledger)
        self.assertEqual(core.validate_hash_chain(loaded), [])
        state = core.replay_events(loaded, resources={"resources": []}, gates={"gates": []})
        self.assertEqual(len(loaded), 10_000)
        self.assertEqual(len(state["observations"]), 9_999)
        self.assertEqual(state["last_event"], events[-1]["event_id"])

    def test_append_after_long_ledger_preserves_chain_and_single_new_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = operational_project(root, "long-append")
            events = core.load_events(paths.ledger)
            previous = events[-1]["hash"]
            for index in range(2_000):
                event = core.make_event(
                    previous,
                    actor="probe",
                    loop="system",
                    event_type="observation.recorded",
                    subject=f"long:{index}",
                    risk="standard",
                    evidence=["legacy:long-ledger"],
                )
                events.append(event)
                previous = event["hash"]
            write_events(paths.ledger, events)
            old_head = events[-1]["hash"]
            before_count = len(events)
            appended = core.append_event(
                paths,
                actor="probe",
                loop="system",
                event_type="observation.recorded",
                subject="long:final",
                risk="standard",
                evidence=["legacy:long-ledger"],
            )
            loaded = core.load_events(paths.ledger)
        self.assertEqual(len(loaded), before_count + 1)
        self.assertEqual(appended["prev_hash"], old_head)
        self.assertEqual(core.validate_hash_chain(loaded), [])

    def test_runtime_contains_no_snapshot_checkpoint_or_incremental_index_surface(self) -> None:
        for name in (
            "create_snapshot", "load_snapshot", "write_checkpoint", "load_checkpoint",
            "incremental_index", "snapshot_state",
        ):
            self.assertFalse(hasattr(core, name), name)
        parser = cli.build_parser()
        command_action = next(action for action in parser._actions if action.dest == "command")
        for command in ("snapshot", "checkpoint", "index"):
            self.assertNotIn(command, command_action.choices)
        self.assertFalse(any("snapshot" in path.name or "checkpoint" in path.name for path in (REPOSITORY / "schemas").iterdir()))

    def test_benchmark_and_docs_require_separate_user_work_before_snapshot(self) -> None:
        policy = benchmark_module().benchmark_policy_view()
        self.assertFalse(policy["snapshot_review"]["automatic"])
        text = SYSTEM.read_text(encoding="utf-8") + RUNBOOK.read_text(encoding="utf-8")
        for phrase in ("100,000", "2.0", "256 MiB", "User-approved", "ledger-head hash", "disposable"):
            self.assertIn(phrase, text)
        self.assertIn("no snapshot", text.lower())


class PlatformLockTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "platform-example")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_runtime_capabilities_report_fcntl_backend_on_supported_host(self) -> None:
        capabilities = core.runtime_capabilities()
        self.assertEqual(capabilities["schema_version"], 1)
        self.assertEqual(capabilities["write_lock"]["backend"], "fcntl")
        self.assertTrue(capabilities["write_lock"]["supported"])
        self.assertTrue(capabilities["write_lock"]["append_safe"])
        self.assertTrue(capabilities["platform"])

    def test_core_import_and_read_only_validation_do_not_require_fcntl(self) -> None:
        source = Path(core.__file__).read_text(encoding="utf-8")
        self.assertNotIn("\nimport fcntl\n", source)
        with mock.patch.object(core, "_fcntl", None, create=True):
            self.assertEqual(core.validate_project(self.paths), [])
            self.assertEqual(core.current_state(self.paths)["project_id"], "platform-example")
            snapshot = core.recovery_snapshot(self.paths)
        self.assertFalse(snapshot["runtime_capabilities"]["write_lock"]["supported"])

    def test_unsupported_write_lock_fails_before_ledger_mutation(self) -> None:
        before = self.paths.ledger.read_bytes()
        head = core.current_state(self.paths)["last_event"]
        with mock.patch.object(core, "_fcntl", None, create=True):
            with self.assertRaisesRegex(core.VoyageError, "fcntl|unsupported|read-only"):
                core.append_event(
                    self.paths,
                    actor="probe",
                    loop="system",
                    event_type="observation.recorded",
                    subject="platform:write",
                    risk="standard",
                    evidence=["legacy:platform"],
                )
        self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.assertEqual(core.current_state(self.paths)["last_event"], head)

    def test_recovery_names_unsupported_platform_next_action(self) -> None:
        with mock.patch.object(core, "_fcntl", None, create=True):
            capabilities = core.recovery_snapshot(self.paths)["runtime_capabilities"]
        self.assertFalse(capabilities["write_lock"]["supported"])
        self.assertFalse(capabilities["write_lock"]["append_safe"])
        self.assertIn("Unix", capabilities["write_lock"]["next_safe_action"])
        self.assertIn("external", capabilities["write_lock"]["next_safe_action"])

    def test_active_docs_state_unix_only_write_support_without_windows_claim(self) -> None:
        system = SYSTEM.read_text(encoding="utf-8")
        runbook = RUNBOOK.read_text(encoding="utf-8")
        for text in (system, runbook):
            self.assertIn("`fcntl`", text)
            self.assertIn("Unix", text)
            self.assertIn("read-only", text)
            self.assertIn("Windows", text)
            self.assertIn("not implemented", text.lower())


class TrustBoundaryTests(unittest.TestCase):
    def test_runtime_capabilities_deny_cryptographic_actor_authentication(self) -> None:
        trust = core.runtime_capabilities()["actor_identity"]
        self.assertEqual(trust["mode"], "local-caller-asserted")
        self.assertFalse(trust["cryptographic_authentication"])
        self.assertTrue(trust["tamper_evident"])
        self.assertFalse(trust["tamper_proof"])

    def test_authority_product_system_and_skill_share_exact_trust_boundary(self) -> None:
        texts = [path.read_text(encoding="utf-8") for path in (AUTHORITY, PRODUCT, SYSTEM, SKILL)]
        for text in texts:
            lowered = " ".join(text.lower().split())
            self.assertIn("actor", lowered)
            self.assertIn("os account", lowered)
            self.assertIn("worktree", lowered)
            self.assertIn("cryptographic", lowered)
        self.assertIn("caller assertion", " ".join(texts).lower())

    def test_docs_do_not_claim_signatures_hostile_writer_protection_or_multi_host_locking(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in (AUTHORITY, PRODUCT, SYSTEM, RUNBOOK, SKILL)).lower()
        for forbidden in (
            "cryptographically authenticated actor ids",
            "prevents hostile local writers",
            "tamper-proof ledger",
            "distributed write lock",
            "multi-host write coordination is supported",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn("hostile", text)
        self.assertIn("out of scope", text)

    def test_skill_keeps_trust_detail_progressively_disclosed(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        section = text[text.index("<!-- trust-loading:start -->"):text.index("<!-- trust-loading:end -->")]
        self.assertIn("active governance", section)
        self.assertIn("system truth", section)
        self.assertIn("actor", section.lower())
        self.assertLessEqual(len(section.splitlines()), 8)
        self.assertNotIn("msvcrt", section.lower())


class ResourceIdentityClosureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "resource-identity")
        self.probe = typed_command_evidence(self.paths, name="resource-probe", producer="probe")
        core.register_resource(
            self.paths,
            actor="gov",
            resource_id="file:canonical",
            resource_type="file",
            mode="rebuildable",
            risk="standard",
        )
        core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject="W-RESOURCE",
            risk="standard",
            payload={"title": "resource", "scope": "test", "acceptance": ["done"]},
        )
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-RESOURCE", risk="standard")
        core.append_event(self.paths, actor="dev", loop="execution", event_type="work.started", subject="W-RESOURCE", risk="standard")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def claim(self, lease_id: str) -> dict:
        return core.append_event(
            self.paths,
            actor="dev",
            loop="execution",
            event_type="resource.claimed",
            subject="file:canonical",
            risk="standard",
            evidence=[self.probe],
            payload={
                "resource_id": "file:canonical",
                "lease_id": lease_id,
                "work_id": "W-RESOURCE",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )

    def test_all_resource_lifecycle_events_use_resource_subject_and_lease_payload(self) -> None:
        claim = self.claim("L-1")
        release = core.append_event(
            self.paths,
            actor="dev",
            loop="execution",
            event_type="resource.released",
            subject="file:canonical",
            risk="standard",
            payload={"resource_id": "file:canonical", "lease_id": "L-1"},
        )
        self.claim("L-2")
        recovered = core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="resource.recovered",
            subject="file:canonical",
            risk="standard",
            evidence=[self.probe],
            payload={"resource_id": "file:canonical", "lease_id": "L-2"},
        )
        for event in (claim, release, recovered):
            self.assertEqual(event["subject"], event["payload"]["resource_id"])
            self.assertTrue(event["payload"]["lease_id"])
            self.assertEqual(schema_errors("event", event), [])

    def test_resource_identity_mismatch_is_rejected_before_replay_state_changes(self) -> None:
        before = self.paths.ledger.read_bytes()
        with self.assertRaisesRegex(core.VoyageError, "resource identity|subject"):
            core.append_event(
                self.paths,
                actor="dev",
                loop="execution",
                event_type="resource.claimed",
                subject="file:wrong",
                risk="standard",
                evidence=[self.probe],
                payload={
                    "resource_id": "file:canonical",
                    "lease_id": "L-MISMATCH",
                    "work_id": "W-RESOURCE",
                    "expires_at": "2099-01-01T00:00:00Z",
                },
            )
        self.assertEqual(self.paths.ledger.read_bytes(), before)
        self.claim("L-1")
        for event_type in ("resource.released", "resource.recovered"):
            with self.subTest(event_type=event_type):
                current = self.paths.ledger.read_bytes()
                with self.assertRaisesRegex(core.VoyageError, "resource identity"):
                    core.append_event(
                        self.paths,
                        actor="gov",
                        loop="governance",
                        event_type=event_type,
                        subject="file:wrong",
                        risk="standard",
                        evidence=[self.probe] if event_type == "resource.recovered" else [],
                        payload={"resource_id": "file:canonical", "lease_id": "L-1"},
                    )
                self.assertEqual(self.paths.ledger.read_bytes(), current)

    def test_lease_oriented_cli_resolves_resource_from_replayed_state(self) -> None:
        self.claim("L-CLI")
        result = subprocess.run(
            [
                sys.executable, "-B", str(REPOSITORY / "scripts/voyage.py"),
                "--root", str(self.root), "resource", "release", "L-CLI",
                "--actor", "dev", "--loop", "execution",
            ],
            check=False,
            text=True,
            capture_output=True,
            env={**os.environ, "PYTHONPATH": str(REPOSITORY / "src")},
        )
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        event = core.load_events(self.paths.ledger)[-1]
        self.assertEqual(event["subject"], "file:canonical")
        self.assertEqual(event["payload"], {"resource_id": "file:canonical", "lease_id": "L-CLI"})

    def test_schema_graph_recovery_and_docs_use_the_same_resource_identity(self) -> None:
        self.claim("L-GRAPH")
        core.append_event(
            self.paths,
            actor="user",
            loop="user",
            event_type="decision.recorded",
            subject="USER-GRAPH",
            risk="standard",
            payload={
                "decision": "extension.enable",
                "scope": {
                    "actions": ["extension.enable"],
                    "project_id": "resource-identity",
                    "extensions": ["derived-graph"],
                    "extension_versions": {"derived-graph": "1.0.0"},
                },
            },
        )
        core.enable_extension(
            self.paths,
            actor="gov",
            extension_id="derived-graph",
            version="1.0.0",
            decision_id="USER-GRAPH",
        )
        graph = core.derive_graph(self.paths)
        work = next(node for node in graph["nodes"] if node["id"] == "work:W-RESOURCE")
        self.assertEqual(work["status"], "active")
        lease = next(node for node in graph["nodes"] if node["id"] == "lease:L-GRAPH")
        self.assertEqual(lease["attributes"]["resource_id"], "file:canonical")
        self.assertEqual(core.recovery_snapshot(self.paths)["active_leases"][0]["resource_id"], "file:canonical")
        text = RUNBOOK.read_text(encoding="utf-8") + SYSTEM.read_text(encoding="utf-8")
        for value in ("resource ID", "lease ID", "event subject", "payload.resource_id"):
            self.assertIn(value, text)


class InitRecoveryTests(unittest.TestCase):
    def marker(self, root: Path) -> dict:
        return json.loads((root / INIT_MARKER).read_text(encoding="utf-8"))

    def interrupt(self, root: Path, phase: str, *, project_id: str = "init-recovery", registry: str | None = None) -> None:
        def fail(current: str) -> None:
            if current == phase:
                raise OSError(f"injected interruption after {phase}")

        with mock.patch.object(core, "_init_phase_hook", side_effect=fail, create=True):
            with self.assertRaisesRegex(core.VoyageError, "interrupted|rerun"):
                core.initialize_project(root, project_id, registry)

    def test_successful_init_removes_recovery_marker_and_records_one_event(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = core.initialize_project(root, "init-success")
            self.assertFalse((root / INIT_MARKER).exists())
            events = core.load_events(paths.ledger)
        initialized = [event for event in events if event["type"] == "project.initialized"]
        self.assertEqual(len(initialized), 1)
        self.assertEqual(initialized[0]["subject"], "init-success")

    def test_interrupted_init_leaves_versioned_scoped_marker(self) -> None:
        for phase in ("control-written", "truth-written", "ledger-written"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                self.interrupt(root, phase)
                marker = self.marker(root)
                self.assertEqual(marker["schema_version"], 1)
                self.assertEqual(marker["status"], "in-progress")
                self.assertEqual(marker["project_id"], "init-recovery")
                self.assertEqual(marker["truth_registry"], "docs/voyage/truth-registry.json")
                self.assertEqual(marker["registry_mode"], "generated")
                self.assertEqual(marker["phase"], phase)
                self.assertIn("rerun", marker["next_safe_action"])

    def test_same_arguments_resume_interrupted_init_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.interrupt(root, "truth-written")
            paths = core.initialize_project(root, "init-recovery")
            self.assertFalse((root / INIT_MARKER).exists())
            self.assertEqual(core.validate_project(paths), [])
            events = core.load_events(paths.ledger)
            registry = core.load_json(paths.truth_registry)
        self.assertEqual(sum(event["type"] == "project.initialized" for event in events), 1)
        self.assertEqual(len(registry["sources"]), 4)

    def test_resume_after_initial_event_does_not_duplicate_ledger_head(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.interrupt(root, "event-written")
            ledger = root / ".voyage/ledger/events.jsonl"
            before = core.load_events(ledger)
            self.assertEqual(sum(event["type"] == "project.initialized" for event in before), 1)
            paths = core.initialize_project(root, "init-recovery")
            after = core.load_events(paths.ledger)
        self.assertEqual(len(after), len(before))
        self.assertEqual(after[-1]["hash"], before[-1]["hash"])

    def test_mismatched_resume_arguments_refuse_without_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.interrupt(root, "ledger-written")
            marker_before = (root / INIT_MARKER).read_bytes()
            tree_before = control_digest(root)
            for project_id, registry in (
                ("different-project", None),
                ("init-recovery", "different/registry.json"),
            ):
                with self.subTest(project_id=project_id, registry=registry):
                    with self.assertRaisesRegex(core.VoyageError, "does not match|same|resume"):
                        core.initialize_project(root, project_id, registry)
                    self.assertEqual((root / INIT_MARKER).read_bytes(), marker_before)
                    self.assertEqual(control_digest(root), tree_before)

    def test_adopted_truth_registry_is_never_overwritten_during_retry(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "project/truth.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps({"schema_version": core.SCHEMA_VERSION, "project": "adopted-init", "sources": []}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            before = registry.read_bytes()
            self.interrupt(root, "truth-written", project_id="adopted-init", registry="project/truth.json")
            self.assertEqual(registry.read_bytes(), before)
            paths = core.initialize_project(root, "adopted-init", "project/truth.json")
            self.assertEqual(paths.truth_registry.read_bytes(), before)
        self.assertFalse((root / INIT_MARKER).exists())

    def test_invalid_adopted_registry_does_not_create_recovery_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(core.VoyageError, "truth registry not found"):
                core.initialize_project(root, "invalid-adopt", "missing/truth.json")
            self.assertFalse((root / INIT_MARKER).exists())
            self.assertFalse((root / ".voyage/manifest.json").exists())

    def test_fresh_init_refuses_preexisting_targets_without_overwrite(self) -> None:
        cases = (
            Path(".voyage/graph.json"),
            Path("docs/voyage/product.md"),
            Path("docs/voyage/truth-registry.json"),
        )
        for relative in cases:
            with self.subTest(relative=str(relative)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                original = b"user-owned\n"
                target.write_bytes(original)
                with self.assertRaisesRegex(core.VoyageError, "already exists|user-owned"):
                    core.initialize_project(root, "preexisting-target")
                self.assertEqual(target.read_bytes(), original)
                self.assertFalse((root / INIT_MARKER).exists())

    def test_adopted_init_refuses_preexisting_control_target_without_registry_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            registry = root / "project/truth.json"
            registry.parent.mkdir(parents=True)
            registry.write_text(
                json.dumps({"schema_version": core.SCHEMA_VERSION, "project": "adopted-control", "sources": []}) + "\n",
                encoding="utf-8",
            )
            graph = root / ".voyage/graph.json"
            graph.parent.mkdir(parents=True)
            graph.write_bytes(b"user-owned-control\n")
            registry_before = registry.read_bytes()
            graph_before = graph.read_bytes()
            with self.assertRaisesRegex(core.VoyageError, "already exists|user-owned"):
                core.initialize_project(root, "adopted-control", "project/truth.json")
            self.assertEqual(registry.read_bytes(), registry_before)
            self.assertEqual(graph.read_bytes(), graph_before)
            self.assertFalse((root / INIT_MARKER).exists())

    def test_interrupted_project_cannot_validate_as_operational_or_authorize_work(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.interrupt(root, "control-written")
            marker = self.marker(root)
            self.assertEqual(marker["status"], "in-progress")
            try:
                paths = core.project_paths(root)
            except core.VoyageError:
                paths = None
            if paths is not None:
                self.assertTrue(core.validate_project(paths))
                with self.assertRaises(core.VoyageError):
                    core.append_event(
                        paths,
                        actor="gov",
                        loop="governance",
                        event_type="work.authorized",
                        subject="W-NOT-READY",
                        risk="standard",
                    )
            self.assertIn("voyage init", marker["next_safe_action"])


if __name__ == "__main__":
    unittest.main()
