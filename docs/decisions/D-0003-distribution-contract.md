# D-0003: Distribution and release authority

- Status: active
- Decider: User
- Decided: 2026-08-19
- Scope: PLAN-0002 real-world adoption and release hardening
- Supersedes: none

VoyageSkill has two supported distribution surfaces:

1. The **source-checkout Skill bundle** contains the stable `SKILL.md` entry,
   agent metadata, deterministic scripts, Python source, and the repository
   contracts needed to develop and validate the Skill. It is invoked directly
   from one immutable checkout.
2. The **installable CLI artifact** contains the Python runtime and exposes the
   `voyage` console command. It must not include project-specific truth,
   dogfood ledger state, tests, research input, or generated release reports.

Build requirements and runtime requirements are separate contracts. A source
build may require explicitly declared packaging tools. The installed runtime
continues to require only the supported Python standard library; build tools
must not be represented as runtime dependencies.

Both surfaces must resolve to the same CLI behavior and version. Their
acceptance evidence must bind an immutable source commit, artifact digest,
interpreter, complete test counts, and real command readback. Generated build
artifacts and release reports are disposable evidence, never a source of
project truth.

Local artifact construction and verification are authorized by PLAN-0002.
Uploading a package, creating a remote tag or release, signing an artifact,
enabling an optional extension, or changing the supported trust boundary still
requires separate, scoped User authorization. A passing release report cannot
grant that authorization.
