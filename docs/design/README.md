# AI Mock Interview Platform — Design Docs

An AI interviewer that reads your resume, runs a realistic multi-round interview over voice (or chat),
asks counter-questions and scenario questions, and produces an evidence-backed score and study plan.
Works for any role (SDE, QA, DevOps, Data, Managers, Directors) and any language/stack via **role packs**.

## How to read this folder

| # | File | What it covers |
|---|------|----------------|
| 01 | [01-product-overview.md](01-product-overview.md) | Goals, users, round matrix by level, success metrics |
| 02 | [02-hld.md](02-hld.md) | Services, data flow, sequence diagrams, scaling, failure handling |
| 03 | [03-lld.md](03-lld.md) | Domain model, state machine, classes, design patterns |
| 04 | [04-database-schema.md](04-database-schema.md) | Postgres DDL, indexes, Redis keys, S3 layout |
| 05 | [05-interviewer-engine.md](05-interviewer-engine.md) | Turn controller, depth ladder, probing rules, prompts |
| 06 | [06-evaluation-engine.md](06-evaluation-engine.md) | Rubrics, multi-pass scoring, evidence validation, report |
| 07 | [07-role-packs.md](07-role-packs.md) | Config schema that makes the platform generic |
| 08 | [08-api-contracts.md](08-api-contracts.md) | REST endpoints, realtime events, queue events |
| 09 | [09-project-structure.md](09-project-structure.md) | Tech stack, repo layout, testing strategy |
| 10 | [10-nfr-security-cost.md](10-nfr-security-cost.md) | Latency budget, scaling, privacy, cost controls |
| 11 | [11-roadmap.md](11-roadmap.md) | Phased delivery with exit criteria |

## Key decisions (ADR summary)

| Decision | Choice | Why |
|----------|--------|-----|
| Language | Python 3.12 + FastAPI | Voice/LLM ecosystem is Python-first (LiveKit Agents, Pipecat, LLM SDKs) |
| Realtime audio | WebRTC via LiveKit, client ↔ voice worker directly | REST/gateway hop would add latency |
| Interview brain | Orchestrator owns state; voice worker is thin | Chat and voice share identical logic |
| Interviewer control | LLM decides *judgment*, code enforces *rules* (state machine) | Keeps interviews on time and on topic |
| Evaluation | Separate async worker, multi-pass, evidence required | Unbiased, explainable, trustworthy scores |
| Genericity | Role packs as versioned YAML config | New field = new config, not new code |
| Storage | Postgres (+pgvector), Redis, S3 | Simple, proven, one relational source of truth |
| Async | Redis Streams first, Kafka later if needed | Avoid premature infrastructure |

## Glossary
- **Role pack** – config describing a role: competencies, rounds per level, rubrics, seed questions.
- **Round** – one stage of an interview (e.g., DSA, LLD, HLD, Behavioral, Project deep-dive).
- **Turn** – one utterance by interviewer or candidate.
- **Topic coverage** – which planned topics were discussed and how deep the candidate went.
- **Depth ladder** – L1 (what) → L5 (alternatives from real experience); target depth depends on level.
