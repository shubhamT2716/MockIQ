"""Role pack loading and validation."""
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

from .enums import RoundType


class Competency(BaseModel):
    description: str
    anchors: dict[int, str]


class TopicDef(BaseModel):
    title: str
    seed: str | None = None
    key_points: list[str] = Field(default_factory=list)


class StackDef(BaseModel):
    label: str
    topics: list[str]


class RoundRules(BaseModel):
    max_probes: int = 3
    max_hints: int = 1


class RoundSpec(BaseModel):
    type: RoundType
    title: str
    duration_min: int
    target_depth: int = 3
    mandatory_topics: list[str] = Field(default_factory=list)
    optional_topics: list[str] = Field(default_factory=list)
    include_stack_topics: int = 0
    competencies: dict[str, float]
    tools: list[str] = Field(default_factory=list)
    rules: RoundRules = Field(default_factory=RoundRules)


class LevelDef(BaseModel):
    label: str
    bar: str


class Persona(BaseModel):
    name: str
    style: str


class RolePack(BaseModel):
    slug: str
    title: str
    domain: str
    persona: Persona
    levels: dict[str, LevelDef]
    stacks: dict[str, StackDef] = Field(default_factory=dict)
    competencies: dict[str, Competency]
    topics: dict[str, TopicDef] = Field(default_factory=dict)
    rounds_by_level: dict[str, list[RoundSpec]]

    @model_validator(mode="after")
    def _check_references(self):
        for level, rounds in self.rounds_by_level.items():
            if level not in self.levels:
                raise ValueError(f"{self.slug}: rounds defined for unknown level {level}")
            for r in rounds:
                for c in r.competencies:
                    if c not in self.competencies:
                        raise ValueError(f"{self.slug}/{level}/{r.title}: unknown competency {c}")
                if abs(sum(r.competencies.values()) - 1.0) > 0.01:
                    raise ValueError(f"{self.slug}/{level}/{r.title}: competency weights must sum to 1")
                for t in r.mandatory_topics + r.optional_topics:
                    if t not in self.topics:
                        raise ValueError(f"{self.slug}/{level}/{r.title}: unknown topic {t}")
        return self


def load_rolepacks(directory: str) -> dict[str, RolePack]:
    packs: dict[str, RolePack] = {}
    for path in sorted(Path(directory).glob("*.yaml")):
        data = yaml.safe_load(path.read_text())
        pack = RolePack.model_validate(data)
        packs[pack.slug] = pack
    return packs
