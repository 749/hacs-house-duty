"""Pure domain model for House Duty."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True, slots=True)
class Period:
    """A local, half-open duty week."""

    start: date

    @property
    def end(self) -> date:
        return self.start + timedelta(days=7)


@dataclass(frozen=True, slots=True)
class Absence:
    """Half-open absence interval."""

    start: datetime
    end: datetime


@dataclass(frozen=True, slots=True)
class Assignment:
    """Resolution of one rotation occurrence."""

    period: Period
    household_id: str | None
    originally_next: str
    skipped: tuple[str, ...] = ()

    @property
    def problem(self) -> bool:
        return self.household_id is None


def period_for(value: date | datetime) -> Period:
    """Return the Monday-based duty period containing value."""
    day = value.date() if isinstance(value, datetime) else value
    return Period(day - timedelta(days=day.weekday()))


def period_bounds(period: Period, timezone: ZoneInfo) -> tuple[datetime, datetime]:
    """Return local-midnight bounds, preserving DST semantics."""
    return (
        datetime.combine(period.start, time.min, timezone),
        datetime.combine(period.end, time.min, timezone),
    )


def overlaps_period(absence: Absence, period: Period, timezone: ZoneInfo) -> bool:
    """Return whether an absence intersects a duty period."""
    start, end = period_bounds(period, timezone)
    return absence.start < end and absence.end > start


def resolve(
    period: Period,
    household_ids: list[str],
    next_index: int,
    unavailable: set[str],
) -> tuple[Assignment, int]:
    """Consume one rotation occurrence and select the first available household.

    Every examined household consumes its turn. If everyone is absent, the cursor
    advances exactly one full cycle, so the next period starts with the same
    originally-next household and the rotation remains recoverable.
    """
    if not household_ids:
        raise ValueError("At least one household is required")
    next_index %= len(household_ids)
    original = household_ids[next_index]
    skipped: list[str] = []
    for offset in range(len(household_ids)):
        idx = (next_index + offset) % len(household_ids)
        household_id = household_ids[idx]
        if household_id not in unavailable:
            return (
                Assignment(period, household_id, original, tuple(skipped)),
                (idx + 1) % len(household_ids),
            )
        skipped.append(household_id)
    return Assignment(period, None, original, tuple(skipped)), next_index


@dataclass(slots=True)
class RotationState:
    """Materialized weekly assignments and persistent cursor."""

    anchor: Period
    household_ids: list[str]
    next_index: int
    assignments: dict[str, Assignment] = field(default_factory=dict)

    @classmethod
    def from_anchor(cls, anchor: Period, household_ids: list[str], household_id: str) -> RotationState:
        """Create state where the user-confirmed anchor assignment is authoritative."""
        index = household_ids.index(household_id)
        assignment = Assignment(anchor, household_id, household_id)
        return cls(anchor, household_ids, (index + 1) % len(household_ids), {anchor.start.isoformat(): assignment})

    def reconcile(
        self,
        through: Period,
        unavailable_by_period: dict[str, set[str]],
    ) -> list[Assignment]:
        """Materialize every missing period from the anchor through target."""
        if through.start < self.anchor.start:
            raise ValueError("Cannot reconcile before the rotation anchor")
        created: list[Assignment] = []
        cursor = self.anchor.start
        while cursor <= through.start:
            key = cursor.isoformat()
            if key not in self.assignments:
                assignment, self.next_index = resolve(
                    Period(cursor),
                    self.household_ids,
                    self.next_index,
                    unavailable_by_period.get(key, set()),
                )
                self.assignments[key] = assignment
                created.append(assignment)
            cursor += timedelta(days=7)
        return created


def normalized_title(value: str) -> str:
    """Normalize an event title for special-event comparison."""
    return " ".join(value.casefold().split())


def notification_recipients(
    kind: str,
    title: str,
    special_title: str,
    assigned_household: str,
    household_ids: list[str],
) -> list[str]:
    """Route a source event without depending on Home Assistant."""
    if kind == "garbage" and normalized_title(title) == normalized_title(special_title):
        return household_ids.copy()
    return [assigned_household]


def configuration_preserves_rotation(old_ids: list[str], new_ids: list[str]) -> bool:
    """Return whether existing cursor/assignments remain unambiguous."""
    return old_ids == new_ids
