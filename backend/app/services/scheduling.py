from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import calendar
import re
from typing import Iterable, Mapping, Sequence


MINIMUM_REST_HOURS = 11
DEFAULT_REQUIRED_COUNT = 1

SHIFT_WINDOWS: dict[str, tuple[time, time]] = {
    "Opening": (time(8, 0), time(16, 0)),
    "Mid": (time(12, 0), time(20, 0)),
    "Closing": (time(14, 0), time(22, 0)),
}


@dataclass(frozen=True)
class ScheduleCandidate:
    user_id: int
    station_id: int
    shift_name: str
    start_time: time | None = None
    end_time: time | None = None


@dataclass(frozen=True)
class ScheduledAssignment:
    user_id: int
    station_id: int
    shift_name: str
    schedule_date: date
    start_time: time | None = None
    end_time: time | None = None


def station_shift_times(station: object, shift_name: str) -> tuple[time, time]:
    try:
        default_start, default_end = SHIFT_WINDOWS[shift_name]
    except KeyError as error:
        raise ValueError(f"Unsupported shift: {shift_name}") from error

    prefix = shift_name.lower()
    start_time = getattr(station, f"{prefix}_start_time", default_start)
    end_time = getattr(station, f"{prefix}_end_time", default_end)
    return start_time, end_time


def shift_interval(
    shift_date: date,
    shift_name: str,
    station: object | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
) -> tuple[datetime, datetime]:
    if start_time is None or end_time is None:
        if station is not None:
            start_time, end_time = station_shift_times(station, shift_name)
        else:
            try:
                start_time, end_time = SHIFT_WINDOWS[shift_name]
            except KeyError as error:
                raise ValueError(f"Unsupported shift: {shift_name}") from error

    return (
        datetime.combine(shift_date, start_time),
        datetime.combine(shift_date, end_time),
    )


def shift_hours(
    shift_name: str,
    station: object | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
) -> float:
    start, end = shift_interval(
        date.min,
        shift_name,
        station=station,
        start_time=start_time,
        end_time=end_time,
    )
    return (end - start).total_seconds() / 3600


def week_bounds(target_date: date) -> tuple[date, date]:
    start = target_date - timedelta(days=target_date.weekday())
    return start, start + timedelta(days=6)


def period_bounds(target_date: date) -> tuple[date, date]:
    """Return the active 15-day pay-period window for the given date.

    Period 1: day 1 to day 15 of the month.
    Period 2: day 16 to the last day of the month.
    """
    year = target_date.year
    month = target_date.month
    if target_date.day <= 15:
        return date(year, month, 1), date(year, month, 15)
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, 16), date(year, month, last_day)


def fairness_priority(employee: object, weekly_hours: float) -> tuple[int, float, int]:
    minimum_hours = getattr(employee, "min_hours", None) or 0
    return (
        int(weekly_hours >= minimum_hours),
        weekly_hours,
        employee.id,
    )


def employee_is_qualified(employee: object, station_id: int) -> bool:
    qualified_stations = getattr(employee, "qualified_stations", None)
    if not qualified_stations:
        return False
    return str(station_id) in {
        station.strip() for station in qualified_stations.split(",")
    }


def employee_is_available(
    availabilities: Sequence[object],
    shift_date: date,
    shift_name: str,
    station: object | None = None,
    start_time: time | None = None,
    end_time: time | None = None,
) -> bool:
    start, end = shift_interval(
        shift_date,
        shift_name,
        station=station,
        start_time=start_time,
        end_time=end_time,
    )
    day_name = shift_date.strftime("%A")

    windows: list[tuple[time, time]] = []
    for availability in availabilities:
        if (
            availability.day_of_week == day_name
            and availability.valid_from <= shift_date <= availability.valid_to
        ):
            windows.append((availability.start_time, availability.end_time))

    # Ang availability ng crew ay union ng kanyang windows para sa araw.
    # Tavailable siya kung naka-fit ang buong shift sa isa sa merged windows,
    # kaya pwede nang gamitin ang magkahiwalay na windows (p.,
    # 08:00-14:00 + 10:00-16:00) para sakop ng isang shift (08:00-16:00).
    return any(
        window_start <= start.time() and window_end >= end.time()
        for window_start, window_end in _merge_windows(windows)
    )


def _merge_windows(
    windows: Sequence[tuple[time, time]],
) -> list[tuple[time, time]]:
    if not windows:
        return []
    ordered = sorted(windows, key=lambda window: (window[0], window[1]))
    merged: list[list[time, time]] = [list(ordered[0])]
    for window_start, window_end in ordered[1:]:
        if window_start <= merged[-1][1]:
            if window_end > merged[-1][1]:
                merged[-1][1] = window_end
        else:
            merged.append([window_start, window_end])
    return [(start, end) for start, end in merged]


