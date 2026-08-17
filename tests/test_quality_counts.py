from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from voyage_skill.core import VoyageError, append_event, current_state, initialize_project, load_events


def delivered_project(root: Path):
    paths = initialize_project(root, "quality-counts")
    append_event(
        paths,
        actor="gov",
        loop="governance",
        event_type="work.created",
        subject="W-1",
        risk="standard",
        payload={"title": "Counts", "scope": "test", "acceptance": ["valid counts"]},
    )
    append_event(paths, actor="gov", loop="governance", event_type="work.authorized", subject="W-1", risk="standard")
    append_event(paths, actor="dev", loop="execution", event_type="work.started", subject="W-1", risk="standard")
    append_event(
        paths,
        actor="dev",
        loop="execution",
        event_type="work.delivered",
        subject="W-1",
        risk="standard",
        anchor="commit:counts",
        evidence=["test:self"],
    )
    return paths


def quality(paths, event_type: str, counts: object):
    return append_event(
        paths,
        actor="qa",
        loop="quality",
        event_type=event_type,
        subject="W-1",
        risk="standard",
        payload={"counts": counts},
        anchor="commit:counts",
        evidence=["test:independent"],
    )


class QualityCountTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.paths = delivered_project(self.root)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_core_rejects_quality_counts_that_do_not_sum(self) -> None:
        counts = {"total": 3, "passed": 2, "failed": 0, "skipped": 0, "unknown": 0}
        with self.assertRaisesRegex(VoyageError, "quality counts do not add up"):
            quality(self.paths, "quality.passed", counts)

    def test_core_rejects_negative_quality_counts(self) -> None:
        counts = {"total": 1, "passed": 2, "failed": -1, "skipped": 0, "unknown": 0}
        with self.assertRaisesRegex(VoyageError, "non-negative integer"):
            quality(self.paths, "quality.passed", counts)

    def test_core_rejects_non_integer_quality_counts(self) -> None:
        for invalid in (True, "1", 1.5):
            with self.subTest(value=invalid), tempfile.TemporaryDirectory() as directory:
                paths = delivered_project(Path(directory))
                counts = {"total": 1, "passed": invalid, "failed": 0, "skipped": 0, "unknown": 0}
                with self.assertRaisesRegex(VoyageError, "non-negative integer"):
                    quality(paths, "quality.passed", counts)

    def test_core_rejects_passing_quality_with_failed_unknown_or_skipped(self) -> None:
        for field in ("failed", "unknown", "skipped"):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                paths = delivered_project(Path(directory))
                counts = {"total": 2, "passed": 1, "failed": 0, "skipped": 0, "unknown": 0}
                counts[field] = 1
                with self.assertRaisesRegex(VoyageError, "passing independent quality"):
                    quality(paths, "quality.passed", counts)

    def test_core_accepts_complete_passing_quality_counts(self) -> None:
        counts = {"total": 3, "passed": 3, "failed": 0, "skipped": 0, "unknown": 0}
        quality(self.paths, "quality.passed", counts)
        gate = current_state(self.paths)["gates"]["W-1"]["independent-quality"]
        self.assertEqual(gate["counts"], counts)
        self.assertEqual(gate["verdict"], "pass")

    def test_core_accepts_complete_rejection_counts(self) -> None:
        counts = {"total": 3, "passed": 2, "failed": 1, "skipped": 0, "unknown": 0}
        quality(self.paths, "quality.rejected", counts)
        state = current_state(self.paths)
        self.assertEqual(state["works"]["W-1"]["status"], "rejected")
        self.assertEqual(state["gates"]["W-1"]["independent-quality"]["counts"], counts)

    def test_core_rejects_rejection_without_failure_or_unknown(self) -> None:
        counts = {"total": 1, "passed": 0, "failed": 0, "skipped": 1, "unknown": 0}
        with self.assertRaisesRegex(VoyageError, "rejected quality requires failed or unknown"):
            quality(self.paths, "quality.rejected", counts)

    def test_failed_append_does_not_advance_ledger_head(self) -> None:
        before = load_events(self.paths.ledger)
        counts = {"total": 3, "passed": 2, "failed": 0, "skipped": 0, "unknown": 0}
        with self.assertRaises(VoyageError):
            quality(self.paths, "quality.passed", counts)
        after = load_events(self.paths.ledger)
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
