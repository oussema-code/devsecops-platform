# Project working instructions

## Current working mode — 2026-11-05

The user explicitly replaced the mentoring sequence with implementation work.
Build the platform, provide architecture diagrams, and ask the user to choose
major architectural trade-offs. Do not require lessons, quizzes, or demonstrations
of understanding before implementation. Preserve the historical learning notes.
Read `docs/architecture.md` and `IMPLEMENTATION_STATUS.md` for current decisions
and verified runtime state. These instructions supersede conflicting mentoring
instructions below and in the two historical documents.

Approved: a new three-node kind cluster, preserving `devsecops-lab`; a separate
platform Git repository at the workspace root with pinned upstream app source;
Cilium networking with Hubble. Never operate on the old lab while provisioning
the platform. Always use the platform's explicit kubeconfig and context.

Before investigating, teaching, or changing this project, read:

1. [MENTORING_WORKFLOW.md](MENTORING_WORKFLOW.md) — the user's standing working method.
2. [LEARNING_PROGRESS.md](LEARNING_PROGRESS.md) — the current module, evidence of understanding, and next exercise.

Follow the mentoring workflow throughout this workspace, including `lab/` and `microservices-demo/`. Resume at the recorded learning checkpoint; do not interpret completed implementation as demonstrated understanding. Current user instructions take precedence over these files.
