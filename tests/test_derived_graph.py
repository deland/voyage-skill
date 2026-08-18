from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import voyage_skill.core as core

from tests.support import legacy_project, operational_project, typed_artifact_anchor, typed_command_evidence
from tests.test_contracts import schema_errors


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"
SKILL = REPOSITORY / "SKILL.md"
GRAPH_TRUTH = REPOSITORY / "docs" / "system" / "graph.md"
RUNBOOK = REPOSITORY / "docs" / "operations" / "runbook.md"
NODE_FIELDS = {
    "id", "type", "schema_version", "status", "scope", "authority",
    "risk", "evidence", "provenance", "supersedes", "attributes",
}
EDGE_FIELDS = {
    "id", "type", "schema_version", "source", "target", "status",
    "authority", "evidence", "provenance", "attributes",
}


def control_snapshot(paths: core.ProjectPaths) -> dict[str, str]:
    return {
        str(path.relative_to(paths.control)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths.control.rglob("*"))
        if path.is_file()
    }


def rewrite_events(paths: core.ProjectPaths, mutate) -> None:
    events = core.load_events(paths.ledger)
    mutate(events)
    previous = None
    for event in events:
        event["prev_hash"] = previous
        event["hash"] = core.content_hash({key: value for key, value in event.items() if key != "hash"})
        previous = event["hash"]
    paths.ledger.write_text("".join(core.canonical_json(event) + "\n" for event in events), encoding="utf-8")


class DerivedGraphTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = operational_project(self.root, "graph-example")
        self.classification = typed_command_evidence(self.paths, name="graph-classification", producer="gov")
        self.execution = typed_command_evidence(self.paths, name="graph-execution", producer="dev")
        self.quality = typed_command_evidence(self.paths, name="graph-quality", producer="qa")

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

    def extension_decision(
        self,
        decision_id: str,
        *,
        action: str = "extension.enable",
        extension_id: str = "derived-graph",
        version: str = "1.0.0",
        project_id: str = "graph-example",
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

    def enable_graph(self, *, decision_id: str = "USER-ENABLE-GRAPH") -> None:
        self.extension_decision(decision_id)
        core.enable_extension(
            self.paths,
            actor="gov",
            extension_id="derived-graph",
            version="1.0.0",
            decision_id=decision_id,
        )

    def disable_graph(self, *, decision_id: str = "USER-DISABLE-GRAPH") -> None:
        self.extension_decision(decision_id, action="extension.disable")
        core.disable_extension(
            self.paths,
            actor="gov",
            extension_id="derived-graph",
            version="1.0.0",
            decision_id=decision_id,
        )

    def create_work(self, work_id: str, *, dependencies: list[str] | None = None, resources: list[str] | None = None) -> None:
        self.event(
            "work.created",
            work_id,
            actor="gov",
            loop="governance",
            evidence=[self.classification],
            payload={
                "title": work_id,
                "scope": "derived graph test",
                "acceptance": ["graph trace exists"],
                "dependencies": dependencies or [],
                "required_resources": resources or [],
            },
        )

    def start_work(self, work_id: str) -> None:
        self.event("work.authorized", work_id, actor="gov", loop="governance")
        self.event("work.started", work_id, actor="dev", loop="execution")

    def deliver(self, work_id: str, name: str) -> tuple[dict, str]:
        anchor = typed_artifact_anchor(self.paths, name=name)
        delivered = self.event(
            "work.delivered",
            work_id,
            actor="dev",
            loop="execution",
            anchor=anchor,
            evidence=[self.execution],
        )
        return delivered, anchor

    def quality_verdict(self, work_id: str, anchor: str, *, passed: bool) -> None:
        self.event(
            "quality.passed" if passed else "quality.rejected",
            work_id,
            actor="qa",
            loop="quality",
            anchor=anchor,
            evidence=[self.quality],
            payload={
                "counts": {
                    "total": 1,
                    "passed": 1 if passed else 0,
                    "failed": 0 if passed else 1,
                    "skipped": 0,
                    "unknown": 0,
                }
            },
        )

    def run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), *args],
            text=True,
            capture_output=True,
            check=False,
        )


