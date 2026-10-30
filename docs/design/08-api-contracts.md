# 08 — API Contracts

Base path `/v1`. Auth: Bearer JWT. All IDs are UUIDs. Errors use RFC 7807 problem+json.

## REST
| Method | Path | Body / Query | Response |
|--------|------|--------------|----------|
| POST | `/profiles` | multipart: `resume` file | `202 {profile_id, status:"PARSING"}` |
| GET | `/profiles/{id}` | – | `{status, parsed, years_experience}` |
| GET | `/role-packs` | `?domain=testing` | `[{slug, title, levels, stacks}]` |
| GET | `/role-packs/{slug}` | – | pack summary (rounds per level) |
| POST | `/sessions` | `{profile_id, role_pack_slug, level, stack[], mode, language, rounds?: [seq]}` | `201 {session_id, plan}` |
| POST | `/sessions/{id}/start` | – | voice: `{livekit_url, token, room}`; chat: `{first_message}` |
| POST | `/sessions/{id}/turns` | chat mode `{text, code_snapshot?}` | SSE stream of interviewer utterance + events |
| POST | `/sessions/{id}/pause` | – | `{status:"PAUSED", resume_before}` |
| POST | `/sessions/{id}/resume` | – | same as start |
| POST | `/sessions/{id}/end` | `{reason}` | `{status:"EVALUATING"}` |
| POST | `/sessions/{id}/code/run` | `{language, code, stdin?}` | `{stdout, stderr, time_ms, passed?}` |
| GET | `/sessions/{id}/report` | – | `{status:"PENDING"}` or report body |
| POST | `/sessions/{id}/report/feedback` | `{rating, comment, competency?}` | `204` |
| GET | `/me/progress` | `?role_pack=backend-sde` | scores over time, weak topics |

Idempotency: `POST /sessions` and `/turns` accept `Idempotency-Key` header.

## Realtime events (LiveKit data channel, JSON)
Server → client:
| Event | Payload |
|-------|---------|
| `transcript.partial` | `{speaker, text}` |
| `transcript.final` | `{speaker, turn_seq, text}` |
| `interviewer.state` | `{state: "listening" \| "thinking" \| "speaking"}` |
| `round.changed` | `{seq, type, duration_min}` |
| `ui.open_editor` | `{language, starter_code?}` |
| `ui.open_whiteboard` | `{}` |
| `session.paused` / `session.completed` | `{}` |

Client → server:
| Event | Payload |
|-------|---------|
| `code.snapshot` | `{language, code, cursor_line}` (debounced 2 s) |
| `whiteboard.snapshot` | `{elements_json}` (debounced 5 s) |
| `candidate.request_time` | `{seconds}` |
| `candidate.skip_question` | `{}` |

## Internal (orchestrator ↔ voice worker)
```
POST /internal/sessions/{id}/candidate-turn
  {text, started_at, ended_at, stt_confidence, code_snapshot?}
  → chunked stream of utterance text + control events
```

## Domain events (Redis Streams)
```json
// stream:rounds
{"type":"RoundCompleted","event_id":"...","session_id":"...","round_id":"...","seq":2,"occurred_at":"..."}
// stream:sessions
{"type":"SessionCompleted","event_id":"...","session_id":"...","user_id":"...","occurred_at":"..."}
// stream:profiles
{"type":"ResumeUploaded","event_id":"...","profile_id":"...","s3_key":"..."}
```
Consumers are idempotent on `event_id`.
