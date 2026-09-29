"""A language model fixes the whole layout turn by turn, picking from the menu of legal moves each time.

Set SP_LOOP_MODEL_URL and SP_LOOP_MODEL (an OpenAI-compatible server, such as
the Fireworks fine-tune behind scripts/finetune/fireworks_chat_server.py) and
SP_LOOP_MODEL_LABEL (what the owner's button calls it). Each turn builds the
menu for every problem still left, asks the model, applies its pick and
re-checks. The menu never covers every idea, so the model may also write its
own moves for a problem no option clears, even when the menu is empty; those
are kept only when the room then passes the same gate every option passed.
It runs for at most MODEL_LOOP_TURNS turns, each menu built within
LOOP_MENU_SECONDS. Furniture and built-in moves are offered (a slid counter
is construction, reported as such); wall shifts are not, because the owner's
plan cannot show a moved wall. Nothing is saved: the stream ends with every move the loop made, for the owner to open
in the plan and keep or not.

The loop works on what the owner's report shows: an answer resting on scan
geometry marked "needs another look" stays a question here too, so the loop
never chases something the owner sees as still to check.

A loop holds one of the owner's `ModelSlots` from the moment it is admitted
until its stream ends, and may spend at most MODEL_LOOP_TURNS calls' worth of
the chooser's `reply_seconds` in all; past that it stops and offers what it
found. A reply the loop can't read ends the stream with a failed line.
"""

from __future__ import annotations

import itertools
import json
import logging
import math
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field, replace

from standardphysics_agents.evaluation.gate import accepts
from standardphysics_agents.fix import carried_along
from standardphysics_agents.fix.budget import deadline_in
from standardphysics_agents.redesign import FurnitureMove
from standardphysics_agents.training.checker import TrainingChecker
from standardphysics_agents.training.edits import TrainingEdits, apply_edits, has_construction, node_moves, parse_edits
from standardphysics_agents.training.menu import Menu, MenuLimits, build_menu, menu_messages, resolve
from standardphysics_agents.training.owner import WishBook, stated_book
from standardphysics_contracts import (
    Finding,
    ModelLoopEvent,
    ModelLoopInfo,
    ModelLoopRequest,
    NodeMove,
    SceneGraph,
    Vec3,
    to_inches,
    to_meters,
)

from .db import Database
from .layout import plan_candidate
from .model_chooser import ModelChooser, ModelReplyError, ModelSlots, without_wall_shifts
from .proposals import fix_inputs, owner_wishes_of, space_typology_of
from .stages import Stages

log = logging.getLogger(__name__)

MODEL_LOOP_TURNS = 5
LOOP_MENU_SECONDS = 40.0
"""Longer than a single proposal's menu: built-in slides are guessed last, and on Share Tea the whole menu,
built-ins included, took 31 s. The card shows a turn clock, so the owner sees the wait."""
LOOP_ENVIRONMENT = "SP_LOOP_"
UNEXPECTED_FAILURE = "Something went wrong on our side while fixing the room. Nothing was changed. Try again."
clock: Callable[[], float] = time.monotonic


def loop_chooser() -> ModelChooser | None:
    return ModelChooser.from_environment(LOOP_ENVIRONMENT)


def loop_info() -> ModelLoopInfo:
    chooser = loop_chooser()
    return ModelLoopInfo(available=chooser is not None, label=chooser.label if chooser else "")


def _combined(moves: dict[uuid.UUID, NodeMove], added: list[NodeMove]) -> dict[uuid.UUID, NodeMove]:
    """Each piece's total move from the starting layout; a later turn's move adds to an earlier one."""
    total = dict(moves)
    for move in added:
        before = total.get(move.node_id)
        if before is None:
            total[move.node_id] = move
            continue
        total[move.node_id] = NodeMove(node_id=move.node_id, delta_translation=Vec3(
            x=before.delta_translation.x + move.delta_translation.x,
            y=before.delta_translation.y + move.delta_translation.y,
            z=before.delta_translation.z + move.delta_translation.z,
        ), delta_rotation_z_degrees=before.delta_rotation_z_degrees + move.delta_rotation_z_degrees)
    return total