class GraphExtensionAccessTests(DerivedGraphTestCase):
    def test_derived_graph_catalog_is_available_with_stable_empty_additive_contract(self) -> None:
        self.assertEqual(len(core.EXTENSION_CATALOG), 6)
        contract = core.EXTENSION_CATALOG["derived-graph"]
        self.assertEqual(contract["version"], "1.0.0")
        self.assertEqual(contract["availability"], "available")
        for field in ("event_types", "node_types", "edge_types", "gates"):
            self.assertEqual(contract[field], ())

    def test_graph_queries_require_explicit_enabled_extension(self) -> None:
        before = self.paths.ledger.read_bytes()
        for operation in (
            lambda: core.derive_graph(self.paths),
            lambda: core.check_graph(self.paths),
            lambda: core.graph_path(self.paths, "project:graph-example", "loop:audit"),
        ):
            with self.subTest(operation=operation):
                with self.assertRaisesRegex(core.VoyageError, "derived-graph.*enabled"):
                    operation()
        self.assertEqual(self.paths.ledger.read_bytes(), before)

        with tempfile.TemporaryDirectory() as temporary:
            legacy_paths = legacy_project(Path(temporary), "legacy-graph")
            legacy_before = legacy_paths.ledger.read_bytes()
            with self.assertRaisesRegex(core.VoyageError, "derived-graph.*enabled"):
                core.derive_graph(legacy_paths)
            self.assertEqual(legacy_paths.ledger.read_bytes(), legacy_before)

    def test_derived_graph_enable_requires_exact_user_scope(self) -> None:
        cases = (
            ("wrong-action", "extension.disable", "derived-graph", "1.0.0", "graph-example"),
            ("wrong-extension", "extension.enable", "channel-tracking", "1.0.0", "graph-example"),
            ("wrong-version", "extension.enable", "derived-graph", "2.0.0", "graph-example"),
            ("wrong-project", "extension.enable", "derived-graph", "1.0.0", "other"),
        )
        for decision_id, action, extension_id, version, project_id in cases:
            with self.subTest(decision_id=decision_id):
                self.extension_decision(
                    decision_id,
                    action=action,
                    extension_id=extension_id,
                    version=version,
                    project_id=project_id,
                )
                with self.assertRaises(core.VoyageError):
                    core.enable_extension(
                        self.paths,
                        actor="gov",
                        extension_id="derived-graph",
                        version="1.0.0",
                        decision_id=decision_id,
                    )
        self.extension_decision("revoked")
        self.event("decision.revoked", "revoked", actor="user", loop="user", payload={"reason": "withdrawn"})
        with self.assertRaisesRegex(core.VoyageError, "revoked"):
            core.enable_extension(
                self.paths,
                actor="gov",
                extension_id="derived-graph",
                version="1.0.0",
                decision_id="revoked",
            )

    def test_disable_revokes_graph_query_access_without_deleting_history(self) -> None:
        self.enable_graph()
        self.assertEqual(core.derive_graph(self.paths)["project_id"], "graph-example")
        self.disable_graph()
        with self.assertRaisesRegex(core.VoyageError, "derived-graph.*enabled"):
            core.derive_graph(self.paths)
        state = core.current_state(self.paths)["extensions"]["derived-graph"]
        self.assertEqual(state["status"], "disabled")
        self.assertEqual([item["type"] for item in state["history"]], ["extension.enabled", "extension.disabled"])

    def test_graph_access_checks_do_not_create_control_files_or_events(self) -> None:
        before = control_snapshot(self.paths)
        with self.assertRaises(core.VoyageError):
            core.derive_graph(self.paths)
        self.assertEqual(control_snapshot(self.paths), before)
        self.enable_graph()
        enabled = control_snapshot(self.paths)
        core.derive_graph(self.paths)
        core.check_graph(self.paths)
        self.assertEqual(control_snapshot(self.paths), enabled)
        self.assertFalse(any("derived" in path.name or "index" in path.name for path in self.paths.control.iterdir()))


