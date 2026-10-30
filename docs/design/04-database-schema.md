# 04 — Database Schema

Postgres 16 with extensions `pgcrypto`, `citext`, `vector` (pgvector).

## Tables

```sql
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS citext;
CREATE EXTENSION IF NOT EXISTS vector;

-- ---------- Users & profiles ----------
CREATE TABLE users (
  id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email         citext UNIQUE NOT NULL,
  name          text,
  auth_provider text NOT NULL,                 -- google, github, email
  created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE candidate_profiles (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id          uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  resume_s3_key    text NOT NULL,
  parse_status     text NOT NULL DEFAULT 'PARSING', -- PARSING | READY | FAILED
  parsed           jsonb,                           -- skills, projects, claims, education
  years_experience numeric(4,1),
  primary_skills   text[],
  embedding        vector(1536),
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_profiles_user ON candidate_profiles(user_id, created_at DESC);

-- ---------- Role packs & question bank ----------
CREATE TABLE role_packs (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        text NOT NULL,                  -- backend-sde, qa-automation, eng-manager
  version     int  NOT NULL,
  title       text NOT NULL,
  domain      text NOT NULL,                  -- software, testing, devops, management
  config      jsonb NOT NULL,                 -- full parsed YAML (see 07-role-packs.md)
  is_active   boolean NOT NULL DEFAULT true,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (slug, version)
);

CREATE TABLE questions (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  role_pack_slug   text NOT NULL,
  round_type       text NOT NULL,
  topic            text NOT NULL,             -- caching, concurrency, joins, test-pyramid
  subtopic         text,
  level_min        text NOT NULL,
  level_max        text NOT NULL,
  difficulty       smallint NOT NULL CHECK (difficulty BETWEEN 1 AND 5),
  prompt           text NOT NULL,
  follow_ups       jsonb NOT NULL DEFAULT '[]',   -- ordered probe ladder
  reference_answer text,                          -- key points, not a script
  rubric_hints     jsonb,
  embedding        vector(1536),
  status           text NOT NULL DEFAULT 'DRAFT', -- DRAFT | REVIEWED | RETIRED
  reviewed_by      text,
  created_at       timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_q_lookup ON questions(role_pack_slug, round_type, topic) WHERE status = 'REVIEWED';
CREATE INDEX idx_q_embedding ON questions USING hnsw (embedding vector_cosine_ops);

-- ---------- Sessions ----------
CREATE TABLE interview_sessions (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  profile_id         uuid REFERENCES candidate_profiles(id),
  role_pack_slug     text NOT NULL,
  role_pack_version  int  NOT NULL,             -- pin version for reproducible scoring
  target_level       text NOT NULL,
  stack              text[],                    -- {java, spring} / {python} / {selenium}
  language           text NOT NULL DEFAULT 'en',
  mode               text NOT NULL,             -- VOICE | CHAT
  status             text NOT NULL,             -- see SessionStatus
  plan               jsonb NOT NULL,
  started_at         timestamptz,
  ended_at           timestamptz,
  created_at         timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX idx_sessions_user ON interview_sessions(user_id, created_at DESC);
CREATE INDEX idx_sessions_live ON interview_sessions(status) WHERE status IN ('LIVE','PAUSED');

CREATE TABLE rounds (
  id               uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id       uuid NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  seq              smallint NOT NULL,
  round_type       text NOT NULL,
  status           text NOT NULL,
  topic_plan       jsonb NOT NULL,            -- [{topic, target_depth, mandatory, source}]
  time_budget_sec  int NOT NULL,
  started_at       timestamptz,
  ended_at         timestamptz,
  UNIQUE (session_id, seq)
);

CREATE TABLE turns (
  id            bigint GENERATED ALWAYS AS IDENTITY,
  round_id      uuid NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  session_id    uuid NOT NULL,
  seq           int NOT NULL,
  speaker       text NOT NULL,                -- INTERVIEWER | CANDIDATE | SYSTEM
  text          text NOT NULL,
  stt_confidence real,
  audio_s3_key  text,
  started_at    timestamptz NOT NULL,
  ended_at      timestamptz,
  meta          jsonb,                        -- TurnDecision, topic, code snapshot ref
  PRIMARY KEY (round_id, seq)
);
CREATE INDEX idx_turns_session ON turns(session_id);

CREATE TABLE topic_coverage (
  round_id       uuid NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  topic          text NOT NULL,
  target_depth   smallint NOT NULL,
  depth_reached  smallint NOT NULL DEFAULT 0, -- 0..5 depth ladder
  status         text NOT NULL,               -- NOT_STARTED | COVERED | PARTIAL | MISSED
  probes         smallint NOT NULL DEFAULT 0,
  hints          smallint NOT NULL DEFAULT 0,
  signals        jsonb,                       -- key points hit / missed
  PRIMARY KEY (round_id, topic)
);

CREATE TABLE code_submissions (
  id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  round_id    uuid NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  language    text NOT NULL,
  code        text NOT NULL,
  result      jsonb,                          -- stdout, stderr, tests passed, runtime
  created_at  timestamptz NOT NULL DEFAULT now()
);

-- ---------- Evaluation & reports ----------
CREATE TABLE evaluations (
  id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  round_id           uuid NOT NULL REFERENCES rounds(id) ON DELETE CASCADE,
  pass_no            smallint NOT NULL,
  model              text NOT NULL,
  prompt_version     text NOT NULL,
  competency_scores  jsonb NOT NULL,          -- {problem_solving: {score, evidence:[turn_seq]}}
  created_at         timestamptz NOT NULL DEFAULT now(),
  UNIQUE (round_id, pass_no)                  -- idempotency
);

CREATE TABLE round_scores (
  round_id    uuid PRIMARY KEY REFERENCES rounds(id) ON DELETE CASCADE,
  final       jsonb NOT NULL,                 -- aggregated per competency
  overall     numeric(3,2) NOT NULL,
  confidence  text NOT NULL,                  -- HIGH | MEDIUM | LOW
  verdict     text NOT NULL
);

CREATE TABLE reports (
  id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id     uuid UNIQUE NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
  verdict        text NOT NULL,               -- STRONG_HIRE | HIRE | LEAN_HIRE | LEAN_NO | NO_HIRE
  overall_score  numeric(3,2) NOT NULL,
  percentile     numeric(5,2),                -- null until cohort is large enough
  body           jsonb NOT NULL,              -- see 06-evaluation-engine.md
  user_rating    smallint,                    -- trust feedback from user
  created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE weak_topics (
  user_id            uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  role_pack_slug     text NOT NULL,
  topic              text NOT NULL,
  severity           smallint NOT NULL,       -- 1..3
  times_missed       int NOT NULL DEFAULT 1,
  last_session_id    uuid,
  updated_at         timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, role_pack_slug, topic)
);
```