def _all_moves(edits: TrainingEdits) -> list[NodeMove]:
    """Furniture moves, then each built-in's slide as a move of that piece, so the plan can show both."""
    slides = [NodeMove(node_id=move.node_id, delta_translation=Vec3(
        x=to_meters(move.dx_inches), y=to_meters(move.dy_inches), z=0.0), delta_rotation_z_degrees=0.0)
        for move in edits.fixture_moves]
    return [*node_moves(edits), *slides]


def _titles(problems: list[Finding]) -> list[str]:
    """Each open problem's title once, in the owner's words."""
    return list(dict.fromkeys(problem.title for problem in problems))


MENU_MISSES_BEFORE_OWN_MOVES = 2
"""Turns of menu picks a problem may stay open through before the loop stops offering the menu for it and asks
the model for its own moves instead, so it does not keep picking from options that have already failed it."""
GAVE_UP = "Nothing we can move or build clears what is left, so it stays on your list."


@dataclass
class ModelLoop:
    """One loop's state: the layout so far, every move made, and what to tell the model next turn."""

    start: SceneGraph
    checker: TrainingChecker
    stated: WishBook
    current: SceneGraph = field(init=False)
    moves: dict = field(default_factory=dict)
    last: dict | None = None
    menu: Menu | None = None
    stop: str = ""
    built_ins: set = field(default_factory=set)
    misses: dict[uuid.UUID, int] = field(default_factory=dict)
    """Per problem, the turns of menu picks it has stayed open through."""
    given_up: set[uuid.UUID] = field(default_factory=set)
    """Problems the model's own moves could not help either; nothing more is offered for them."""

    def __post_init__(self) -> None:
        self.current = self.start

    def offered(self) -> Menu:
        """The menu the last prompt showed; a reply only means something against it."""
        if self.menu is None:
            raise RuntimeError("a reply arrived before any menu was offered")
        return self.menu

    def open_problems(self) -> list[Finding]:
        return self.checker.fixable_problems(self.checker.assess(self.current))

    def fixable_left(self) -> int:
        return len(self.open_problems())

    def next_messages(self) -> list[dict] | None:
        """The prompt for the next turn, or None when every problem is fixed or given up."""
        open_problems = self.open_problems()
        if not open_problems:
            self.stop = "Every problem a move or a contractor can fix is fixed."
            return None
        trying = [problem for problem in open_problems if problem.id not in self.given_up]
        if not trying:
            self.stop = GAVE_UP
            return None
        self.menu = self._menu_for(trying)
        return menu_messages(self.current, self.checker, self.menu, self.last)

    def _menu_for(self, trying: list[Finding]) -> Menu:
        """The menu for the problems still worth trying, or none at all for those the menu has failed twice."""
        stuck = frozenset(problem.id for problem in trying
                          if self.misses.get(problem.id, 0) >= MENU_MISSES_BEFORE_OWN_MOVES)
        if stuck:
            labels_only = build_menu(self.current, self.checker, stated=self.stated,
                                     limits=MenuLimits(focus=stuck, deadline=deadline_in(0.0)))
            return replace(labels_only, options=[], tried_twice=list(labels_only.no_option_clears))
        limits = MenuLimits(focus=frozenset(problem.id for problem in trying), deadline=deadline_in(LOOP_MENU_SECONDS))
        return without_wall_shifts(build_menu(self.current, self.checker, stated=self.stated, limits=limits))

    def _own_idea_holds(self, edits: TrainingEdits, menu: Menu) -> bool:
        """Whether the model's own moves keep every owner wish and directive, and pass the gate every option passed."""
        after = apply_edits(self.current, edits)
        if menu.veto is not None and menu.veto(self.current, after):
            return False
        return bool(accepts(self.checker.assess(self.current), self.checker.assess(after)))

    def _apply(self, edits: TrainingEdits | None, own_idea: bool, menu: Menu) -> str:
        """Makes the change and returns "", or leaves the room as it was and returns why nothing changed."""
        added = _all_moves(edits) if edits else []
        if edits is None or not (added or has_construction(edits)):
            return "The model did not pick a change that helps, so it stopped here."
        if own_idea and not self._own_idea_holds(edits, menu):
            return "The model's own idea didn't measure any better, so nothing changed and it stopped here."
        self.current = apply_edits(self.current, edits)
        self.moves = _combined(self.moves, added)
        self.built_ins |= {move.node_id for move in edits.fixture_moves}
        return ""

    def _after_turn(self, menu: Menu, own_idea: bool, refused: str, still_open: set[uuid.UUID]) -> None:
        """Gives up on what the model's own moves could not help, stops on a menu turn that changed nothing,
        and counts a miss for every problem a menu turn left open."""
        if refused:
            asked_for = {problem_id for problem_id, label in menu.problems.items() if label in menu.no_option_clears}
            if (own_idea or not menu.options) and asked_for:
                self.given_up |= asked_for
            else:
                self.stop = refused
            return
        if menu.tried_twice:
            return
        for problem_id in menu.problems:
            if problem_id in still_open:
                self.misses[problem_id] = self.misses.get(problem_id, 0) + 1

    def take(self, turn: int, reply: str) -> ModelLoopEvent:
        menu = self.offered()
        before = self.current
        resolution = resolve(reply, self.current, menu, self.checker.pinned)
        edits = parse_edits(resolution.completion)
        own_idea = resolution.interface == "free_moves"
        refused = self._apply(edits, own_idea, menu)
        open_problems = self.open_problems()
        self._after_turn(menu, own_idea, refused, {problem.id for problem in open_problems})
        self.last = {**resolution.as_dict(), "fixable_left": len(open_problems), "kept": not refused}
        picked = [menu.picked_in_owner_words(number) for number in resolution.applied]
        if own_idea and edits is not None and not refused:
            picked = [_own_move_words(before, move) for move in edits.moves]
        construction = [menu.picked_in_owner_words(number) for number in resolution.applied
                        if (option := menu.option(number)) is not None and has_construction(option.edits)]
        return ModelLoopEvent(kind="turn", turn=turn, picked=picked, construction=construction,
                              why=menu.in_owner_words(resolution.why),
                              fixable_left=len(open_problems), working_on=_titles(open_problems))