def assignment_interval(
    assignment: object,
    stations: Mapping[int, object],
) -> tuple[datetime, datetime]:
    station = stations.get(assignment.station_id)
    return shift_interval(
        assignment.schedule_date,
        assignment.shift_name,
        station=station,
        start_time=getattr(assignment, "start_time", None),
        end_time=getattr(assignment, "end_time", None),
    )


def has_minimum_rest(
    employee_id: int,
    candidate: ScheduleCandidate,
    schedule_date: date,
    assignments: Iterable[object],
    stations: Mapping[int, object],
) -> bool:
    candidate_start, candidate_end = shift_interval(
        schedule_date,
        candidate.shift_name,
        station=stations.get(candidate.station_id),
        start_time=candidate.start_time,
        end_time=candidate.end_time,
    )
    minimum_rest = timedelta(hours=MINIMUM_REST_HOURS)

    for assignment in assignments:
        if assignment.user_id != employee_id:
            continue

        existing_start, existing_end = assignment_interval(assignment, stations)
        if existing_start <= candidate_start:
            rest = candidate_start - existing_end
        else:
            rest = existing_start - candidate_end

        if rest < minimum_rest:
            return False

    return True


def unfilled_slot_reason(
    qualified_employees: Sequence[object],
    available_employees: Sequence[object],
    assigned_employee_ids_today: set[int],
    scheduled_hours: Mapping[int, int],
    shift_name: str,
    station: object,
    start_time: time | None,
    end_time: time | None,
    schedule_date: date,
    assignments_for_rest: Iterable[object],
    stations: Mapping[int, object],
) -> str:
    if not qualified_employees:
        return "Walang qualified na crew para sa station na ito."
    if not available_employees:
        return "Walang crew na available sa oras ng shift na ito."

    still_available_today = [
        employee
        for employee in available_employees
        if employee.id not in assigned_employee_ids_today
    ]
    if not still_available_today:
        return (
            "Lahat ng kwalipikadong at available na crew ay may schedule na "
            "ngayong araw (isa lang ang shift bawat araw)."
        )

    max_hours_by_employee = {
        employee.id: employee.max_hours if employee.max_hours is not None else 80
        for employee in still_available_today
    }
    if all(
        scheduled_hours.get(employee.id, 0)
        + shift_hours(shift_name, station=station, start_time=start_time, end_time=end_time)
        > max_hours_by_employee[employee.id]
        for employee in still_available_today
    ):
        return "Lampas sa weekly maximum na oras ng mga kwalipikadong crew."

    candidate_for_rest = ScheduleCandidate(
        user_id=0,
        station_id=station.id,
        shift_name=shift_name,
        start_time=start_time,
        end_time=end_time,
    )
    if all(
        not has_minimum_rest(
            employee.id,
            candidate_for_rest,
            schedule_date,
            assignments_for_rest,
            stations,
        )
        for employee in still_available_today
    ):
        return "Kulang sa 11-hour minimum rest pagkatapos ng nakaraang shift."

    return "Hindi mabukas ang slot na ito ng crew."


def unfilled_slot_breakdown(
    qualified_employees: Sequence[object],
    available_employees: Sequence[object],
    assigned_employee_ids_today: set[int],
    scheduled_hours: Mapping[int, int],
    shift_name: str,
    station: object,
    start_time: time | None,
    end_time: time | None,
    schedule_date: date,
    assignments_for_rest: Iterable[object],
    stations: Mapping[int, object],
) -> dict:
    """Return detailed counts of why each qualified employee was rejected for this slot."""
    if not qualified_employees:
        return {"no_qualified": 0, "not_available": 0, "already_assigned_today": 0, "max_hours": 0, "rest_rule": 0, "other": 0}
    if not available_employees:
        return {"no_qualified": 0, "not_available": len(qualified_employees), "already_assigned_today": 0, "max_hours": 0, "rest_rule": 0, "other": 0}

    still_available_today = [
        employee
        for employee in available_employees
        if employee.id not in assigned_employee_ids_today
    ]
    already_assigned_today = len(available_employees) - len(still_available_today)

    counts = {"no_qualified": 0, "not_available": 0, "already_assigned_today": already_assigned_today, "max_hours": 0, "rest_rule": 0, "other": 0}
    if not still_available_today:
        return counts

    shift_h = shift_hours(shift_name, station=station, start_time=start_time, end_time=end_time)
    candidate_for_rest = ScheduleCandidate(
        user_id=0,
        station_id=station.id,
        shift_name=shift_name,
        start_time=start_time,
        end_time=end_time,
    )

    for employee in still_available_today:
        max_h = employee.max_hours if employee.max_hours is not None else 80
        if scheduled_hours.get(employee.id, 0) + shift_h > max_h:
            counts["max_hours"] += 1
        elif not has_minimum_rest(
            employee.id,
            candidate_for_rest,
            schedule_date,
            assignments_for_rest,
            stations,
        ):
            counts["rest_rule"] += 1
        else:
            counts["other"] += 1

    counts["not_available"] = len(qualified_employees) - len(available_employees)
    return counts


