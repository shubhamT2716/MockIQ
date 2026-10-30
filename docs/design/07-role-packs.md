# 07 — Role Packs (making the platform generic)

A role pack is versioned YAML. Adding a new field (QA, DevOps, Data, PM, Director) = adding a pack.
Sessions pin `role_pack_version` so scores stay reproducible.

## Schema
```yaml
slug: string                 # unique id
version: int
title: string
domain: software | testing | devops | data | management | product
stacks: [string]             # selectable stacks/languages
levels: [FRESHER, L1, L2, L3_SENIOR, L4_STAFF, EM, DIRECTOR]

competencies:                # reusable across rounds
  <name>:
    description: string
    anchors:                 # per-level BARS, 1..5
      <LEVEL>: {1: str, 2: str, 3: str, 4: str, 5: str}

rounds_by_level:
  <LEVEL>:
    - type: RoundType
      duration_min: int
      target_depth: 1..5
      mandatory_topics: [string]
      optional_topics: [string]
      competencies: {<name>: weight}
      tools: [editor | whiteboard]
      rules: {max_probes: int, max_hints: int}

persona:
  name: string
  style: string              # e.g. "friendly but rigorous senior engineer"
```

## Example: backend SDE (excerpt)
```yaml
slug: backend-sde
version: 3
title: Backend Software Engineer
domain: software
stacks: [java-spring, python-django, python-fastapi, go, nodejs, cpp]
levels: [FRESHER, L1, L2, L3_SENIOR, L4_STAFF]

competencies:
  trade_off_reasoning:
    description: Compares options against requirements
    anchors:
      L2:
        1: "Picks a solution with no justification"
        3: "Compares 2 options on at least 2 dimensions"
        5: "Quantifies impact, notes when the choice would flip, covers ops"

rounds_by_level:
  L2:
    - type: DSA
      duration_min: 45
      target_depth: 3
      mandatory_topics: [arrays-hashing, graphs-or-trees]
      optional_topics: [dp, heaps, sliding-window]
      competencies: {approach: 0.25, correctness: 0.25, complexity_analysis: 0.2, code_quality: 0.15, communication: 0.15}
      tools: [editor]
      rules: {max_probes: 3, max_hints: 1}
    - type: LLD
      duration_min: 45
      target_depth: 3
      mandatory_topics: [object-modeling, solid, design-patterns]
      competencies: {requirements: 0.2, object_modeling: 0.35, design_principles: 0.25, extensibility: 0.2}
      tools: [editor]
    - type: HLD
      duration_min: 45
      target_depth: 3
      mandatory_topics: [estimation, api-design, data-modeling, caching, scaling]
      optional_topics: [messaging, consistency, rate-limiting]
      competencies: {architecture: 0.3, scalability: 0.25, reliability: 0.2, trade_off_reasoning: 0.25}
      tools: [whiteboard]
    - type: PROJECT_DEEP_DIVE
      duration_min: 30
      target_depth: 4
      mandatory_topics: [resume-claims]
      competencies: {ownership: 0.4, technical_depth: 0.4, communication: 0.2}

stack_topics:                # appended when user picks a stack
  java-spring: [jvm-memory, gc, concurrency-java-util, spring-di, transactions, jpa-n-plus-1]
  python-fastapi: [gil, asyncio, typing, dependency-injection, sqlalchemy-sessions]
  cpp: [raii, smart-pointers, move-semantics, stl-complexity, undefined-behavior]

persona:
  name: "Arjun"
  style: "calm, curious senior engineer who follows up on every claim"
```

## Example: QA automation (excerpt)
```yaml
slug: qa-automation
version: 1
title: QA / SDET
domain: testing
stacks: [selenium-java, playwright-ts, pytest, restassured, appium]
rounds_by_level:
  L2:
    - type: FUNDAMENTALS
      duration_min: 30
      mandatory_topics: [test-pyramid, test-design-techniques, bug-lifecycle]
    - type: TESTING_STRATEGY
      duration_min: 40
      mandatory_topics: [test-plan-for-feature, risk-based-testing, api-testing, flaky-tests]
      tools: [whiteboard]
    - type: DSA
      duration_min: 30
      target_depth: 2
      mandatory_topics: [strings, hashing]
      tools: [editor]
    - type: BEHAVIORAL
      duration_min: 20
```

## Example: Director (excerpt)
```yaml
slug: engineering-director
version: 1
domain: management
rounds_by_level:
  DIRECTOR:
    - type: LEADERSHIP
      duration_min: 45
      target_depth: 5
      mandatory_topics: [org-design, hiring-bar, underperformance, multi-team-planning]
    - type: HLD
      duration_min: 45
      target_depth: 3
      mandatory_topics: [platform-strategy, build-vs-buy, tech-debt-portfolio]
```

## Authoring workflow
1. Author writes YAML in `rolepacks/` → PR.
2. CI validates against JSON Schema, checks every competency has anchors for each level used.
3. Seed questions imported into `questions` table as DRAFT → reviewed by a domain expert → REVIEWED.
4. Golden transcripts added before the pack is marked `is_active`.