class GraphDerivationTests(DerivedGraphTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enable_graph()

    def test_derive_is_byte_deterministic_and_fingerprint_bound_to_registered_inputs(self) -> None:
        first = core.derive_graph(self.paths)
        second = core.derive_graph(self.paths)
        self.assertEqual(core.canonical_json(first), core.canonical_json(second))
        self.assertNotIn("generated_at", first)
        self.assertEqual(
            set(first["source_fingerprints"]),
            {"manifest", "truth_registry", "graph", "resources", "gates", "ledger", "evidence"},
        )
        core.register_resource(
            self.paths,
            actor="gov",
            resource_id="file:fingerprint",
            resource_type="file",
            mode="rebuildable",
        )
        changed = core.derive_graph(self.paths)
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])

    def test_derive_projects_project_truth_loops_principals_decisions_and_work(self) -> None:
        self.create_work("W-1")
        graph = core.derive_graph(self.paths)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertIn("project:graph-example", nodes)
        for loop in core.KERNEL_LOOPS:
            self.assertEqual(nodes[f"loop:{loop}"]["type"], "loop-binding")
        registry = core.load_json(self.paths.truth_registry)
        for source in registry["sources"]:
            if source.get("status") == "active":
                self.assertEqual(nodes[f"truth:{source['id']}"]["type"], "truth-source")
        self.assertIn("decision:USER-ENABLE-GRAPH", nodes)
        self.assertIn("principal:user", nodes)
        self.assertIn("principal:gov", nodes)
        self.assertEqual(nodes["work:W-1"]["type"], "work-item")
        for node in nodes.values():
            self.assertEqual(set(node), NODE_FIELDS)

    def test_derive_traces_every_delivery_anchor_evidence_and_gate_result(self) -> None:
        self.create_work("W-DELIVERY")
        self.start_work("W-DELIVERY")
        first_event, first_anchor = self.deliver("W-DELIVERY", "graph-first")
        self.quality_verdict("W-DELIVERY", first_anchor, passed=False)
        self.event("work.started", "W-DELIVERY", actor="dev", loop="execution")
        second_event, second_anchor = self.deliver("W-DELIVERY", "graph-second")
        self.quality_verdict("W-DELIVERY", second_anchor, passed=True)
        graph = core.derive_graph(self.paths)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes[f"delivery:{first_event['event_id']}"]["status"], "superseded")
        self.assertEqual(nodes[f"delivery:{second_event['event_id']}"]["status"], "current")
        self.assertIn(f"anchor:{first_anchor}", nodes)
        self.assertIn(f"anchor:{second_anchor}", nodes)
        self.assertIn(f"evidence:{self.execution}", nodes)
        self.assertIn(f"evidence:{self.quality}", nodes)
        edges = graph["edges"]
        self.assertTrue(any(edge["type"] == "delivered-via" and edge["target"] == f"delivery:{second_event['event_id']}" for edge in edges))
        self.assertTrue(any(edge["type"] == "anchored-at" and edge["target"] == f"anchor:{second_anchor}" for edge in edges))
        self.assertTrue(any(edge["type"] == "validated-by" and edge["target"] == "gate:independent-quality" for edge in edges))

    def test_derive_traces_resources_historical_leases_and_release_state(self) -> None:
        resource_id = "file:graph"
        core.register_resource(
            self.paths,
            actor="gov",
            resource_id=resource_id,
            resource_type="file",
            mode="rebuildable",
        )
        self.create_work("W-RESOURCE", resources=[resource_id])
        self.event("work.authorized", "W-RESOURCE", actor="gov", loop="governance")
        self.event(
            "resource.claimed",
            resource_id,
            actor="dev",
            loop="execution",
            evidence=[self.execution],
            payload={
                "resource_id": resource_id,
                "lease_id": "L-GRAPH",
                "work_id": "W-RESOURCE",
                "expires_at": "2099-01-01T00:00:00Z",
            },
        )
        self.event(
            "resource.released",
            resource_id,
            actor="dev",
            loop="execution",
            payload={"resource_id": resource_id, "lease_id": "L-GRAPH"},
        )
        graph = core.derive_graph(self.paths)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes[f"resource:{resource_id}"]["type"], "resource")
        self.assertEqual(nodes["lease:L-GRAPH"]["status"], "released")
        self.assertEqual(nodes["lease:L-GRAPH"]["evidence"], [self.execution])
        edges = graph["edges"]
        self.assertTrue(any(edge["type"] == "claims" and edge["source"] == "work:W-RESOURCE" and edge["target"] == "lease:L-GRAPH" for edge in edges))
        self.assertTrue(any(edge["type"] == "releases" and edge["source"] == "lease:L-GRAPH" and edge["target"] == f"resource:{resource_id}" for edge in edges))

    def test_derive_traces_rules_supersession_blocks_and_appeal_targets(self) -> None:
        for rule_id in ("R-1", "R-2"):
            self.event(
                "rule.proposed",
                rule_id,
                actor=f"proposer-{rule_id}",
                loop="audit",
                payload={"scope": "test", "source": "finding", "cost": "low", "verification": "test", "retirement": "manual"},
            )
            self.event("rule.approved", rule_id, actor=f"approver-{rule_id}", loop="governance")
            self.event("rule.applied", rule_id, actor=f"applier-{rule_id}", loop="governance", evidence=[self.execution])
            self.event("rule.verified", rule_id, actor=f"verifier-{rule_id}", loop="quality", evidence=[self.quality])
        self.event(
            "rule.superseded",
            "R-1",
            actor="gov",
            loop="governance",
            evidence=[self.quality],
            payload={"replacement": "R-2"},
        )
        self.create_work("W-BLOCK")
        self.event(
            "work.blocked",
            "W-BLOCK",
            actor="auditor",
            loop="audit",
            evidence=[self.quality],
            payload={
                "block_id": "B-1",
                "reason": "unsafe",
                "scope": "W-BLOCK",
                "unblock_condition": "independent evidence",
                "appeal_to": "resolver",
            },
        )
        graph = core.derive_graph(self.paths)
        nodes = {node["id"]: node for node in graph["nodes"]}
        self.assertEqual(nodes["rule:R-1"]["status"], "superseded")
        self.assertEqual(nodes["rule:R-1"]["supersedes"], "rule:R-2")
        self.assertEqual(nodes["block:B-1"]["status"], "active")
        self.assertIn("principal:resolver", nodes)
        self.assertTrue(any(edge["type"] == "supersedes" and edge["source"] == "rule:R-1" and edge["target"] == "rule:R-2" for edge in graph["edges"]))
        self.assertTrue(any(edge["type"] == "blocks" and edge["source"] == "block:B-1" and edge["target"] == "work:W-BLOCK" for edge in graph["edges"]))
        self.assertTrue(any(edge["type"] == "escalates-to" and edge["source"] == "block:B-1" and edge["target"] == "principal:resolver" for edge in graph["edges"]))

    def test_derived_ids_types_sorting_and_schema_are_exact(self) -> None:
        self.create_work("W-SCHEMA")
        graph = core.derive_graph(self.paths)
        self.assertEqual(graph["schema_version"], 1)
        node_ids = [node["id"] for node in graph["nodes"]]
        edge_ids = [edge["id"] for edge in graph["edges"]]
        self.assertEqual(node_ids, sorted(node_ids))
        self.assertEqual(edge_ids, sorted(edge_ids))
        self.assertEqual(len(node_ids), len(set(node_ids)))
        self.assertEqual(len(edge_ids), len(set(edge_ids)))
        effective = core.effective_contract(self.paths)
        self.assertTrue({node["type"] for node in graph["nodes"]}.issubset(set(effective["node_types"])))
        self.assertTrue({edge["type"] for edge in graph["edges"]}.issubset(set(effective["edge_types"])))
        for edge in graph["edges"]:
            self.assertEqual(set(edge), EDGE_FIELDS)
        self.assertEqual(schema_errors("derived-graph", graph), [])
        damaged = copy.deepcopy(graph)
        damaged["unexpected"] = True
        self.assertTrue(schema_errors("derived-graph", damaged))


