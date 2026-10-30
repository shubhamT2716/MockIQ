# MockIQ: AI Interview Platform

## Quick start

1. Install **Python 3.11+** from python.org (on Windows, tick "Add Python to PATH").
2. Start MockIQ:
   - **Windows:** double-click **`Start MockIQ (Windows).bat`**
   - **Mac / Linux:** run `./start-mockiq-mac-linux.sh` in a terminal
3. The first run creates a `.env` settings file. Paste your Anthropic API key into it (or set `LLM_PROVIDER=fake` to try without a key), save, and start MockIQ again.
4. Your browser opens at http://localhost:8000. Create an account and start practising. Use Chrome or Edge for voice.

Keep the black window open while you practise; closing it stops MockIQ. Manual setup steps are below if you prefer.

---


An AI interviewer that reads your resume, runs multi-round interviews by voice or text, asks follow-ups until it finds the edge of what you know, and gives an evidence-backed report.

## Run it

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                     # Windows: copy .env.example .env, then add your ANTHROPIC_API_KEY
uvicorn app.main:create_app --factory --reload
```
Open http://localhost:8000 in **Chrome or Edge** (needed for voice input) and create an account.

**Upgrading from the first version?** The database now has user accounts. Delete `mockiq.db` once (it only held practice data); the app tells you if you forget.

No API key yet? Set `LLM_PROVIDER=fake` in `.env` to click through the whole UI with canned responses.

With Postgres instead of SQLite: `docker compose up --build`.

## Test it

```bash
pytest -q                                                     # 43 Python tests, no API key needed
node --test tests/js/*.test.mjs                               # voice command parser tests
python -m scripts.e2e_voice                                   # browser test: fakes the mic, talks to the app (needs playwright)
python -m scripts.simulate_candidate --persona weak --rounds 2   # LLM plays the candidate (needs key)
```
Use the simulator with each persona after every prompt change: a weak candidate should get hints and a low score, a strong one should get twists and a high score.

## What's inside

```
app/
  core/                      pure domain logic, no framework imports
    planner.py               role pack + level + resume + weak topics -> rounds and topics
    progress.py              dashboard maths: trend, streak, practice time, skill trends
    auth.py                  password hashing, tokens, login limiter
    interview_engine.py      turn controller: LLM judges, code decides; handles "skip"
    rules_engine.py          probe/hint/time limits, blocks premature endings
    state_machine.py         legal round transitions
    prompts.py               interviewer prompts, depth ladder, decision policy
    rolepacks.py             YAML schema + validation
    evaluation/
      scorer.py              N independent scoring passes per round
      evidence_validator.py  drops any quote the candidate never said
      aggregator.py          median, spread -> confidence, verdict
      report.py              overall verdict, gaps, study plan
  adapters/                  Anthropic LLM, fake LLM, resume parsing, SQLAlchemy
  auth_service.py            sign-up, sign-in, cookie sessions
  services.py                interview flow, reports, dashboard (all scoped to a user)
  api/routes.py              REST API
  rolepacks/*.yaml           backend-sde, qa-automation, engineering-manager
  static/                    UI (vanilla JS, browser speech in/out, voice-commands.js)
tests/                       unit + full-flow API tests
scripts/simulate_candidate.py
scripts/e2e_voice.py         hands-free voice browser test
docs/design/                 HLD/LLD design docs
```

## Hands-free voice

In Speak mode the interview runs without touching the keyboard:

- **Auto-send on pause.** After the interviewer speaks, the mic opens. When you stop talking for the chosen pause (2, 3 or 5 seconds), your answer is sent. A bar fills during the pause; talking again cancels it. If you trail off on "so", "and" or "umm", it waits twice as long.
- **Voice commands**, said on their own:

| Say | What happens |
|---|---|
| "Can you repeat the question?" / "Pardon?" | The last question is spoken again |
| "Give me a minute" / "Let me think" | Auto-send pauses until you start talking again |
| "Can I skip this one?" | Moves to the next topic; it's marked **Skipped** in your report and weak topics |
| "That's my answer" / "I'm done" / "Over to you" | Sends immediately (the phrase is removed from your answer) |
| "Clear my answer" / "Start over" | Empties the answer box |
| "Speak slower" / "Speak faster" | Changes the interviewer's speed (remembered) |
| "End the interview" | Asks you to confirm with "yes" or "no" |

- **No false triggers.** A command only counts when it's a short phrase on its own. "I'd skip this question of locking and..." inside an answer stays in the answer. "Next question" and "move on" only count as skip before you've started answering.
- **Turn hands-free off** with the toggle to go back to pressing Send; commands still work while the mic is on.
- **Use headphones** if you can. The mic is closed while the interviewer speaks so it doesn't hear itself; tap the mic to interrupt.

Code: `app/static/voice-commands.js` (parser, no dependencies) and the voice section of `app/static/app.js`. Skips go through `POST /api/sessions/{id}/turns` with `{"command": "skip"}` and are handled deterministically by `InterviewEngine.skip_question`.

## Accounts and progress

- **Sign-in:** email and password. Passwords are hashed with scrypt (salted, standard library). Sessions are random tokens in an httpOnly, SameSite=Lax cookie; only a SHA-256 of each token is stored, valid for 30 days.
- **Protection:** 5 failed sign-ins per email or IP per 15 minutes, then a 429. Wrong-email and wrong-password errors are identical (no account discovery). State-changing API calls from other origins are rejected (CSRF), and security headers are set.
- **Data isolation:** every resume, interview, report and weak topic is tied to a user; other users get 404.
- **Dashboard** (`#/dashboard`): score trend against the hire bar, practice time and streak (computed in your timezone), skills weakest first with recent change, weak topics, interviews to resume, and history.
- **Practise these topics:** starts a session that keeps only rounds covering your weak topics and asks those first.
- **Saved resume:** your latest resume is reused automatically when you start a new interview.

### Before you put this on the internet
- Serve over HTTPS and set `COOKIE_SECURE=true`.
- Run more than one server process? Move the login limiter and session locks to Redis (they're in-memory now).
- Not built yet: email verification, password reset, Google sign-in, account deletion and data export. Add these before public launch.

## Add a new role
Create `app/rolepacks/<slug>.yaml` following an existing pack. Startup validation rejects unknown topics/competencies and weights that don't sum to 1. No code changes needed.

## Phase 1 simplifications (vs. the design docs)
| Design doc | Phase 1 | Upgrade path |
|---|---|---|
| LiveKit + server STT/TTS | Browser Web Speech API | Phase 2: voice worker calling the same `InterviewEngine` |
| Redis state + streams | Session state as JSON row; evaluation via FastAPI background task | Move to Redis + worker when you run more than one server process |
| Full Postgres schema (turns, topic_coverage tables) | `sessions.state` JSON | Split into tables when you need analytics |
| pgvector question retrieval | Seed questions in YAML | Import into `questions` table |
| Separate async coverage analyzer | Coverage fields inside each turn decision | Split out when optimising latency |
| OAuth sign-in | Email and password | Add Google/GitHub OAuth next to the existing cookie sessions |