def _own_move_words(graph: SceneGraph, move: FurnitureMove) -> str:
    """A move the model wrote itself, in the owner's words."""
    label = graph.by_id(move.node_id).label
    inches = to_inches(math.hypot(move.dx, move.dy))
    degrees = f"{abs(move.rotation_degrees):.0f} degrees"
    if inches < 0.5:
        return f"turn {label} {degrees}"
    if abs(move.rotation_degrees) < 1:
        return f"slide {label} {inches:.0f} in"
    return f"slide {label} {inches:.0f} in and turn it {degrees}"


def _in_words(seconds: float) -> str:
    return f"{seconds / 60:g} minutes" if seconds >= 120 and seconds % 60 == 0 else f"{seconds:g} seconds"


@dataclass(frozen=True)
class Plan:
    """Where the loop starts: the saved shop with the owner's unsaved moves, and those moves."""

    start: SceneGraph
    moves: list[NodeMove]
    built_ins: set[uuid.UUID]


def _plan(graph: SceneGraph, moves: list[NodeMove]) -> Plan | str:
    """The owner's plan to start from, or why it cannot be a starting point."""
    if not moves:
        return Plan(graph, [], set())
    start, blocked = plan_candidate(graph, moves, construction=True)
    if blocked:
        return f"Your plan has something where it can't stand ({blocked[0].detail}). Move it, then try again."
    carried = carried_along(graph, moves)
    fixtures = {move.node_id for move in carried if not graph.by_id(move.node_id).movable}
    return Plan(start.model_copy(update={"revision": graph.revision}), carried, fixtures)


def _proposed(loop: ModelLoop, plan: Plan) -> list[uuid.UUID]:
    """The pieces whose move differs from the plan the loop started with."""
    started = {move.node_id: move for move in plan.moves}
    return [node_id for node_id, move in loop.moves.items() if started.get(node_id) != move]


