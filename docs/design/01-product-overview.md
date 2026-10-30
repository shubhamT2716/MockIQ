# 01 — Product Overview

## Problem
Candidates prepare alone and have no way to check whether their answers are correct, deep enough
for the target level, or missing key topics. They discover gaps only in the real interview.

## Goals
1. Feel like a real interview: voice, interruptions, follow-ups, time pressure, multiple rounds.
2. Personalized: questions grounded in the candidate's resume and target role/level.
3. Trustworthy feedback: every score backed by evidence from the transcript; explicit list of missed topics.
4. Generic: fresher → director, any field (SDE, QA, DevOps, Data, PM...), any stack (Java, Python, C++, C, Go...).
5. Progress loop: weak topics feed the next mock.

## Non-goals (v1)
- Live human interviewers / marketplace.
- Proctoring or anti-cheating.
- Video/face analysis (privacy-sensitive, low signal).

## Personas
| Persona | Needs |
|---------|-------|
| Fresher | Fundamentals, DSA, confidence speaking, HR basics |
| SDE1–SDE2 | DSA, LLD, intro HLD, project deep-dives, trade-off reasoning |
| Senior/Staff | HLD at scale, cross-team design, ambiguity, mentoring signals |
| EM / Director | Org design, delivery, stakeholder conflict, hiring, technical strategy |
| QA / SDET | Test strategy, automation frameworks, API testing, CI, bug triage scenarios |

## Round matrix (default — overridable per role pack)
| Level | Round 1 | Round 2 | Round 3 | Round 4 |
|-------|---------|---------|---------|---------|
| Fresher | CS fundamentals + language basics | DSA (easy–medium) | Projects + HR | – |
| SDE1 | DSA (medium) | Language/framework depth | Projects + behavioral | – |
| SDE2 | DSA (medium–hard) | LLD (machine coding discussion) | HLD (intro–mid) | Project deep-dive + behavioral |
| Senior/Staff | HLD (large scale) | LLD / code quality | Architecture deep-dive on past work | Leadership & ambiguity |
| EM | People management | Execution & delivery | System design (breadth) | Stakeholders & hiring |
| Director | Strategy & org design | Technical vision | Cross-org influence | Exec communication |

Each round: 15–45 min (configurable). User can run a single round or the full loop.

## Core user journey
1. Sign up → upload resume → choose role, level, stack, mode (voice/chat), language.
2. See the interview plan (rounds, durations) → start.
3. Interview round by round; between rounds, a short break screen.
4. Report: overall verdict, per-round scores, evidence, missed topics, model answers, study plan.
5. "Practice my weak topics" → targeted next mock.

## Success metrics
- Feedback trust: ≥ 70% of users rate report "accurate" (in-app thumbs + comment).
- Evaluator agreement with human reviewers: ≥ 80% of competency scores within ±0.5 (on 1–5 scale).
- Voice latency: p50 < 1.2 s, p95 < 2.0 s from end-of-speech to first interviewer audio.
- Retention: ≥ 30% of users take a 2nd mock within 7 days.