class GraphConsistencyTests(DerivedGraphTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enable_graph()

    def test_healthy_derived_graph_has_zero_errors_and_stable_summary(self) -> None:
        self.create_work("W-HEALTHY")
        first = core.check_graph(self.paths)
        second = core.check_graph(self.paths)
        self.assertTrue(first["valid"])
        self.assertEqual(first["issues"], [])
        self.assertEqual(first, second)
        self.assertEqual(first["summary"]["errors"], 0)

    def test_check_reports_hash_consistent_dangling_internal_dependency(self) -> None:
        self.create_work("W-DANGLING")

        def mutate(events: list[dict]) -> None:
            event = next(item for item in events if item["type"] == "work.created" and item["subject"] == "W-DANGLING")
            event["payload"]["dependencies"] = ["W-MISSING"]

        rewrite_events(self.paths, mutate)
        result = core.check_graph(self.paths)
        self.assertFalse(result["valid"])
        issue = next(item for item in result["issues"] if item["code"] == "dangling-reference")
        self.assertEqual(issue["subject"], "work:W-DANGLING")
        self.assertIn("work:W-MISSING", issue["related"])

    def test_check_reports_canonical_dependency_cycle(self) -> None:
        self.create_work("W-A")
        self.create_work("W-B", dependencies=["W-A"])

        def mutate(events: list[dict]) -> None:
            event = next(item for item in events if item["type"] == "work.created" and item["subject"] == "W-A")
            event["payload"]["dependencies"] = ["W-B"]

        rewrite_events(self.paths, mutate)
        result = core.check_graph(self.paths)
        cycles = [item for item in result["issues"] if item["code"] == "dependency-cycle"]
        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0]["related"], ["work:W-A", "work:W-B", "work:W-A"])

    def test_check_revalidates_current_immutable_anchor(self) -> None:
        damaged: list[tuple[str, str]] = []
        for label in ("missing", "tampered", "wrong-kind"):
            work_id = f"W-{label}"
            self.create_work(work_id)
            self.start_work(work_id)
            _, anchor = self.deliver(work_id, f"graph-{label}")
            damaged.append((work_id, anchor))
        missing_path = self.paths.evidence / "sha256" / f"{damaged[0][1].removeprefix('sha256:')}.json"
        missing_path.unlink()
        tampered_path = self.paths.evidence / "sha256" / f"{damaged[1][1].removeprefix('sha256:')}.json"
        tampered_path.write_text("{}\n", encoding="utf-8")
        wrong_kind = typed_command_evidence(self.paths, name="graph-wrong-anchor", producer="dev")

        def mutate(events: list[dict]) -> None:
            event = next(item for item in events if item["type"] == "work.delivered" and item["subject"] == "W-wrong-kind")
            event["anchor"] = wrong_kind

        rewrite_events(self.paths, mutate)
        result = core.check_graph(self.paths)
        issues = [item for item in result["issues"] if item["code"] == "invalid-anchor"]
        self.assertEqual({item["subject"] for item in issues}, {"work:W-missing", "work:W-tampered", "work:W-wrong-kind"})

    def test_check_reports_orphan_active_node_and_dangling_edge(self) -> None:
        self.create_work("W-CONNECTED")
        typed_command_evidence(self.paths, name="graph-unused", producer="tester")
        graph = core.derive_graph(self.paths)
        orphan = copy.deepcopy(next(node for node in graph["nodes"] if node["id"] == "work:W-CONNECTED"))
        orphan["id"] = "work:W-ORPHAN"
        orphan["status"] = "active"
        graph["nodes"].append(orphan)
        edge = copy.deepcopy(graph["edges"][0])
        edge["id"] = "edge:" + "f" * 64
        edge["target"] = "work:W-MISSING"
        graph["edges"].append(edge)
        result = core.check_graph(self.paths, graph=graph)
        codes = {(item["code"], item["subject"]) for item in result["issues"]}
        self.assertIn(("orphan-active-node", "work:W-ORPHAN"), codes)
        self.assertIn(("dangling-edge", edge["id"]), codes)
        self.assertFalse(any(item["code"] == "orphan-active-node" and item["subject"].startswith("evidence:") for item in result["issues"]))

    def test_check_reports_active_block_without_independent_resolution_target(self) -> None:
        for work_id, blocker, appeal_to in (
            ("W-SELF", "auditor", "auditor"),
            ("W-INDEPENDENT", "auditor", "resolver"),
        ):
            self.create_work(work_id)
            self.event(
                "work.blocked",
                work_id,
                actor=blocker,
                loop="audit",
                evidence=[self.quality],
                payload={
                    "block_id": f"B-{work_id}",
                    "reason": "unsafe",
                    "scope": work_id,
                    "unblock_condition": "new independent evidence",
                    "appeal_to": appeal_to,
                },
            )
        result = core.check_graph(self.paths)
        issues = [item for item in result["issues"] if item["code"] == "unresolvable-block"]
        self.assertEqual([item["subject"] for item in issues], ["block:B-W-SELF"])