## Indexing & growth notes
- `turns` is the largest table (~100–300 rows per session). Partition by month on `started_at` once > 50M rows.
- Percentile: compute nightly per `(role_pack_slug, target_level)` cohort into a materialized view; show only when cohort ≥ 200 sessions.
- Never update scores in place for a pinned `prompt_version`; re-scoring writes new `evaluations` rows.

## Redis keys
| Key | Type | TTL | Purpose |
|-----|------|-----|---------|
| `session:{id}:state` | JSON | 2 h | `RoundContext` checkpoint (current round, topic, counters, last N turns) |
| `session:{id}:lease` | string (worker id) | 15 s, renewed | Single-writer guarantee |
| `session:{id}:pause` | string | 15 min | Resumable pause window |
| `stream:rounds` | Stream | – | `RoundCompleted` events (consumer group `eval`) |
| `stream:sessions` | Stream | – | `SessionCompleted` events (consumer groups `report`, `analytics`) |
| `ratelimit:{user}` | counter | 1 day | Daily interview-minute quota |

## Object storage layout
```
s3://mockiq-prod/
  resumes/{user_id}/{profile_id}/original.pdf
  audio/{session_id}/{round_seq}/{turn_seq}.opus      (only if user consented)
  transcripts/{session_id}/full.json                  (archival copy)
  reports/{session_id}/report.pdf                     (generated on demand)
```
