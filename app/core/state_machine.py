"""Round state machine. The LLM can only *request* actions; this decides what is legal."""
from .enums import NextAction, RoundStatus

ACTION_TO_STATE = {
    NextAction.PROBE: RoundStatus.PROBING,
    NextAction.TWIST: RoundStatus.PROBING,
    NextAction.HINT: RoundStatus.HINTING,
    NextAction.NEXT_TOPIC: RoundStatus.QUESTIONING,
    NextAction.END_ROUND: RoundStatus.WRAP_UP,
}

ALLOWED = {
    RoundStatus.PLANNED: {RoundStatus.QUESTIONING, RoundStatus.SKIPPED},
    RoundStatus.QUESTIONING: {RoundStatus.QUESTIONING, RoundStatus.PROBING, RoundStatus.HINTING,
                              RoundStatus.WRAP_UP, RoundStatus.ENDED_EARLY},
    RoundStatus.PROBING: {RoundStatus.PROBING, RoundStatus.HINTING, RoundStatus.QUESTIONING,
                          RoundStatus.WRAP_UP, RoundStatus.ENDED_EARLY},
    RoundStatus.HINTING: {RoundStatus.PROBING, RoundStatus.QUESTIONING, RoundStatus.HINTING,
                          RoundStatus.WRAP_UP, RoundStatus.ENDED_EARLY},
    RoundStatus.WRAP_UP: {RoundStatus.COMPLETED, RoundStatus.ENDED_EARLY},
    RoundStatus.COMPLETED: set(),
    RoundStatus.ENDED_EARLY: set(),
    RoundStatus.SKIPPED: set(),
}


class InvalidTransition(Exception):
    pass


def transition(current: RoundStatus, target: RoundStatus) -> RoundStatus:
    if target not in ALLOWED[current]:
        raise InvalidTransition(f"{current} -> {target} is not allowed")
    return target


def state_for_action(current: RoundStatus, action: NextAction) -> RoundStatus:
    """CLARIFY / REDIRECT keep the current state."""
    target = ACTION_TO_STATE.get(action, current)
    return transition(current, target)