def validate_schedule(
    candidates: Sequence[ScheduleCandidate],
    employees: Mapping[int, object],
    stations: Mapping[int, object],
    availabilities: Mapping[int, Sequence[object]],
    existing_assignments: Sequence[object],
    requirements: Mapping[tuple[int, str], int],
    schedule_date: date,
    unavailable_dates: Mapping[int, Sequence[date]] | None = None,
) -> list[str]:
    errors: list[str] = []
    period_start, period_end = period_bounds(schedule_date)
    existing_for_hours: dict[int, int] = defaultdict(int)

    for assignment in existing_assignments:
        if (
            period_start <= assignment.schedule_date <= period_end
            and assignment.schedule_date != schedule_date
        ):
            station = stations.get(assignment.station_id)
            existing_for_hours[assignment.user_id] += shift_hours(
                assignment.shift_name,
                station=station,
                start_time=getattr(assignment, "start_time", None),
                end_time=getattr(assignment, "end_time", None),
            )

    scheduled_hours = dict(existing_for_hours)
    assignments_for_rest = [
        assignment
        for assignment in existing_assignments
        if assignment.schedule_date != schedule_date
    ]
    counts: dict[tuple[int, str], int] = defaultdict(int)
    seen_employee_shifts: set[tuple[int, int, str]] = set()
    seen_employee_ids: set[int] = set()

    for candidate in candidates:
        employee = employees.get(candidate.user_id)
        station = stations.get(candidate.station_id)
        if employee is None or station is None:
            errors.append("Assignments must use active crew and stations from your branch.")
            continue

        requirement_key = (candidate.station_id, candidate.shift_name)
        if requirement_key not in requirements:
            errors.append(f"{employee.full_name}: unsupported shift '{candidate.shift_name}'.")
            continue
        key = (candidate.user_id, candidate.station_id, candidate.shift_name)
        if key in seen_employee_shifts:
            errors.append(
                f"{employee.full_name}: assigned more than once to the {candidate.shift_name} shift."
            )
            continue
        seen_employee_shifts.add(key)
        if candidate.user_id in seen_employee_ids:
            errors.append(
                f"{employee.full_name}: assigned more than once on the same day."
            )
        seen_employee_ids.add(candidate.user_id)

        if not employee_is_qualified(employee, candidate.station_id):
            errors.append(
                f"{employee.full_name} is not qualified for {station.name}."
            )

        if schedule_date in (unavailable_dates or {}).get(candidate.user_id, ()):
            errors.append(f"{employee.full_name} has approved leave on this date.")
        elif not employee_is_available(
            availabilities.get(candidate.user_id, []),
            schedule_date,
            candidate.shift_name,
            station,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
        ):
            errors.append(
                f"{employee.full_name} is not available for {candidate.shift_name}."
            )

        if not has_minimum_rest(
            candidate.user_id,
            candidate,
            schedule_date,
            assignments_for_rest,
            stations,
        ):
            errors.append(
                f"{employee.full_name} does not meet the {MINIMUM_REST_HOURS}-hour minimum rest rule."
            )

        worked_hours = scheduled_hours.get(candidate.user_id, 0)
        candidate_hours = shift_hours(
            candidate.shift_name,
            station=station,
            start_time=candidate.start_time,
            end_time=candidate.end_time,
        )
        maximum_hours = employee.max_hours if employee.max_hours is not None else 80
        if worked_hours + candidate_hours > maximum_hours:
            errors.append(
                f"{employee.full_name} would exceed the weekly maximum of {maximum_hours} hours."
            )
        scheduled_hours[candidate.user_id] = worked_hours + candidate_hours

        counts[(candidate.station_id, candidate.shift_name)] += 1
        assignments_for_rest.append(
            ScheduledAssignment(
                user_id=candidate.user_id,
                station_id=candidate.station_id,
                shift_name=candidate.shift_name,
                schedule_date=schedule_date,
                start_time=candidate.start_time,
                end_time=candidate.end_time,
            )
        )

    for (station_id, shift_name), required_count in requirements.items():
        assigned_count = counts[(station_id, shift_name)]
        if assigned_count < required_count:
            station = stations.get(station_id)
            station_name = station.name if station else f"Station {station_id}"
            errors.append(
                f"{station_name} ({shift_name}): staffing shortage "
                f"({assigned_count}/{required_count})."
            )

    return errors


