from __future__ import annotations

import platform
import statistics
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from .core import SCHEMA_VERSION, canonical_json, content_hash, load_events, replay_events, validate_hash_chain


BENCHMARK_SCHEMA_VERSION = 1
DEFAULT_EVENT_COUNTS = (1_000, 10_000, 100_000)
SNAPSHOT_REVIEW_EVENT_COUNT = 100_000
SNAPSHOT_REVIEW_SECONDS = 2.0
SNAPSHOT_REVIEW_BYTES = 256 * 1024 * 1024


def benchmark_policy_view() -> dict[str, Any]:
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "default_event_counts": list(DEFAULT_EVENT_COUNTS),
        "phases": ["load", "hash", "replay"],
        "snapshot_review": {
            "target_event_count": SNAPSHOT_REVIEW_EVENT_COUNT,
            "max_median_seconds": SNAPSHOT_REVIEW_SECONDS,
            "max_ledger_bytes": SNAPSHOT_REVIEW_BYTES,
            "automatic": False,
        },
    }


def _synthetic_events(count: int) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    previous_hash: str | None = None
    for index in range(count):
        initialized = index == 0
        event = {
            "schema_version": SCHEMA_VERSION,
            "event_id": f"evt-benchmark-{index:08d}",
            "timestamp": "2026-01-01T00:00:00Z",
            "actor": "voyage-system" if initialized else "benchmark-probe",
            "loop": "system",
            "type": "project.initialized" if initialized else "observation.recorded",
            "subject": "benchmark" if initialized else f"observation:{index}",
            "risk": "standard",
            "caused_by": None,
            "payload": (
                {"schema_version": SCHEMA_VERSION, "project_stage": "bootstrap", "extension_mode": "explicit"}
                if initialized
                else {"sequence": index}
            ),
            "evidence": [] if initialized else ["legacy:synthetic-benchmark"],
            "anchor": None,
            "authorization": None,
            "prev_hash": previous_hash,
        }
        event["hash"] = content_hash(event)
        events.append(event)
        previous_hash = event["hash"]
    return events


def assess_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    target = next((row for row in rows if row.get("event_count") == SNAPSHOT_REVIEW_EVENT_COUNT), None)
    if target is None:
        return {
            "status": "insufficient-data",
            "reasons": ["target-sample-missing"],
            "creates_snapshot": False,
            "next_safe_action": f"run the {SNAPSHOT_REVIEW_EVENT_COUNT}-event benchmark sample",
        }
    reasons: list[str] = []
    medians = target.get("medians") if isinstance(target.get("medians"), dict) else {}
    total_seconds = medians.get("total_seconds")
    ledger_bytes = target.get("ledger_bytes")
    valid_target = (
        type(total_seconds) in {int, float}
        and total_seconds >= 0
        and type(ledger_bytes) is int
        and ledger_bytes > 0
        and target.get("chain_errors") == 0
        and target.get("head_matches") is True
    )
    if not valid_target:
        return {
            "status": "insufficient-data",
            "reasons": ["target-sample-invalid"],
            "creates_snapshot": False,
            "next_safe_action": f"rerun a valid {SNAPSHOT_REVIEW_EVENT_COUNT}-event benchmark sample",
        }
    if total_seconds >= SNAPSHOT_REVIEW_SECONDS:
        reasons.append("time-threshold")
    if ledger_bytes >= SNAPSHOT_REVIEW_BYTES:
        reasons.append("size-threshold")
    if reasons:
        return {
            "status": "investigate-snapshot",
            "reasons": reasons,
            "creates_snapshot": False,
            "next_safe_action": "open a separate User-approved snapshot design and verification work item",
        }
    return {
        "status": "retain-full-replay",
        "reasons": [],
        "creates_snapshot": False,
        "next_safe_action": "continue authoritative full-ledger validation and replay",
    }


def _validated_counts(event_counts: list[int] | tuple[int, ...], runs: int) -> list[int]:
    if type(runs) is not int or runs <= 0:
        raise ValueError("runs must be a positive integer")
    if not event_counts:
        raise ValueError("at least one event count is required")
    counts = sorted(set(event_counts))
    if any(type(count) is not int or count <= 0 for count in counts):
        raise ValueError("event counts must be positive integers")
    return counts


def run_benchmark(*, event_counts: list[int] | tuple[int, ...] = DEFAULT_EVENT_COUNTS, runs: int = 3) -> dict[str, Any]:
    counts = _validated_counts(event_counts, runs)
    rows: list[dict[str, Any]] = []
    for count in counts:
        events = _synthetic_events(count)
        with tempfile.TemporaryDirectory(prefix="voyage-ledger-benchmark-") as directory:
            ledger = Path(directory) / "events.jsonl"
            ledger.write_text("".join(canonical_json(event) + "\n" for event in events), encoding="utf-8")
            samples: list[dict[str, Any]] = []
            chain_errors = 0
            head_matches = True
            for _ in range(runs):
                started = time.perf_counter()
                loaded = load_events(ledger)
                loaded_at = time.perf_counter()
                errors = validate_hash_chain(loaded)
                hashed_at = time.perf_counter()
                state = replay_events(loaded, resources={"resources": []}, gates={"gates": []})
                replayed_at = time.perf_counter()
                chain_errors += len(errors)
                head_matches = head_matches and state["last_event"] == events[-1]["event_id"]
                samples.append({
                    "load_seconds": loaded_at - started,
                    "hash_seconds": hashed_at - loaded_at,
                    "replay_seconds": replayed_at - hashed_at,
                    "total_seconds": replayed_at - started,
                })
            medians = {
                field: statistics.median(sample[field] for sample in samples)
                for field in ("load_seconds", "hash_seconds", "replay_seconds", "total_seconds")
            }
            rows.append({
                "event_count": count,
                "ledger_bytes": ledger.stat().st_size,
                "runs": runs,
                "samples": samples,
                "medians": medians,
                "chain_errors": chain_errors,
                "head_matches": head_matches,
            })
    return {
        "schema_version": BENCHMARK_SCHEMA_VERSION,
        "platform": platform.platform(),
        "python": sys.version.split()[0],
        "policy": benchmark_policy_view(),
        "rows": rows,
        "decision": assess_rows(rows),
    }
