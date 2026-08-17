from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import voyage_skill.core as core

from tests.support import (
    REQUIRED_DOMAINS,
    REVIEWED_CONTRACTS,
    activate_all_truth,
    legacy_project,
    record_scoped_decision,
    reviewed_contracts,
)
from tests.test_contracts import REPOSITORY, schema_errors


SCRIPT = REPOSITORY / "scripts" / "voyage.py"


def source_by_domain(paths: core.ProjectPaths, domain: str) -> dict:
    registry = core.load_json(paths.truth_registry)
    return next(source for source in registry["sources"] if source.get("domain") == domain)


def source_by_id(paths: core.ProjectPaths, source_id: str) -> dict:
    registry = core.load_json(paths.truth_registry)
    return next(source for source in registry["sources"] if source.get("id") == source_id)


class BootstrapInitializationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = core.initialize_project(self.root, "bootstrap-project")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_new_manifest_starts_in_bootstrap(self) -> None:
        manifest = core.load_json(self.paths.manifest)
        self.assertEqual(manifest["project_stage"], "bootstrap")
        self.assertEqual(schema_errors("manifest", manifest), [])

    def test_generated_required_truth_starts_as_draft(self) -> None:
        registry = core.load_json(self.paths.truth_registry)
        required = {source["domain"]: source for source in registry["sources"] if source.get("domain") in REQUIRED_DOMAINS}
        self.assertEqual(set(required), set(REQUIRED_DOMAINS))
        for domain, source in required.items():
            with self.subTest(domain=domain):
                self.assertEqual(source["status"], "draft")
                self.assertIn("- Status: draft", (self.root / source["path"]).read_text(encoding="utf-8"))

    def test_generated_contracts_expose_unresolved_review_fields(self) -> None:
        registry = core.load_json(self.paths.truth_registry)
        for source in registry["sources"]:
            if source.get("domain") in REQUIRED_DOMAINS:
                with self.subTest(domain=source["domain"]):
                    self.assertIn("TODO", (self.root / source["path"]).read_text(encoding="utf-8"))

    def test_bootstrap_recovery_lists_required_domain_gaps(self) -> None:
        snapshot = core.recovery_snapshot(self.paths)
        self.assertEqual(snapshot["project_stage"], "bootstrap")
        self.assertEqual(set(snapshot["bootstrap"]["missing_domains"]), set(REQUIRED_DOMAINS))
        self.assertIn("review", snapshot["bootstrap"]["next_safe_action"])

    def test_bootstrap_rejects_work_authorization(self) -> None:
        core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject="W-1",
            risk="standard",
            payload={"title": "Bootstrap", "scope": "test", "acceptance": ["blocked"]},
        )
        with self.assertRaisesRegex(core.VoyageError, "bootstrap.*operational"):
            core.append_event(
                self.paths,
                actor="gov",
                loop="governance",
                event_type="work.authorized",
                subject="W-1",
                risk="standard",
            )

    def test_bootstrap_project_remains_structurally_valid(self) -> None:
        self.assertEqual(core.validate_project(self.paths), [])
        self.assertIsNotNone(core.recovery_snapshot(self.paths)["ledger_head"])


class TruthActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = core.initialize_project(self.root, "activation-project")
        reviewed_contracts(self.paths)
        self.product = source_by_domain(self.paths, "product")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def snapshot(self) -> tuple[dict, dict, str, list[dict]]:
        return (
            core.load_json(self.paths.manifest),
            core.load_json(self.paths.truth_registry),
            (self.root / self.product["path"]).read_text(encoding="utf-8"),
            core.load_events(self.paths.ledger),
        )

    def test_activation_rejects_unknown_decision(self) -> None:
        before = self.snapshot()
        with self.assertRaisesRegex(core.VoyageError, "recorded User decision"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="MISSING")
        self.assertEqual(self.snapshot(), before)

    def test_activation_rejects_non_user_decision(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "decision recording requires User loop"):
            record_scoped_decision(self.paths, "BAD-LOOP", action="truth.activate", loop="governance")

    def test_activation_rejects_scope_mismatch(self) -> None:
        record_scoped_decision(self.paths, "WRONG-ACTION", action="truth.migrate", sources=[self.product["id"]])
        with self.assertRaisesRegex(core.VoyageError, "does not cover action"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="WRONG-ACTION")

        record_scoped_decision(self.paths, "WRONG-SOURCE", action="truth.activate", sources=["another-source"])
        with self.assertRaisesRegex(core.VoyageError, "does not cover truth source"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="WRONG-SOURCE")

        record_scoped_decision(
            self.paths,
            "WRONG-PROJECT",
            action="truth.activate",
            sources=[self.product["id"]],
            project_id="another-project",
        )
        with self.assertRaisesRegex(core.VoyageError, "does not cover project"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="WRONG-PROJECT")

    def test_activation_rejects_missing_contract_file(self) -> None:
        record_scoped_decision(self.paths, "USER-1", action="truth.activate", sources=[self.product["id"]])
        (self.root / self.product["path"]).unlink()
        manifest = core.load_json(self.paths.manifest)
        registry = core.load_json(self.paths.truth_registry)
        ledger = core.load_events(self.paths.ledger)
        with self.assertRaisesRegex(core.VoyageError, "contract file is missing"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="USER-1")
        self.assertEqual(core.load_json(self.paths.manifest), manifest)
        self.assertEqual(core.load_json(self.paths.truth_registry), registry)
        self.assertEqual(core.load_events(self.paths.ledger), ledger)

    def test_activation_rejects_unresolved_bootstrap_contract(self) -> None:
        record_scoped_decision(self.paths, "USER-2", action="truth.activate", sources=[self.product["id"]])
        path = self.root / self.product["path"]
        path.write_text(REVIEWED_CONTRACTS["product"] + "\nTODO: unresolved\n", encoding="utf-8")
        with self.assertRaisesRegex(core.VoyageError, "unresolved TODO"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="USER-2")

        path.write_text("# Product contract\n\n- Status: draft\n", encoding="utf-8")
        with self.assertRaisesRegex(core.VoyageError, "required section"):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="USER-2")

    def test_activation_records_decision_and_exact_source(self) -> None:
        record_scoped_decision(self.paths, "USER-3", action="truth.activate", sources=[self.product["id"]])
        event = core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="USER-3")
        source = source_by_id(self.paths, self.product["id"])
        self.assertEqual(source["status"], "active")
        self.assertEqual(source["authority"], "user-decision:USER-3")
        self.assertIn("- Status: active", (self.root / source["path"]).read_text(encoding="utf-8"))
        self.assertEqual(event["type"], "truth.activated")
        self.assertEqual(event["authorization"], "USER-3")
        self.assertEqual(event["payload"]["source_id"], source["id"])
        self.assertEqual(event["payload"]["domain"], "product")
        self.assertEqual(event["payload"]["path"], source["path"])

    def test_failed_activation_is_atomic(self) -> None:
        before = self.snapshot()
        with self.assertRaises(core.VoyageError):
            core.activate_truth(self.paths, actor="gov", source_id=self.product["id"], decision_id="MISSING")
        self.assertEqual(self.snapshot(), before)


class OperationalTransitionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = core.initialize_project(self.root, "operational-project")
        reviewed_contracts(self.paths)
        self.sources = {
            source["domain"]: source
            for source in core.load_json(self.paths.truth_registry)["sources"]
            if source.get("domain") in REQUIRED_DOMAINS
        }
        record_scoped_decision(self.paths, "USER-ALL", action="truth.activate", sources=[item["id"] for item in self.sources.values()])

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def activate(self, domain: str) -> dict:
        return core.activate_truth(self.paths, actor="gov", source_id=self.sources[domain]["id"], decision_id="USER-ALL")

    def test_partial_activation_remains_bootstrap(self) -> None:
        for domain in REQUIRED_DOMAINS[:-1]:
            self.activate(domain)
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "bootstrap")
        self.assertEqual(core.truth_status(self.paths)["missing_domains"], [REQUIRED_DOMAINS[-1]])

    def test_four_verified_domains_become_operational(self) -> None:
        for domain in REQUIRED_DOMAINS:
            self.activate(domain)
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "operational")
        self.assertEqual(core.truth_status(self.paths)["project_stage"], "operational")
        self.assertEqual(core.truth_status(self.paths)["missing_domains"], [])

    def test_operational_stage_allows_work_authorization(self) -> None:
        for domain in REQUIRED_DOMAINS:
            self.activate(domain)
        core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject="W-1",
            risk="standard",
            payload={"title": "Operational", "scope": "test", "acceptance": ["authorized"]},
        )
        core.append_event(self.paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-1", risk="standard")
        self.assertEqual(core.current_state(self.paths)["works"]["W-1"]["status"], "authorized")

    def add_replacement(self, *, domain: str = "product") -> dict:
        registry = core.load_json(self.paths.truth_registry)
        replacement = {
            "id": f"{domain}-replacement",
            "domain": domain,
            "path": f"docs/voyage/{domain}-replacement.md",
            "version": "2",
            "status": "draft",
            "authority": "bootstrap-draft",
        }
        registry["sources"].append(replacement)
        core.atomic_write_json(self.paths.truth_registry, registry)
        (self.root / replacement["path"]).write_text(REVIEWED_CONTRACTS[domain], encoding="utf-8")
        record_scoped_decision(self.paths, f"USER-{domain}-REPLACE", action="truth.activate", sources=[replacement["id"]])
        return replacement

    def test_duplicate_active_domain_requires_supersedes(self) -> None:
        self.activate("product")
        replacement = self.add_replacement()
        with self.assertRaisesRegex(core.VoyageError, "active source.*supersedes"):
            core.activate_truth(self.paths, actor="gov", source_id=replacement["id"], decision_id="USER-product-REPLACE")

    def test_supersedes_must_target_same_domain(self) -> None:
        self.activate("governance")
        replacement = self.add_replacement(domain="product")
        with self.assertRaisesRegex(core.VoyageError, "same domain"):
            core.activate_truth(
                self.paths,
                actor="gov",
                source_id=replacement["id"],
                decision_id="USER-product-REPLACE",
                supersedes=self.sources["governance"]["id"],
            )

    def test_successful_supersession_is_atomic_and_auditable(self) -> None:
        self.activate("product")
        replacement = self.add_replacement()
        event = core.activate_truth(
            self.paths,
            actor="gov",
            source_id=replacement["id"],
            decision_id="USER-product-REPLACE",
            supersedes=self.sources["product"]["id"],
        )
        self.assertEqual(source_by_id(self.paths, self.sources["product"]["id"])["status"], "superseded")
        self.assertEqual(source_by_id(self.paths, replacement["id"])["status"], "active")
        self.assertEqual(event["payload"]["supersedes"], self.sources["product"]["id"])
        self.assertEqual(event["authorization"], "USER-product-REPLACE")

    def test_activation_cannot_be_replayed_for_same_source(self) -> None:
        self.activate("product")
        before = core.load_events(self.paths.ledger)
        with self.assertRaisesRegex(core.VoyageError, "already has activation evidence"):
            self.activate("product")
        self.assertEqual(core.load_events(self.paths.ledger), before)


class AdoptedTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        sources = []
        for domain in REQUIRED_DOMAINS:
            path = self.root / "docs" / f"{domain}.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"# Adopted {domain}\n\nReviewed project truth.\n", encoding="utf-8")
            sources.append({"id": f"adopted-{domain}", "domain": domain, "path": f"docs/{domain}.md", "version": "1", "status": "active"})
        registry = self.root / "docs" / "truth.json"
        core.atomic_write_json(registry, {"schema_version": "0.1.0", "project": "adopted", "sources": sources})
        self.paths = core.initialize_project(self.root, "adopted", "docs/truth.json")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_adopted_active_sources_do_not_auto_operationalize(self) -> None:
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "bootstrap")
        status = core.truth_status(self.paths)
        self.assertEqual(set(status["missing_domains"]), set(REQUIRED_DOMAINS))
        self.assertEqual(set(status["unverified_active_sources"]), {f"adopted-{domain}" for domain in REQUIRED_DOMAINS})

    def test_adopted_source_requires_user_scoped_activation(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "recorded User decision"):
            core.activate_truth(self.paths, actor="gov", source_id="adopted-product", decision_id="MISSING")
        record_scoped_decision(self.paths, "USER-ADOPT", action="truth.activate", sources=["adopted-product"])
        core.activate_truth(self.paths, actor="gov", source_id="adopted-product", decision_id="USER-ADOPT")
        self.assertNotIn("adopted-product", core.truth_status(self.paths)["unverified_active_sources"])

    def test_adopted_all_required_domains_need_all_evidence(self) -> None:
        ids = [f"adopted-{domain}" for domain in REQUIRED_DOMAINS]
        record_scoped_decision(self.paths, "USER-ADOPT-ALL", action="truth.activate", sources=ids)
        for source_id in ids[:-1]:
            core.activate_truth(self.paths, actor="gov", source_id=source_id, decision_id="USER-ADOPT-ALL")
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "bootstrap")
        core.activate_truth(self.paths, actor="gov", source_id=ids[-1], decision_id="USER-ADOPT-ALL")
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "operational")

    def test_adopted_registry_is_not_rewritten_on_failed_activation(self) -> None:
        before = self.paths.truth_registry.read_bytes()
        with self.assertRaises(core.VoyageError):
            core.activate_truth(self.paths, actor="gov", source_id="adopted-product", decision_id="MISSING")
        self.assertEqual(self.paths.truth_registry.read_bytes(), before)

    def test_adopted_registry_project_must_match_manifest_without_partial_init(self) -> None:
        other = self.root / "mismatch"
        registry = other / "docs" / "truth.json"
        registry.parent.mkdir(parents=True)
        core.atomic_write_json(
            registry,
            {
                "schema_version": "0.1.0",
                "project": "different-project",
                "sources": [],
            },
        )
        with self.assertRaisesRegex(core.VoyageError, "registry project.*does not match"):
            core.initialize_project(other, "expected-project", "docs/truth.json")
        self.assertFalse((other / ".voyage" / "manifest.json").exists())


class LegacyMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = legacy_project(self.root, "legacy-project")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_legacy_manifest_recovers_as_legacy_bootstrap(self) -> None:
        snapshot = core.recovery_snapshot(self.paths)
        self.assertEqual(snapshot["project_stage"], "legacy-bootstrap")
        self.assertTrue(snapshot["bootstrap"]["legacy"])
        self.assertIn("truth migrate", snapshot["bootstrap"]["next_safe_action"])

    def test_legacy_first_write_requires_confirmation(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "legacy.*migration confirmation"):
            core.append_event(
                self.paths,
                actor="gov",
                loop="governance",
                event_type="work.created",
                subject="W-1",
                risk="standard",
                payload={"title": "Legacy", "scope": "test", "acceptance": ["blocked"]},
            )
        record_scoped_decision(self.paths, "USER-MIGRATE", action="truth.migrate")

    def test_legacy_migration_rejects_missing_or_mismatched_decision(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "recorded User decision"):
            core.migrate_legacy_project(self.paths, actor="gov", decision_id="MISSING")
        record_scoped_decision(self.paths, "WRONG", action="truth.activate")
        with self.assertRaisesRegex(core.VoyageError, "does not cover action"):
            core.migrate_legacy_project(self.paths, actor="gov", decision_id="WRONG")
        record_scoped_decision(self.paths, "WRONG-PROJECT", action="truth.migrate", project_id="other")
        with self.assertRaisesRegex(core.VoyageError, "does not cover project"):
            core.migrate_legacy_project(self.paths, actor="gov", decision_id="WRONG-PROJECT")

    def test_legacy_migration_requires_four_existing_active_domains(self) -> None:
        registry = core.load_json(self.paths.truth_registry)
        next(source for source in registry["sources"] if source["domain"] == "operations")["status"] = "retired"
        core.atomic_write_json(self.paths.truth_registry, registry)
        record_scoped_decision(self.paths, "USER-MIGRATE", action="truth.migrate")
        with self.assertRaisesRegex(core.VoyageError, "active required domains"):
            core.migrate_legacy_project(self.paths, actor="gov", decision_id="USER-MIGRATE")

    def test_legacy_migration_appends_without_rewriting_history(self) -> None:
        record_scoped_decision(self.paths, "USER-MIGRATE", action="truth.migrate")
        before = self.paths.ledger.read_bytes()
        event = core.migrate_legacy_project(self.paths, actor="gov", decision_id="USER-MIGRATE")
        after = self.paths.ledger.read_bytes()
        self.assertTrue(after.startswith(before))
        self.assertEqual(event["type"], "project.migrated")
        self.assertEqual(event["authorization"], "USER-MIGRATE")

    def test_legacy_migration_sets_operational_and_unblocks_writes(self) -> None:
        record_scoped_decision(self.paths, "USER-MIGRATE", action="truth.migrate")
        core.migrate_legacy_project(self.paths, actor="gov", decision_id="USER-MIGRATE")
        self.assertEqual(core.load_json(self.paths.manifest)["project_stage"], "operational")
        self.assertEqual(core.recovery_snapshot(self.paths)["project_stage"], "operational")
        core.append_event(
            self.paths,
            actor="gov",
            loop="governance",
            event_type="work.created",
            subject="W-1",
            risk="standard",
            payload={"title": "Legacy", "scope": "test", "acceptance": ["allowed"]},
        )

    def test_already_staged_project_cannot_use_legacy_migration(self) -> None:
        fresh = self.root / "fresh"
        paths = core.initialize_project(fresh, "fresh")
        record_scoped_decision(paths, "USER-MIGRATE", action="truth.migrate")
        with self.assertRaisesRegex(core.VoyageError, "only for v0.1 legacy"):
            core.migrate_legacy_project(paths, actor="gov", decision_id="USER-MIGRATE")


class BootstrapCliAndDocsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_cli(self, *arguments: str, expected: int = 0) -> dict:
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *arguments],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, expected, msg=f"stdout={result.stdout}\nstderr={result.stderr}")
        self.assertNotIn("Traceback", result.stderr)
        return json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}

    def init_and_review(self) -> core.ProjectPaths:
        self.run_cli("init", "--project-id", "cli-bootstrap")
        paths = core.project_paths(self.root)
        reviewed_contracts(paths)
        return paths

    def record_cli_decision(self, decision_id: str, *, action: str, sources: list[str]) -> None:
        payload = {
            "decision": action,
            "scope": {"actions": [action], "project_id": "cli-bootstrap", "truth_sources": sources},
        }
        self.run_cli(
            "event", "record", "--type", "decision.recorded", "--subject", decision_id,
            "--payload-json", json.dumps(payload), "--actor", "user", "--loop", "user",
        )

    def test_cli_truth_list_and_status_are_structured(self) -> None:
        self.run_cli("init", "--project-id", "cli-bootstrap")
        listed = self.run_cli("truth", "list")
        status = self.run_cli("truth", "status")
        self.assertEqual(len(listed["sources"]), 4)
        self.assertEqual(status["project_stage"], "bootstrap")
        self.assertEqual(set(status["missing_domains"]), set(REQUIRED_DOMAINS))
        self.assertIn("next_safe_action", status)

    def test_cli_truth_activate_requires_decision(self) -> None:
        paths = self.init_and_review()
        product = source_by_domain(paths, "product")
        missing = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "truth", "activate", product["id"], "--actor", "gov"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(missing.returncode, 0)
        self.assertNotIn("Traceback", missing.stderr)
        self.record_cli_decision("WRONG", action="truth.activate", sources=["another"])
        result = self.run_cli("truth", "activate", product["id"], "--decision", "WRONG", "--actor", "gov", expected=2)
        self.assertIn("does not cover truth source", result["stderr"])

    def test_cli_bootstrap_to_operational_end_to_end(self) -> None:
        paths = self.init_and_review()
        source_ids = [source["id"] for source in core.load_json(paths.truth_registry)["sources"]]
        self.record_cli_decision("USER-ALL", action="truth.activate", sources=source_ids)
        for source_id in source_ids:
            self.run_cli("truth", "activate", source_id, "--decision", "USER-ALL", "--actor", "gov")
        self.assertEqual(self.run_cli("truth", "status")["project_stage"], "operational")
        self.run_cli("work", "create", "W-1", "--title", "CLI", "--scope", "test", "--acceptance", "authorized", "--actor", "gov")
        self.run_cli("work", "authorize", "W-1", "--actor", "gov")

    def test_cli_truth_migrate_handles_legacy_project(self) -> None:
        paths = legacy_project(self.root, "cli-bootstrap")
        self.record_cli_decision("USER-MIGRATE", action="truth.migrate", sources=["*"])
        migrated = self.run_cli("truth", "migrate", "--decision", "USER-MIGRATE", "--actor", "gov")
        self.assertEqual(migrated["project_stage"], "operational")
        self.assertEqual(core.load_json(paths.manifest)["project_stage"], "operational")

    def test_skill_and_runbook_document_bootstrap_protocol(self) -> None:
        skill = (REPOSITORY / "SKILL.md").read_text(encoding="utf-8")
        runbook = (REPOSITORY / "docs" / "operations" / "runbook.md").read_text(encoding="utf-8")
        self.assertIn("bootstrap", skill.lower())
        self.assertIn("truth status", skill)
        for command in ("truth list", "truth status", "truth activate", "truth migrate"):
            self.assertIn(command, runbook)

    def test_dogfood_repository_is_explicitly_operational(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.load_json(paths.manifest)["project_stage"], "operational")
        self.assertEqual(core.recovery_snapshot(paths)["project_stage"], "operational")
        self.assertTrue(any(event["type"] == "project.migrated" for event in core.load_events(paths.ledger)))

    def test_manifest_and_registry_schemas_accept_bootstrap_and_legacy(self) -> None:
        paths = core.initialize_project(self.root, "schema-bootstrap")
        manifest = core.load_json(paths.manifest)
        self.assertEqual(schema_errors("manifest", manifest), [])
        legacy = copy.deepcopy(manifest)
        del legacy["project_stage"]
        self.assertEqual(schema_errors("manifest", legacy), [])
        self.assertEqual(schema_errors("truth-registry", core.load_json(paths.truth_registry)), [])


class RuntimeTruthConsistencyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = core.initialize_project(self.root, "runtime-consistency")
        reviewed_contracts(self.paths)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_validate_reports_manifest_stage_drift(self) -> None:
        manifest = core.load_json(self.paths.manifest)
        manifest["project_stage"] = "operational"
        core.atomic_write_json(self.paths.manifest, manifest)
        errors = core.validate_project(self.paths)
        self.assertTrue(any("manifest project_stage operational" in error and "ledger-derived bootstrap" in error for error in errors), errors)

    def test_direct_activation_cannot_target_draft_registry(self) -> None:
        source = source_by_domain(self.paths, "product")
        record_scoped_decision(self.paths, "USER-DIRECT", action="truth.activate", sources=[source["id"]])
        with self.assertRaisesRegex(core.VoyageError, "activation.*draft registry source"):
            core.append_event(
                self.paths,
                actor="gov",
                loop="governance",
                event_type="truth.activated",
                subject=source["id"],
                risk="standard",
                authorization="USER-DIRECT",
                payload={
                    "source_id": source["id"],
                    "domain": source["domain"],
                    "path": source["path"],
                    "project_id": "runtime-consistency",
                    "supersedes": None,
                },
            )

    def test_direct_activation_must_match_registry_identity(self) -> None:
        source = source_by_domain(self.paths, "product")
        registry = core.load_json(self.paths.truth_registry)
        next(item for item in registry["sources"] if item["id"] == source["id"])["status"] = "active"
        core.atomic_write_json(self.paths.truth_registry, registry)
        record_scoped_decision(self.paths, "USER-DIRECT", action="truth.activate", sources=[source["id"]])
        with self.assertRaisesRegex(core.VoyageError, "activation identity does not match registry"):
            core.append_event(
                self.paths,
                actor="gov",
                loop="governance",
                event_type="truth.activated",
                subject=source["id"],
                risk="standard",
                authorization="USER-DIRECT",
                payload={
                    "source_id": source["id"],
                    "domain": source["domain"],
                    "path": "docs/not-the-registered-path.md",
                    "project_id": "runtime-consistency",
                    "supersedes": None,
                },
            )

    def test_operational_registry_requires_verified_current_sources(self) -> None:
        activate_all_truth(self.paths)
        registry = core.load_json(self.paths.truth_registry)
        current = next(item for item in registry["sources"] if item["domain"] == "product" and item["status"] == "active")
        current["status"] = "superseded"
        registry["sources"].append({
            "id": "unverified-product",
            "domain": "product",
            "path": current["path"],
            "version": "2",
            "status": "active",
        })
        core.atomic_write_json(self.paths.truth_registry, registry)
        errors = core.validate_project(self.paths)
        self.assertTrue(any("active truth source unverified-product lacks activation evidence" in error for error in errors), errors)


class OptionalTruthActivationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = core.initialize_project(self.root, "optional-truth")
        registry = core.load_json(self.paths.truth_registry)
        registry["sources"].append({
            "id": "planning",
            "domain": "planning",
            "path": "docs/voyage/planning.md",
            "version": "1",
            "status": "draft",
            "authority": "project-draft",
        })
        core.atomic_write_json(self.paths.truth_registry, registry)
        planning = self.root / "docs" / "voyage" / "planning.md"
        planning.write_text("# Planning\n\nReviewed plan.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_optional_truth_source_can_be_activated_without_changing_required_gate(self) -> None:
        record_scoped_decision(self.paths, "USER-OPTIONAL", action="truth.activate", sources=["planning"])
        core.activate_truth(self.paths, actor="gov", source_id="planning", decision_id="USER-OPTIONAL")
        status = core.truth_status(self.paths)
        source = next(item for item in status["sources"] if item["id"] == "planning")
        self.assertTrue(source["activation_verified"])
        self.assertEqual(source["status"], "active")
        self.assertEqual(status["project_stage"], "bootstrap")
        self.assertEqual(set(status["missing_domains"]), set(REQUIRED_DOMAINS))

    def test_dogfood_has_no_unverified_active_truth(self) -> None:
        status = core.truth_status(core.project_paths(REPOSITORY))
        self.assertEqual(status["unverified_active_sources"], [])


if __name__ == "__main__":
    unittest.main()
