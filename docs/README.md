# Documentation index

| Doc | Purpose |
|---|---|
| [architecture.md](./architecture.md) | Clean Architecture layers + twelve-analyzer registry |
| [system-design.md](./system-design.md) | End-to-end system design matching this codebase |
| [weights.md](./weights.md) | Fusion weights (must match `weights.py`) |
| [references.md](./references.md) | Verified bibliography mapped to modules |
| [research-challenges.md](./research-challenges.md) | Challenge → Solution + Status (`challenge_flags`, `failure_modes`) |
| [benchmarks.md](./benchmarks.md) | Local measured results only (no public leaderboard claims) |
| [contributing.md](./contributing.md) | How to add an analyzer / run checks |
| [naming-conventions.md](./naming-conventions.md) | File and symbol naming standards |
| [gap-analysis.md](./gap-analysis.md) | Audited bugs, missing capability, and claims to correct (2026-09-18) |

Local benchmark harness: `uv run python scripts/run_local_benchmark.py`
