"""Deterministic fake LLM for tests and offline UI development (LLM_PROVIDER=fake).

The stand-in still has to ask the problem that is in the prompt. It must not
score a candidate who only said that no question was asked.
"""
import re
import threading

_NOT_AN_ANSWER = re.compile(
    r"\b(?:no questions?|explain the problem|what(?:'s| is) the (?:question|problem)|"
    r"there is no|didn'?t ask|repeat the question|i don'?t know|which problem)\b",
    re.I,
)


def _suggested(user: str) -> str | None:
    m = re.search(r"Suggested question: (.*?)\.\s+You must say the problem", user, re.S)
    if not m:
        m = re.search(r"Suggested question: (.*?)\.\s+Adapt it", user, re.S)
    if m:
        q = " ".join(m.group(1).split())
        if q and not q.startswith("an open question"):
            return q
    m = re.search(r"Suggested opener: (.+)", user)
    if m:
        q = m.group(1).strip()
        if q and not q.startswith("ask an open"):
            return q
    return None


def _question_already_asked(user: str) -> str | None:
    for line in reversed(re.findall(r"\[T\d+\] Interviewer: (.+)", user)):
        if "?" in line:
            return line.strip()
    return None


def _latest_candidate(user: str) -> str:
    lines = re.findall(r"\[T\d+\] Candidate: (.+)", user)
    return lines[-1].strip() if lines else ""


def _is_answer(text: str) -> bool:
    text = (text or "").strip()
    if not text or _NOT_AN_ANSWER.search(text):
        return False
    return len(text.split()) >= 6


class FakeLLM:
    def __init__(self, decision_cycle=("PROBE", "NEXT_TOPIC")):
        self.calls: list[str] = []
        self.cycle = decision_cycle
        self._n = 0
        self._lock = threading.Lock()

    def structured(self, *, role, system, user, tool_name, tool_description, schema,
                   temperature=None, max_tokens=1200) -> dict:
        with self._lock:
            self.calls.append(tool_name)
            self._n += 1
            n = self._n
        if tool_name == "say":
            q = _suggested(user) or "Tell me about a project you are proud of and what you personally did."
            name = "there"
            named = re.search(r"introduce yourself as ([^,]+)", user)
            if named:
                name = named.group(1).strip()
            return {"utterance": f"Hi, I'm {name}. We'll start with this. {q}"}
        if tool_name == "turn_decision":
            forced = re.search(r"MUST choose next_action = (\w+)", user)
            latest = _latest_candidate(user)
            if forced is None and not _is_answer(latest):
                q = _question_already_asked(user) or _suggested(user) or "Let me state the problem before we go on."
                return {"answer_quality": "unclear", "estimated_depth": 0,
                        "key_points_hit": [], "key_points_missed": [],
                        "next_action": "CLARIFY",
                        "utterance": f"You're right, let me state it. {q}"}
            action = forced.group(1) if forced else self.cycle[n % len(self.cycle)]
            if action == "END_ROUND":
                utterance = "That's everything I had for this part. Do you have any questions for me?"
            elif action == "NEXT_TOPIC":
                nxt = _suggested(user)
                utterance = f"Okay, let's move on. {nxt}" if nxt else "Okay, let's move to the next topic."
            elif action == "HINT":
                utterance = "Here's a small nudge: start with the simplest working approach, then improve it."
            else:
                utterance = "Okay. What is the time and space cost of that, and what breaks on an edge case?"
            return {"answer_quality": "partial", "estimated_depth": 2,
                    "key_points_hit": ["basic idea"], "key_points_missed": ["trade-offs"],
                    "next_action": action, "utterance": utterance}
        if tool_name == "resume_profile":
            skills = sorted(set(re.findall(r"\b(Java|Python|Spring|Kafka|Redis|AWS|React|SQL|Docker)\b", user)))
            return {"name": "Candidate", "years_experience": 3, "skills": skills,
                    "projects": [{"name": "Payments service", "tech": skills[:3],
                                  "claims": [{"text": "reduced API latency by 40% using Redis caching", "verifiability": "HIGH"}]}],
                    "summary": f"Engineer with experience in {', '.join(skills) or 'software development'}."}
        if tool_name == "round_evaluation":
            names = schema["properties"]["competencies"]["items"]["properties"]["name"]["enum"]
            answered = [(int(m.group(1)), m.group(2).strip())
                        for m in re.finditer(r"\[T(\d+)\] CANDIDATE: (.+)", user)
                        if _is_answer(m.group(2))]
            if not answered:
                return {"competencies": [{"name": nm, "score": None, "evidence": [],
                                          "reasoning": "No answer was given, so this cannot be scored.",
                                          "missed_points": []} for nm in names],
                        "strengths": [], "model_answers": []}
            turn, text = answered[-1]
            quote = " ".join(text.split()[:12])
            return {"competencies": [{"name": nm, "score": 3, "evidence": [{"turn": turn, "quote": quote}],
                                      "reasoning": "Reasonable but not deep.", "missed_points": ["trade-offs"]}
                                     for nm in names],
                    "strengths": ["Clear communication"],
                    "model_answers": [{"question_turn": max(turn - 1, 1), "question": "First question",
                                       "key_points": ["state the approach", "analyse complexity"]}]}
        if tool_name == "report_summary":
            if re.search(r"Overall verdict None \(None\)", user) or re.search(r"overall None", user):
                return {"summary": "There isn't enough here to score. The problem was not answered, so this is not a hire signal.",
                        "study_plan": [{"topic": "Answer the question asked", "why": "The interview moved on without an answer.",
                                        "how_to_practice": "Restate the problem, then give an approach out loud before writing code.", "priority": 1}],
                        "next_mock_focus": ["State your approach before coding"]}
            return {"summary": "Solid basics; go deeper on trade-offs.",
                    "study_plan": [{"topic": "Trade-offs", "why": "Often stopped at the how.",
                                    "how_to_practice": "Compare two options for each design decision out loud.", "priority": 1}],
                    "next_mock_focus": ["trade-offs"]}
        raise ValueError(f"FakeLLM has no handler for {tool_name}")
