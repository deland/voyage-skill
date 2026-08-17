# VoyageSkill

VoyageSkill is a project-level operating control system for long-running,
multi-agent software work. A concise Skill provides discovery and recovery;
versioned project documents and an append-only ledger remain authoritative.

The current normative sources are registered in
[`docs/truth-registry.json`](docs/truth-registry.json). Research material under
`docs/research/` is input only and is never an operational source of truth.

## Quick start

Run from a checkout without installation:

```bash
python3 -B scripts/voyage.py --root /path/to/project init --project-id example
python3 -B scripts/voyage.py --root /path/to/project validate
python3 -B scripts/voyage.py --root /path/to/project recover
```

Install the `voyage` console command with any Python 3.9+ package installer.
The runtime has no third-party dependencies.

## Development

```bash
PYTHONPATH=src python3 -B -m unittest discover -s tests -v
python3 -B scripts/voyage.py --root . validate
```
