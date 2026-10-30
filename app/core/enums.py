from enum import StrEnum


class SessionStatus(StrEnum):
    PLANNED = "PLANNED"
    LIVE = "LIVE"
    COMPLETED = "COMPLETED"


class RoundStatus(StrEnum):
    PLANNED = "PLANNED"
    QUESTIONING = "QUESTIONING"
    PROBING = "PROBING"
    HINTING = "HINTING"
    WRAP_UP = "WRAP_UP"
    COMPLETED = "COMPLETED"
    ENDED_EARLY = "ENDED_EARLY"
    SKIPPED = "SKIPPED"


LIVE_ROUND_STATES = {
    RoundStatus.QUESTIONING,
    RoundStatus.PROBING,
    RoundStatus.HINTING,
    RoundStatus.WRAP_UP,
}


class RoundType(StrEnum):
    FUNDAMENTALS = "FUNDAMENTALS"
    DSA = "DSA"
    LANGUAGE_DEPTH = "LANGUAGE_DEPTH"
    LLD = "LLD"
    HLD = "HLD"
    PROJECT_DEEP_DIVE = "PROJECT_DEEP_DIVE"
    BEHAVIORAL = "BEHAVIORAL"
    LEADERSHIP = "LEADERSHIP"
    TESTING_STRATEGY = "TESTING_STRATEGY"


class NextAction(StrEnum):
    PROBE = "PROBE"
    HINT = "HINT"
    TWIST = "TWIST"
    NEXT_TOPIC = "NEXT_TOPIC"
    END_ROUND = "END_ROUND"
    CLARIFY = "CLARIFY"
    REDIRECT = "REDIRECT"


class TopicStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COVERED = "COVERED"      # reached target depth
    PARTIAL = "PARTIAL"      # some depth, below target
    MISSED = "MISSED"        # asked, little or no correct depth
    NOT_REACHED = "NOT_REACHED"  # round ended before this topic
    SKIPPED = "SKIPPED"      # candidate asked to skip it


class Verdict(StrEnum):
    STRONG_HIRE = "STRONG_HIRE"
    HIRE = "HIRE"
    LEAN_HIRE = "LEAN_HIRE"
    LEAN_NO = "LEAN_NO"
    NO_HIRE = "NO_HIRE"
