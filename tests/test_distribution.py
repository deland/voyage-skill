from __future__ import annotations

import configparser
import json
import os
import re
import sys
import tempfile
import time
import unittest
from pathlib import Path

from tests.distribution_support import (
    isolated_source_copy,
    run_black_box,
    sanitized_environment,
    temporary_distribution_workspace,
    tree_snapshot,
)


REPOSITORY = Path(__file__).resolve().parents[1]


class DistributionContractTests(unittest.TestCase):
    def test_packaging_metadata_has_one_version_and_supported_python_floor(self) -> None:
        config = configparser.ConfigParser()
        config.read(REPOSITORY / "setup.cfg", encoding="utf-8")
        package_version = config["metadata"]["version"].strip()
        python_floor = config["options"]["python_requires"].strip()
        module = (REPOSITORY / "src" / "voyage_skill" / "__init__.py").read_text(encoding="utf-8")
        versions = re.findall(r'^__version__\s*=\s*["\']([^"\']+)["\']$', module, flags=re.MULTILINE)
        self.assertEqual(versions, [package_version])
        self.assertEqual(python_floor, ">=3.9")
        self.assertNotRegex((REPOSITORY / "pyproject.toml").read_text(encoding="utf-8"), r"(?m)^version\s*=")

    def test_console_entrypoint_and_source_script_target_the_same_cli(self) -> None:
        config = configparser.ConfigParser()
        config.read(REPOSITORY / "setup.cfg", encoding="utf-8")
        entries = {
            name.strip(): target.strip()
            for name, target in (
                line.split("=", 1)
                for line in config["options.entry_points"]["console_scripts"].splitlines()
                if "=" in line
            )
        }
        self.assertEqual(entries["voyage"], "voyage_skill.cli:main")
        module_entry = (REPOSITORY / "src" / "voyage_skill" / "__main__.py").read_text(encoding="utf-8")
        script_entry = (REPOSITORY / "scripts" / "voyage.py").read_text(encoding="utf-8")
        self.assertIn("from .cli import main", module_entry)
        self.assertIn("from voyage_skill.cli import main", script_entry)
        self.assertIn("raise SystemExit(main())", module_entry)
        self.assertIn("raise SystemExit(main())", script_entry)

    def test_runtime_dependency_contract_is_empty_and_build_requirements_are_explicit(self) -> None:
        config = configparser.ConfigParser(allow_no_value=True)
        config.read(REPOSITORY / "setup.cfg", encoding="utf-8")
        self.assertNotIn("install_requires", config["options"])
        pyproject = (REPOSITORY / "pyproject.toml").read_text(encoding="utf-8")
        self.assertRegex(pyproject, r'(?s)\[build-system\].*requires\s*=\s*\[[^\]]+\]')
        self.assertIn("build-backend = \"setuptools.build_meta\"", pyproject)

    def test_skill_metadata_is_valid_progressive_and_distribution_neutral(self) -> None:
        skill = (REPOSITORY / "SKILL.md").read_text(encoding="utf-8")
        frontmatter = re.match(r"^---\n(.*?)\n---", skill, flags=re.DOTALL)
        self.assertIsNotNone(frontmatter)
        self.assertEqual(set(re.findall(r"^([a-z-]+):", frontmatter.group(1), flags=re.MULTILINE)), {"name", "description"})
        self.assertLessEqual(len(skill.splitlines()), 150)
        self.assertIn("installed `voyage`", skill)
        self.assertIn("checkout script", skill)
        self.assertNotIn(str(REPOSITORY), skill)

    def test_release_contract_decision_is_registered_and_active(self) -> None:
        decision = REPOSITORY / "docs" / "decisions" / "D-0003-distribution-contract.md"
        self.assertTrue(decision.is_file())
        content = decision.read_text(encoding="utf-8")
        self.assertIn("- Status: active", content)
        self.assertIn("D-0003", (REPOSITORY / "docs" / "decisions" / "index.md").read_text(encoding="utf-8"))

    def test_decision_index_version_matches_registered_truth_version(self) -> None:
        index = (REPOSITORY / "docs" / "decisions" / "index.md").read_text(encoding="utf-8")
        declared = re.search(r"^- Version:\s*([^\s]+)\s*$", index, flags=re.MULTILINE)
        self.assertIsNotNone(declared)
        registry = json.loads((REPOSITORY / "docs" / "truth-registry.json").read_text(encoding="utf-8"))
        sources = [source for source in registry["sources"] if source.get("id") == "decision-log"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["version"], declared.group(1))

    def test_active_truth_defines_two_distribution_surfaces_and_user_publish_boundary(self) -> None:
        product = (REPOSITORY / "docs" / "product" / "contract.md").read_text(encoding="utf-8")
        operations = (REPOSITORY / "docs" / "operations" / "runbook.md").read_text(encoding="utf-8")
        decision_path = REPOSITORY / "docs" / "decisions" / "D-0003-distribution-contract.md"
        self.assertTrue(decision_path.is_file())
        decision = decision_path.read_text(encoding="utf-8")
        for content in (product, operations, decision):
            self.assertIn("source-checkout Skill bundle", content)
            self.assertIn("installable CLI artifact", content)
            self.assertIn("User authorization", content)


