# 10 — Non-Functional Requirements, Security & Cost

## Latency budget (voice, end of candidate speech → first interviewer audio)
| Stage | Target |
|-------|--------|
| End-of-turn detection | 300–700 ms (adaptive) |
| Final STT transcript | 100–300 ms (streaming STT) |
| Orchestrator load state + rules | < 30 ms (Redis) |
| LLM time to first utterance token | 300–700 ms (fast model, short prompt, prompt caching) |
| TTS time to first audio | 100–300 ms (streaming TTS, sentence chunking) |
| **Total p50** | **< 1.2 s**; p95 < 2.0 s |

Techniques: prompt caching for static system/rubric parts, keep only last ~12 turns + rolling summary in prompt,
start TTS on first sentence, co-locate workers with LiveKit region (e.g. Mumbai for India users), warm connections.

## Availability & scale
- Target 99.5% for live sessions in v1.
- Graceful degradation: if voice infra fails, offer to continue the same session in chat.
- Capacity planning unit: concurrent sessions; alert when voice worker utilization > 70%.

## Security & privacy
| Area | Control |
|------|---------|
| Resume PII | Encrypt at rest (S3 SSE + DB disk encryption); access only by profile service; delete on request |
| Audio | Record only with explicit consent toggle; default retention 30 days; transcripts kept for report |
| Prompt injection | Resume text and candidate speech wrapped as DATA; system prompts instruct to ignore embedded instructions; outputs schema-validated |
| Code execution | Judge0 in isolated network, no egress, CPU/mem/time limits, language whitelist |
| Auth | OAuth (Google/GitHub) + JWT short-lived access tokens; LiveKit tokens scoped to one room, 1 h expiry |
| Abuse | Per-user daily minute quota, rate limiting at gateway, max session length |
| Compliance | Privacy policy covering AI processing; India DPDP Act and GDPR data-subject rights (export/delete) |
| Secrets | Cloud secret manager; no keys in repo; provider keys never sent to client |

## Cost model
Variable cost per interview minute ≈ STT/min + TTS/min (only interviewer talk time, ~35–45%) + LLM tokens
(hot path turns + async analyzer) + LiveKit/bandwidth + evaluation (3 passes, once per round).

Controls:
- Smaller/faster model on hot path, stronger model only for evaluation.
- Rolling transcript summary to cap prompt size.
- Prompt caching for static prompt sections.
- Free tier: chat mode + 1 short voice round/week; paid tiers for full voice loops.
- Track `cost_per_session` as a first-class metric per role pack and model.

## Observability
- Trace per turn: `vad_end → stt_final → llm_first_token → tts_first_audio`.
- Dashboards: turn latency percentiles, LLM error rate, eval lag, sessions abandoned mid-round, report trust rating.
- Log every `TurnDecision` and `RulesEngine` override (great for tuning).
