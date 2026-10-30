import random

import pytest

from app.core.planner import build_plan
from app.core.rolepacks import RolePack


def test_all_packs_load_and_reference_valid_things(packs):
    assert {"backend-sde", "qa-automation", "engineering-manager"} <= set(packs)
    for p in packs.values():
        for stack in p.stacks.values():
            for t in stack.topics:
                assert t.count("(") == t.count(")"), f"YAML split a topic: {t}"


def test_invalid_weights_rejected(packs):
    data = packs["backend-sde"].model_dump()
    data["rounds_by_level"]["L2"][0]["competencies"] = {"approach": 0.5}
    with pytest.raises(ValueError):
        RolePack.model_validate(data)


def test_plan_uses_resume_claims_for_project_round(packs):
    profile = {"summary": "Backend dev", "projects": [
        {"name": "Payments", "claims": [{"text": "cut latency 40% with Redis", "verifiability": "HIGH"}]}]}
    s = build_plan(packs["backend-sde"], "L2", ["java-spring"], profile, rng=random.Random(1))
    project_round = next(r for r in s.rounds if r.type.value == "PROJECT_DEEP_DIVE")
    assert project_round.topics[0].source == "resume"
    assert "Redis" in project_round.topics[0].seed_question


def test_plan_prioritises_weak_topics(packs):
    s = build_plan(packs["backend-sde"], "L2", [], None, weak_topics={"Reliability and failure modes"},
                   rng=random.Random(3))
    hld = next(r for r in s.rounds if r.type.value == "HLD")
    assert any(t.source == "weak" for t in hld.topics)


def test_round_subset_and_unknown_level(packs):
    s = build_plan(packs["backend-sde"], "L2", [], None, round_indexes=[2])
    assert len(s.rounds) == 1 and s.rounds[0].type.value == "HLD" and s.rounds[0].seq == 1
    with pytest.raises(ValueError):
        build_plan(packs["backend-sde"], "DIRECTOR", [], None)