class DistributionHarnessTests(unittest.TestCase):
    def test_isolated_source_copy_contains_only_tracked_commit_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            destination = Path(directory) / "source"
            copied = isolated_source_copy(REPOSITORY, destination, "HEAD")
            self.assertEqual(copied, destination.resolve())
            self.assertTrue((copied / "SKILL.md").is_file())
            self.assertFalse((copied / ".git").exists())
            self.assertFalse((copied / "untracked-sentinel").exists())

    def test_black_box_environment_removes_pythonpath_and_uses_unrelated_cwd(self) -> None:
        env = sanitized_environment({"PATH": os.environ.get("PATH", ""), "PYTHONPATH": "leak", "PYTHONHOME": "leak"})
        self.assertNotIn("PYTHONPATH", env)
        self.assertNotIn("PYTHONHOME", env)
        self.assertIn("PATH", env)
        with tempfile.TemporaryDirectory() as directory:
            cwd = Path(directory)
            result = run_black_box([sys.executable, "-c", "import os; print(os.getcwd())"], cwd=cwd, env=env, timeout=5)
            self.assertEqual(result.exit_code, 0)
            self.assertEqual(Path(result.stdout.strip()), cwd.resolve())
            self.assertFalse(cwd.is_relative_to(REPOSITORY))

    def test_black_box_runner_captures_argv_exit_stdout_stderr_and_duration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            argv = [sys.executable, "-c", "import sys; print('out'); print('err', file=sys.stderr); raise SystemExit(7)"]
            result = run_black_box(argv, cwd=Path(directory), env=sanitized_environment(), timeout=5)
        self.assertEqual(result.argv, tuple(argv))
        self.assertEqual(result.exit_code, 7)
        self.assertEqual(result.stdout, "out\n")
        self.assertEqual(result.stderr, "err\n")
        self.assertGreaterEqual(result.duration_seconds, 0)
        self.assertFalse(result.timed_out)

    def test_black_box_runner_reports_timeout_without_orphan_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            started = time.monotonic()
            result = run_black_box(
                [sys.executable, "-c", "import time; time.sleep(2)"],
                cwd=Path(directory),
                env=sanitized_environment(),
                timeout=0.05,
            )
        self.assertTrue(result.timed_out)
        self.assertIsNone(result.exit_code)
        self.assertGreaterEqual(result.duration_seconds, 0)
        self.assertLess(time.monotonic() - started, 1.5)
        self.assertIn("timed out", result.stderr.lower())

    def test_tree_digest_detects_generated_or_mutated_source_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tracked = root / "tracked.txt"
            tracked.write_text("one\n", encoding="utf-8")
            first = tree_snapshot(root)
            tracked.write_text("two\n", encoding="utf-8")
            (root / "generated.bin").write_bytes(b"generated")
            second = tree_snapshot(root)
            self.assertNotEqual(first, second)
            self.assertEqual(set(first), {"tracked.txt"})
            self.assertEqual(set(second), {"generated.bin", "tracked.txt"})
            self.assertNotEqual(first["tracked.txt"], second["tracked.txt"])

    def test_temporary_distribution_workspace_is_outside_repository_and_disposable(self) -> None:
        context = temporary_distribution_workspace(REPOSITORY)
        with context as workspace:
            resolved = workspace.resolve()
            self.assertFalse(resolved.is_relative_to(REPOSITORY.resolve()))
            (resolved / "sentinel").write_text("temporary", encoding="utf-8")
            self.assertTrue(resolved.is_dir())
        self.assertFalse(resolved.exists())


if __name__ == "__main__":
    unittest.main()