_REASON_BY_TYPE = {
    "staffing_shortage": "Staffing shortage ({assigned}/{required}). Kulang sa crew para sa slot na ito.",
    "not_qualified": "Walang qualified na crew para sa station na ito.",
    "not_available": "Walang available sa oras ng shift na ito.",
    "rest_rule": "Kulang sa 11-hour minimum rest pagkatapos ng nakaraang shift.",
    "max_hours": "Lampas sa weekly maximum na oras.",
    "leave": "May approved na leave sa petsang ito.",
    "duplicate_day": "May schedule na ngayong araw (isa lang ang shift bawat araw).",
    "duplicate_shift": "Naka-assign na sa parehong shift ngayong araw.",
    "unsupported_shift": "Hindi supported na shift.",
    "general": "Kailangang ayusin ang assignment.",
}


def _issue(
    issue_type: str,
    reason: str,
    message: str,
    station: str | None = None,
    shift: str | None = None,
    crew: str | None = None,
) -> dict:
    return {
        "type": issue_type,
        "station": station,
        "shift": shift,
        "crew": crew,
        "reason": reason,
        "message": message,
    }


def structured_issues(errors: Sequence[str], stations: Mapping[int, object] | None = None) -> list[dict]:
    """Parse flat validation error strings into structured issues.

    Each issue has: type, station, shift, crew, reason, message.
    station/shift/crew are filled in only when the error text carries them,
    so callers can still scroll to/highlight the affected row when possible.
    """
    issues: list[dict] = []
    stations = stations or {}

    for message in errors:
        text = message.strip()

        match = re.match(
            r"^(?P<station>.+) \((?P<shift>[^)]+)\): staffing shortage "
            r"\((?P<assigned>\d+)/(?P<required>\d+)\)\.$",
            text,
        )
        if match:
            issues.append(
                _issue(
                    "staffing_shortage",
                    _REASON_BY_TYPE["staffing_shortage"].format(
                        assigned=match.group("assigned"),
                        required=match.group("required"),
                    ),
                    text,
                    station=match.group("station"),
                    shift=match.group("shift"),
                )
            )
            continue

        match = re.match(r"^(?P<crew>.+) is not qualified for (?P<station>.+)\.$", text)
        if match:
            issues.append(
                _issue(
                    "not_qualified",
                    _REASON_BY_TYPE["not_qualified"],
                    text,
                    station=match.group("station"),
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(r"^(?P<crew>.+) is not available for (?P<shift>.+)\.$", text)
        if match:
            issues.append(
                _issue(
                    "not_available",
                    _REASON_BY_TYPE["not_available"],
                    text,
                    shift=match.group("shift"),
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(
            r"^(?P<crew>.+) does not meet the (?P<hours>\d+)-hour minimum rest rule\.$",
            text,
        )
        if match:
            issues.append(
                _issue(
                    "rest_rule",
                    _REASON_BY_TYPE["rest_rule"],
                    text,
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(
            r"^(?P<crew>.+) would exceed the weekly maximum of (?P<hours>\d+) hours\.$",
            text,
        )
        if match:
            issues.append(
                _issue(
                    "max_hours",
                    _REASON_BY_TYPE["max_hours"],
                    text,
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(r"^(?P<crew>.+) has approved leave on this date\.$", text)
        if match:
            issues.append(
                _issue(
                    "leave",
                    _REASON_BY_TYPE["leave"],
                    text,
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(
            r"^(?P<crew>.+): assigned more than once on the same day\.$", text
        )
        if match:
            issues.append(
                _issue(
                    "duplicate_day",
                    _REASON_BY_TYPE["duplicate_day"],
                    text,
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(
            r"^(?P<crew>.+): assigned more than once to the '(?P<shift>[^']+)' shift\.$",
            text,
        )
        if match:
            issues.append(
                _issue(
                    "duplicate_shift",
                    _REASON_BY_TYPE["duplicate_shift"],
                    text,
                    shift=match.group("shift"),
                    crew=match.group("crew"),
                )
            )
            continue

        match = re.match(
            r"^(?P<crew>.+): unsupported shift '(?P<shift>[^']+)'\.$", text
        )
        if match:
            issues.append(
                _issue(
                    "unsupported_shift",
                    _REASON_BY_TYPE["unsupported_shift"],
                    text,
                    shift=match.group("shift"),
                    crew=match.group("crew"),
                )
            )
            continue

        if "active crew and stations" in text:
            issues.append(
                _issue("general", _REASON_BY_TYPE["general"], text)
            )
            continue

        issues.append(
            _issue("general", _REASON_BY_TYPE["general"], text)
        )

    return issues
