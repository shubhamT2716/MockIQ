# 11 — Roadmap

## Phase 0 — Foundations (1–2 weeks)
- Repo, docker-compose, Postgres/Redis, auth, CI.
- Role pack schema + `backend-sde` pack (L1, L2) with ~150 reviewed seed questions.
**Exit:** packs load and validate in CI.

## Phase 1 — Text MVP (3–4 weeks)
- Resume upload & parsing.
- Planner + one round type end-to-end (Project deep-dive or HLD) in chat mode.
- Turn controller, rules engine, state machine, checkpoints.
- Evaluator (3 passes, evidence validator) + report page.
- Candidate-bot simulation tests; first 30 golden transcripts.
**Exit:** 20 real users; ≥ 60% rate report as accurate; interviewer never exceeds probe/time limits in simulations.

## Phase 2 — Voice (3–4 weeks)
- LiveKit + voice worker, streaming STT/TTS, endpointing, barge-in, reconnect/resume.
- Live transcript UI, interviewer state indicator.
**Exit:** p50 latency < 1.2 s, p95 < 2 s in Mumbai region; < 5% sessions with STT complaints.

## Phase 3 — Full loop (4–6 weeks)
- DSA (Monaco + Judge0), LLD, HLD (whiteboard), Behavioral rounds.
- Multi-round sessions with break screens, overall verdict.
- Weak-topic loop and "practice my gaps" mock.
**Exit:** full SDE2 loop runs reliably; calibration agreement ≥ 75%.

## Phase 4 — Generic platform (ongoing)
- Packs: QA/SDET, DevOps/SRE, Data Engineer, Frontend, EM, Director.
- Stack-specific topics (Java, Python, C++, C, Go, JS).
- Multi-language interviews (Hindi/Hinglish etc.) once STT/TTS quality verified.
- Percentiles per cohort, progress dashboard, shareable reports.
- Expert marketplace for pack authoring and golden-set review.
**Exit per pack:** golden set ≥ 50 transcripts and agreement ≥ 80% before public launch of that pack.

## Top risks
| Risk | Mitigation |
|------|------------|
| Feedback feels generic / wrong | Evidence requirement, golden-set CI gate, user feedback loop |
| Voice latency feels robotic | Latency budget tracking from day one, fast model on hot path |
| Accent bias in STT hurts scores | Accent-specific STT evaluation; low-confidence turns can't drive negative scores |
| Cost per session too high | Model tiering, summaries, caching, quotas |
| Scope creep (all roles at once) | One pack fully polished before the next |