class GraphPathTests(DerivedGraphTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enable_graph()

    def test_path_returns_deterministic_shortest_project_to_current_anchor_route(self) -> None:
        self.create_work("W-PATH")
        self.start_work("W-PATH")
        delivered, anchor = self.deliver("W-PATH", "graph-path")
        result = core.graph_path(self.paths, "project:graph-example", f"anchor:{anchor}")
        self.assertTrue(result["found"])
        self.assertEqual(
            result["nodes"],
            ["project:graph-example", "work:W-PATH", f"delivery:{delivered['event_id']}", f"anchor:{anchor}"],
        )
        self.assertEqual(result["length"], 3)
        self.assertEqual(result, core.graph_path(self.paths, "project:graph-example", f"anchor:{anchor}"))

    def test_path_traces_work_dependency_to_prerequisite(self) -> None:
        self.create_work("W-BASE")
        self.create_work("W-DEPENDENT", dependencies=["W-BASE"])
        result = core.graph_path(self.paths, "work:W-DEPENDENT", "work:W-BASE")
        self.assertTrue(result["found"])
        self.assertEqual(result["nodes"], ["work:W-DEPENDENT", "work:W-BASE"])
        self.assertEqual(result["edges"][0]["type"], "depends-on")

    def test_path_traces_block_to_work_and_independent_appeal_target(self) -> None:
        self.create_work("W-BLOCK-PATH")
        self.event(
            "work.blocked",
            "W-BLOCK-PATH",
            actor="auditor",
            loop="audit",
            evidence=[self.quality],
            payload={
                "block_id": "B-PATH",
                "reason": "unsafe",
                "scope": "W-BLOCK-PATH",
                "unblock_condition": "independent evidence",
                "appeal_to": "resolver",
            },
        )
        to_work = core.graph_path(self.paths, "block:B-PATH", "work:W-BLOCK-PATH")
        to_resolver = core.graph_path(self.paths, "block:B-PATH", "principal:resolver")
        self.assertEqual(to_work["edges"][0]["type"], "blocks")
        self.assertEqual(to_resolver["edges"][0]["type"], "escalates-to")

    def test_path_known_but_disconnected_returns_not_found_without_mutation(self) -> None:
        first = typed_command_evidence(self.paths, name="graph-disconnected-a", producer="tester")
        second = typed_command_evidence(self.paths, name="graph-disconnected-b", producer="tester")
        before = control_snapshot(self.paths)
        result = core.graph_path(self.paths, f"evidence:{first}", f"evidence:{second}")
        self.assertFalse(result["found"])
        self.assertEqual(result["nodes"], [])
        self.assertEqual(result["edges"], [])
        self.assertEqual(result["length"], 0)
        self.assertEqual(control_snapshot(self.paths), before)

    def test_path_unknown_endpoint_is_deterministic_error(self) -> None:
        with self.assertRaisesRegex(core.VoyageError, "unknown graph endpoint.*work:missing"):
            core.graph_path(self.paths, "work:missing", "project:graph-example")


class GraphCliSchemaTests(DerivedGraphTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.enable_graph()

    def test_graph_cli_reference_contains_all_leaf_commands_once(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        section = text[text.index("<!-- voyage-cli-reference:start -->"):text.index("<!-- voyage-cli-reference:end -->")]
        for command in ("voyage graph derive", "voyage graph check", "voyage graph path"):
            self.assertEqual(section.count(f"`{command}`"), 1)

    def test_graph_cli_derive_and_path_emit_stable_json(self) -> None:
        self.create_work("W-CLI-PATH")
        derived = self.run_cli("graph", "derive")
        self.assertEqual(derived.returncode, 0, derived.stderr)
        self.assertEqual(json.loads(derived.stdout), core.derive_graph(self.paths))
        path = self.run_cli("graph", "path", "project:graph-example", "work:W-CLI-PATH")
        self.assertEqual(path.returncode, 0, path.stderr)
        self.assertEqual(json.loads(path.stdout), core.graph_path(self.paths, "project:graph-example", "work:W-CLI-PATH"))

    def test_graph_cli_check_uses_exit_one_for_findings_and_json_stdout(self) -> None:
        self.create_work("W-BAD-CLI")

        def mutate(events: list[dict]) -> None:
            event = next(item for item in events if item["type"] == "work.created" and item["subject"] == "W-BAD-CLI")
            event["payload"]["dependencies"] = ["W-MISSING"]

        rewrite_events(self.paths, mutate)
        result = self.run_cli("graph", "check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertFalse(json.loads(result.stdout)["valid"])
        self.assertNotIn("Traceback", result.stderr)

        with tempfile.TemporaryDirectory() as temporary:
            other = operational_project(Path(temporary), "graph-disabled")
            denied = subprocess.run(
                [sys.executable, "-B", str(SCRIPT), "--root", str(other.root), "graph", "derive"],
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(denied.returncode, 2)

    def test_derived_graph_schema_is_exercised_by_repository_contract_tests(self) -> None:
        graph = core.derive_graph(self.paths)
        self.assertTrue((REPOSITORY / "schemas" / "derived-graph.schema.json").is_file())
        self.assertEqual(schema_errors("derived-graph", graph), [])
        contract_source = (REPOSITORY / "tests" / "test_contracts.py").read_text(encoding="utf-8")
        self.assertIn('"derived-graph"', contract_source)

    def test_all_graph_commands_are_read_only_across_ledger_and_control_tree(self) -> None:
        self.create_work("W-READ-ONLY")
        before = control_snapshot(self.paths)
        self.assertEqual(self.run_cli("graph", "derive").returncode, 0)
        self.assertEqual(self.run_cli("graph", "check").returncode, 0)
        self.assertEqual(self.run_cli("graph", "path", "work:W-READ-ONLY", "loop:audit").returncode, 1)
        self.assertEqual(control_snapshot(self.paths), before)

        def mutate(events: list[dict]) -> None:
            event = next(item for item in events if item["type"] == "work.created" and item["subject"] == "W-READ-ONLY")
            event["payload"]["dependencies"] = ["W-MISSING"]

        rewrite_events(self.paths, mutate)
        damaged = control_snapshot(self.paths)
        self.assertEqual(self.run_cli("graph", "check").returncode, 1)
        self.assertEqual(control_snapshot(self.paths), damaged)


class GraphDocsDogfoodTests(DerivedGraphTestCase):
    def test_system_truth_documents_exact_derived_graph_contract_and_issue_codes(self) -> None:
        text = GRAPH_TRUTH.read_text(encoding="utf-8")
        section = text[text.index("<!-- derived-graph-contract:start -->"):text.index("<!-- derived-graph-contract:end -->")]
        for phrase in (
            "schema_version", "source_fingerprints", "nodes", "edges", "read-only",
            "dangling-reference", "dependency-cycle", "invalid-anchor",
            "orphan-active-node", "unresolvable-block",
        ):
            self.assertIn(phrase, section)

    def test_runbook_documents_enable_derive_check_path_and_exit_semantics(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        section = text[text.index("<!-- derived-graph-operations:start -->"):text.index("<!-- derived-graph-operations:end -->")]
        for phrase in (
            "extension enable", "graph derive", "graph check", "graph path",
            "exit 1", "exit 2", "no cache", "hash-consistent",
        ):
            self.assertIn(phrase, section)

    def test_skill_loads_graph_detail_only_for_graph_tasks(self) -> None:
        text = SKILL.read_text(encoding="utf-8")
        section = text[text.index("<!-- graph-loading:start -->"):text.index("<!-- graph-loading:end -->")]
        for phrase in ("extension status", "active system", "runbook", "only", "read-only"):
            self.assertIn(phrase, section.lower())
        self.assertNotIn(".voyage/derived", section)
        self.assertNotIn("database", section.lower())

    def test_dogfood_remains_valid_recoverable_and_does_not_invent_graph_enablement(self) -> None:
        paths = core.project_paths(REPOSITORY)
        self.assertEqual(core.validate_project(paths), [])
        before = paths.ledger.read_bytes()
        status = core.extension_status(paths)
        self.assertEqual(status["mode"], "legacy-compatible")
        self.assertNotIn("derived-graph", status["enabled"])
        self.assertNotIn("derived-graph", status["reserved"])
        with self.assertRaisesRegex(core.VoyageError, "derived-graph.*enabled"):
            core.derive_graph(paths)
        self.assertEqual(paths.ledger.read_bytes(), before)
        self.assertEqual(core.recovery_snapshot(paths)["extensions"], status)

    def test_docs_and_runtime_reject_graph_database_cache_ui_and_writable_truth_claims(self) -> None:
        system = GRAPH_TRUTH.read_text(encoding="utf-8")
        section = system[system.index("<!-- derived-graph-contract:start -->"):system.index("<!-- derived-graph-contract:end -->")].lower()
        for phrase in ("no graph database", "no cache", "no graph ui", "not a source of truth"):
            self.assertIn(phrase, section)
        self.enable_graph()
        before = control_snapshot(self.paths)
        core.derive_graph(self.paths)
        self.assertEqual(control_snapshot(self.paths), before)
        self.assertFalse(any(path.name.startswith("derived") for path in self.paths.control.rglob("*")))


if __name__ == "__main__":
    unittest.main()
