"""Builds the interview plan: rounds and topics per round."""
import random

from .enums import RoundType
from .models import RoundState, SessionState, TopicState
from .rolepacks import RolePack, RoundSpec

VERIFIABILITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


def _max_topics(duration_min: int) -> int:
    return max(2, min(6, duration_min // 9))


def _resume_topics(profile: dict | None, target_depth: int, limit: int = 3) -> list[TopicState]:
    if not profile:
        return []
    claims = []
    for project in profile.get("projects", []):
        for claim in project.get("claims", []):
            claims.append((VERIFIABILITY_ORDER.get(claim.get("verifiability", "LOW"), 2),
                           project.get("name", "a project"), claim.get("text", "")))
    claims.sort(key=lambda c: c[0])
    topics = []
    for _, project_name, text in claims[:limit]:
        if not text:
            continue
        topics.append(TopicState(
            name=f"{project_name}: {text}"[:160],
            target_depth=target_depth,
            source="resume",
            seed_question=f"On your resume you mention, for {project_name}, that you {text.rstrip('.')}. Walk me through what you personally did there.",
            key_points=["personal contribution", "technical decisions", "trade-offs", "measurable result"],
        ))
    return topics


def _topic_from_slug(pack: RolePack, slug: str, depth: int, source) -> TopicState:
    d = pack.topics[slug]
    return TopicState(name=d.title, target_depth=depth, source=source,
                      seed_question=d.seed, key_points=d.key_points)


def build_round(pack: RolePack, spec: RoundSpec, seq: int, stack: list[str],
                profile: dict | None, weak_topics: set[str], rng: random.Random,
                focus_weak: bool = False) -> RoundState:
    limit = _max_topics(spec.duration_min)
    topics: list[TopicState] = []
    names: set[str] = set()

    def add(t: TopicState):
        if len(topics) < limit and t.name not in names:
            topics.append(t)
            names.add(t.name)

    if focus_weak:
        # Gap practice: the user's weak topics that belong to this round come first.
        stack_pool = [t for s in stack if s in pack.stacks for t in pack.stacks[s].topics]
        candidates = [(pack.topics[s].title, s) for s in spec.mandatory_topics + spec.optional_topics
                      if s != "resume-claims"]
        candidates += [(t, None) for t in stack_pool] if spec.include_stack_topics else []
        for title, slug in candidates:
            if title in weak_topics:
                add(_topic_from_slug(pack, slug, spec.target_depth, "weak") if slug
                    else TopicState(name=title, target_depth=spec.target_depth, source="weak"))
            if sum(1 for t in topics if t.source == "weak") >= 2:
                break

    for slug in spec.mandatory_topics:
        if slug == "resume-claims":
            resume = _resume_topics(profile, spec.target_depth, limit=2)
            for t in resume:
                add(t)
            if not resume:
                add(_topic_from_slug(pack, slug, spec.target_depth, "mandatory"))
        else:
            add(_topic_from_slug(pack, slug, spec.target_depth, "mandatory"))

    if spec.include_stack_topics and stack:
        pool = [t for s in stack if s in pack.stacks for t in pack.stacks[s].topics]
        for title in rng.sample(pool, k=min(spec.include_stack_topics, len(pool))):
            add(TopicState(name=title, target_depth=spec.target_depth, source="stack"))

    weak_optional = [s for s in spec.optional_topics if pack.topics[s].title in weak_topics]
    for slug in weak_optional[:1]:
        add(_topic_from_slug(pack, slug, spec.target_depth, "weak"))

    min_topics = min(limit, 3)
    remaining = [s for s in spec.optional_topics if pack.topics[s].title not in names]
    rng.shuffle(remaining)
    for slug in remaining:
        if len(topics) >= min_topics:
            break
        add(_topic_from_slug(pack, slug, spec.target_depth, "optional"))

    return RoundState(
        seq=seq,
        type=spec.type,
        title=spec.title,
        duration_min=spec.duration_min,
        target_depth=spec.target_depth,
        competencies=spec.competencies,
        tools=spec.tools,
        max_probes=spec.rules.max_probes,
        max_hints=spec.rules.max_hints,
        max_candidate_turns=len(topics) * (spec.rules.max_probes + 2) + 2,
        topics=topics,
    )


def build_plan(pack: RolePack, level: str, stack: list[str], profile: dict | None,
               weak_topics: set[str] | None = None, round_indexes: list[int] | None = None,
               rng: random.Random | None = None, focus_weak: bool = False) -> SessionState:
    if level not in pack.rounds_by_level:
        raise ValueError(f"Level {level} is not available for {pack.title}")
    rng = rng or random.Random()
    specs = pack.rounds_by_level[level]
    if round_indexes:
        specs = [specs[i] for i in round_indexes if 0 <= i < len(specs)]
    if not specs:
        raise ValueError("Pick at least one round")
    weak = weak_topics or set()
    if focus_weak:
        # Only keep rounds that can practise at least one weak topic, unless none can.
        def has_weak(spec):
            titles = {pack.topics[x].title for x in spec.mandatory_topics + spec.optional_topics if x != "resume-claims"}
            if spec.include_stack_topics:
                titles |= {t for st in stack if st in pack.stacks for t in pack.stacks[st].topics}
            return bool(titles & weak)
        specs = [sp for sp in specs if has_weak(sp)] or specs
    rounds = [build_round(pack, spec, i + 1, stack, profile, weak, rng, focus_weak)
              for i, spec in enumerate(specs)]
    return SessionState(
        role_pack=pack.slug,
        role_title=pack.title,
        level=pack.levels[level].label,
        level_bar=pack.levels[level].bar,
        stack=[pack.stacks[s].label for s in stack if s in pack.stacks],
        persona_name=pack.persona.name,
        persona_style=pack.persona.style,
        resume_summary=(profile or {}).get("summary"),
        rounds=rounds,
    )


ROUND_TYPE_LABEL = {t: t.value.replace("_", " ").title() for t in RoundType}
