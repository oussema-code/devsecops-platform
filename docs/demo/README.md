# Demo

`demo.gif` is a condensed replay of recorded output from two real runs:

- `scripts/finish-platform.sh` on 2026-11-07: Kyverno admission proofs, worker-loss
  drill, final verification.
- `scripts/canary-drill.py` on 2026-11-06: production canary abort and promotion.

The lines are copied from those logs. Long image references are shortened, 23 identical
`checkout OK` lines are summarised, and pauses are compressed (the worker-loss drill
took 8 minutes). Regenerate with `python3 docs/demo/render_demo.py` (needs Pillow).