def _events(stages: Stages, graph: SceneGraph, plan: Plan, scenario, chooser: ModelChooser, typology,
            wishes) -> Iterator[ModelLoopEvent]:
    """Turns until the room is clear, the model finds nothing that helps, or the turns or time run out."""
    with stages.locked():
        checker = stages.menu_checker(plan.start, scenario, typology, scope="fittings", trust_unsure_geometry=False)
        loop = ModelLoop(plan.start, checker,
                         stated_book(plan.start, list(wishes)), moves={move.node_id: move for move in plan.moves},
                         built_ins=set(plan.built_ins))
        open_problems = loop.open_problems()
    yield ModelLoopEvent(kind="started", fixable_left=len(open_problems), working_on=_titles(open_problems),
                         turns_at_most=MODEL_LOOP_TURNS, message=f"{chooser.label} is looking at your shop.")
    budget = MODEL_LOOP_TURNS * chooser.reply_seconds
    deadline = clock() + budget
    for turn in range(1, MODEL_LOOP_TURNS + 1):
        with stages.locked():
            messages = loop.next_messages()
        if messages is None:
            break
        remaining = deadline - clock()
        if remaining <= 0:
            loop.stop = f"Stopped because the loop had used its {_in_words(budget)}. Open what it found so far."
            break
        reply = chooser.ask(messages, remaining)
        with stages.locked():
            event = loop.take(turn, reply)
        yield event
        if loop.stop:
            break
    with stages.locked():
        left = loop.fixable_left()
    explanation = stages.explain(graph, loop.current, scenario, wishes) if loop.moves else None
    yield ModelLoopEvent(kind="finished", moves=list(loop.moves.values()), built_ins=sorted(loop.built_ins, key=str),
                         proposed=_proposed(loop, plan), explanation=explanation, fixable_left=left,
                         message=loop.stop or f"Stopped after {MODEL_LOOP_TURNS} turns.")


def _line(event: ModelLoopEvent) -> str:
    return json.dumps(event.model_dump(mode="json")) + "\n"


def _failure(chooser: ModelChooser, error: Exception) -> str:
    if isinstance(error, TimeoutError):
        return f"{chooser.label} took longer than {_in_words(chooser.reply_seconds)} to answer. Try again."
    if isinstance(error, ModelReplyError):
        return f"{chooser.label} {error}, so the loop stopped. Try again."
    return f"Unable to reach {chooser.label}: {error}. Try again."


def _streamed(events: Iterator[ModelLoopEvent], chooser: ModelChooser, release: Callable[[], None]) -> Iterator[str]:
    try:
        yield from (_line(event) for event in events)
    except (OSError, ModelReplyError) as error:
        yield _line(ModelLoopEvent(kind="failed", message=_failure(chooser, error)))
    except Exception:
        log.exception("the model loop stopped on an unexpected error")
        yield _line(ModelLoopEvent(kind="failed", message=UNEXPECTED_FAILURE))
    finally:
        release()


def stream_model_loop(
    database: Database, stages: Stages, slots: ModelSlots, owner_id: uuid.UUID, scan_id: uuid.UUID,
    body: ModelLoopRequest,
) -> Iterator[str]:
    """NDJSON lines: started with the fixable count, one line per turn, then finished with every move, or failed.

    A missing scan, or an owner or server already at its cap of model calls, is
    refused before the stream starts. The first line is produced here, so the
    stream has started, and its slot comes back when it ends or is dropped.
    """
    chooser = loop_chooser()
    if chooser is None:
        return iter([_line(ModelLoopEvent(kind="failed", message="No model is set up to run the loop."))])
    graph, scenario, _ = fix_inputs(database, scan_id, body.base_revision)
    plan = _plan(graph, body.moves)
    if isinstance(plan, str):
        return iter([_line(ModelLoopEvent(kind="failed", message=plan))])
    wishes, typology = owner_wishes_of(database, scan_id), space_typology_of(database, scan_id)
    slots.take(owner_id)
    events = _events(stages, graph, plan, scenario, chooser, typology, wishes)
    lines = _streamed(events, chooser, lambda: slots.give_back(owner_id))
    return itertools.chain([next(lines)], lines)
