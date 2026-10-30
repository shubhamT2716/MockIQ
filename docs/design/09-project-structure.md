# 09 — Project Structure & Tech Stack

## Tech stack
| Layer | Choice | Notes |
|-------|--------|-------|
| Frontend | Next.js (React, TypeScript), Tailwind | Monaco editor, Excalidraw, LiveKit client SDK |
| Backend | Python 3.12, FastAPI, Pydantic v2 | async throughout |
| Voice | LiveKit (self-host or cloud) + LiveKit Agents (Python) | Pipecat is an alternative |
| STT / TTS | Pluggable adapters | Test accuracy on Indian-English accents before choosing |
| LLM | Pluggable adapter (e.g. Claude) | Fast model on hot path, stronger model for evaluation |
| DB | Postgres 16 + pgvector | SQLAlchemy 2.0 + Alembic migrations |
| Cache / state / events | Redis 7 (JSON + Streams) | |
| Code execution | Judge0 (self-hosted, isolated network) | |
| Storage | S3-compatible | |
| Infra | Docker, Kubernetes (later), Terraform | Start with docker-compose |
| Observability | OpenTelemetry, Prometheus, Grafana, Sentry | Trace every turn end-to-end |

## Monorepo layout
```
mock-interview/
├── apps/
│   └── web/                         # Next.js frontend
│       ├── app/(interview)/session/[id]/page.tsx
│       ├── components/{Transcript,CodeEditor,Whiteboard,InterviewerAvatar}.tsx
│       └── lib/{api.ts,livekit.ts}
├── services/
│   ├── api/                         # FastAPI: gateway-facing routes (profile + orchestrator in v1)
│   │   ├── main.py
│   │   ├── routers/{profiles,sessions,role_packs,reports}.py
│   │   └── deps.py
│   ├── voice_agent/                 # LiveKit Agents worker
│   │   ├── worker.py
│   │   └── pipeline.py              # VAD → STT → orchestrator → TTS
│   └── eval_worker/
│       ├── consumer.py              # Redis Streams consumer group
│       └── report_builder.py
├── core/                            # pure domain, no framework imports
│   ├── domain/{models.py,enums.py,state_machine.py}
│   ├── interview/{planner.py,turn_controller.py,rules_engine.py,coverage.py}
│   ├── rounds/{base.py,dsa.py,lld.py,hld.py,behavioral.py,project.py,leadership.py,factory.py}
│   ├── evaluation/{scorer.py,evidence_validator.py,aggregator.py}
│   ├── prompts/{interviewer/*.jinja,evaluator/*.jinja,resume/*.jinja}
│   └── ports.py                     # LLMClient, STTClient, TTSClient, Repos (interfaces)
├── infra_adapters/                  # implementations of ports
│   ├── llm/, stt/, tts/, db/repositories.py, redis/, storage/, judge0/
├── rolepacks/
│   ├── schema.json
│   ├── backend-sde.yaml
│   ├── qa-automation.yaml
│   └── engineering-director.yaml
├── evals/                           # golden transcripts + calibration harness
│   ├── golden/backend-sde/*.json
│   └── run_calibration.py
├── migrations/                      # Alembic
├── tests/{unit,integration,e2e}/
├── docker-compose.yml               # postgres, redis, livekit, judge0, api, workers, web
└── docs/                            # this design folder
```

Rule: `core/` imports nothing from FastAPI, SQLAlchemy, Redis, or provider SDKs (hexagonal architecture).
That keeps the interviewer logic unit-testable with fake LLM responses.

## Testing strategy
| Level | What | How |
|-------|------|-----|
| Unit | State machine, rules engine, planner, aggregator, evidence validator | pytest, fake LLM returning fixed `TurnDecision`s |
| Contract | LLM output schemas | Validate real model outputs against Pydantic models in nightly job |
| Simulation | Full interviews without humans | "Candidate bot" LLM with persona (strong / average / weak / rambling / off-topic) plays the candidate; assert interviewer probes, hints and ends on time |
| Calibration | Evaluator accuracy | `evals/run_calibration.py` vs golden set; CI gate |
| Load | Concurrent voice sessions | Synthetic audio clients against LiveKit; measure p95 turn latency |
| E2E | UI flows | Playwright |

## Local dev
```
docker compose up -d postgres redis livekit judge0
alembic upgrade head
python -m scripts.load_rolepacks rolepacks/
uvicorn services.api.main:app --reload
python -m services.voice_agent.worker dev
python -m services.eval_worker.consumer
cd apps/web && npm run dev
```
