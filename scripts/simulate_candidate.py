"""Run a full interview where an LLM plays the candidate. Use it to tune prompts and rules.

    python -m scripts.simulate_candidate --persona weak --role backend-sde --level L2 --rounds 2

Personas: strong, average, weak, rambling, dont_know. Needs ANTHROPIC_API_KEY.
"""
import argparse
import json

from fastapi.testclient import TestClient

from app.adapters.llm_anthropic import AnthropicLLM
from app.config import settings
from app.main import create_app

PERSONAS = {
    "strong": "a strong candidate who answers precisely, covers trade-offs and failure modes, and uses numbers",
    "average": "an average candidate who knows the basics but rarely mentions trade-offs or edge cases",
    "weak": "a weak candidate with shallow knowledge who often gives vague or partly wrong answers",
    "rambling": "a candidate who knows things but rambles and drifts off topic",
    "dont_know": "a candidate who honestly says 'I don't know' to about half the questions",
}
SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}}, "required": ["answer"]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", default="average", choices=PERSONAS)
    ap.add_argument("--role", default="backend-sde")
    ap.add_argument("--level", default="L2")
    ap.add_argument("--rounds", type=int, nargs="*", default=[2])
    ap.add_argument("--max-turns", type=int, default=60)
    args = ap.parse_args()

    llm = AnthropicLLM(settings)
    client = TestClient(create_app(settings, llm=llm))
    s = client.post("/api/sessions", json={"role_pack": args.role, "level": args.level,
                                           "rounds": args.rounds, "mode": "chat"}).json()
    view = client.post(f"/api/sessions/{s['id']}/start").json()
    for _ in range(args.max_turns):
        if view["status"] == "COMPLETED":
            break
        question = view["transcript"][-1]["text"]
        print(f"\nINTERVIEWER: {question}")
        reply = llm.structured(role="interviewer", system=f"You are role-playing {PERSONAS[args.persona]} in a job interview. Answer in 1-4 spoken sentences.",
                               user=f"The interviewer said: {question}", tool_name="candidate", tool_description="Candidate answer",
                               schema=SCHEMA, temperature=0.8, max_tokens=400)["answer"]
        print(f"CANDIDATE: {reply}")
        view = client.post(f"/api/sessions/{s['id']}/turns", json={"text": reply}).json()
    if view["status"] != "COMPLETED":
        client.post(f"/api/sessions/{s['id']}/end")
    report = client.get(f"/api/sessions/{s['id']}/report").json()
    body = report.get("body") or {}
    print("\n=== VERDICT:", body.get("verdict"), body.get("overall"))
    print(json.dumps([{r["title"]: {c["name"]: c["score"] for c in r["competencies"]}} for r in body.get("rounds", [])], indent=2))


if __name__ == "__main__":
    main()
