from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SCRIPT = REPOSITORY / "scripts" / "voyage.py"


class VoyageCliTests(unittest.TestCase):
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
        return json.loads(result.stdout) if result.stdout else {"stderr": result.stderr}

    def test_cli_end_to_end_and_recovery(self) -> None:
        self.run_cli("init", "--project-id", "cli-project")
        self.run_cli("validate")
        self.run_cli("work", "create", "W-1", "--title", "CLI flow", "--scope", "temporary test project", "--acceptance", "works", "--actor", "gov")
        self.run_cli("work", "authorize", "W-1", "--actor", "gov")
        self.run_cli("work", "start", "W-1", "--actor", "dev")
        self.run_cli("work", "deliver", "W-1", "--anchor", "commit:abc", "--evidence", "self-test", "--actor", "dev")
        self.run_cli("work", "quality", "W-1", "--verdict", "pass", "--anchor", "commit:abc", "--evidence", "independent-test", "--actor", "qa")
        self.run_cli("work", "accept", "W-1", "--actor", "gov")
        self.run_cli("work", "close", "W-1", "--actor", "gov")
        recovered = self.run_cli("recover")
        self.assertEqual(recovered["work"][0]["status"], "closed")
        self.assertEqual(recovered["work"][0]["next_safe_action"], "none")

    def test_cli_rejects_self_review(self) -> None:
        self.run_cli("init", "--project-id", "cli-project")
        self.run_cli("work", "create", "W-1", "--title", "CLI flow", "--scope", "temporary test project", "--acceptance", "works", "--actor", "gov")
        self.run_cli("work", "authorize", "W-1", "--actor", "gov")
        self.run_cli("work", "start", "W-1", "--actor", "dev")
        self.run_cli("work", "deliver", "W-1", "--anchor", "commit:abc", "--evidence", "self-test", "--actor", "dev")
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--root", str(self.root), "work", "quality", "W-1", "--verdict", "pass", "--anchor", "commit:abc", "--evidence", "self-review", "--actor", "dev"],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("executor cannot issue final quality verdict", result.stderr)

    def test_cli_registers_resource_and_rejects_duplicate(self) -> None:
        self.run_cli("init", "--project-id", "cli-project")
        registered = self.run_cli(
            "resource", "register", "file:shared", "--type", "file", "--mode", "exclusive",
            "--conflict-key", "shared.txt", "--actor", "gov",
        )
        self.assertEqual(registered["registered"], "file:shared")
        result = subprocess.run(
            [
                sys.executable, "-B", str(SCRIPT), "--root", str(self.root),
                "resource", "register", "file:shared", "--type", "file", "--mode", "exclusive", "--actor", "gov",
            ],
            check=False,
            text=True,
            capture_output=True,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("resource already exists", result.stderr)


if __name__ == "__main__":
    unittest.main()
