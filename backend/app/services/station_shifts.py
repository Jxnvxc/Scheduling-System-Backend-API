from dataclasses import dataclass
from datetime import time
from typing import Iterable

from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.services.scheduling import DEFAULT_REQUIRED_COUNT, SHIFT_WINDOWS, station_shift_times


@dataclass(frozen=True)
class StationShift:
    station_id: int
    station_name: str
    name: str
    start_time: time
    end_time: time
    required_count: int
    minimum_crew: int
    enabled: bool


def effective_station_shifts(
    stations: Iterable[Station],
    saved_shifts: Iterable[StaffingRequirement],
    *,
    include_disabled: bool = False,
) -> list[StationShift]:
    stations = list(stations)
    saved_shifts = list(saved_shifts)
    shifts_by_station: dict[int, list[StaffingRequirement]] = {}
    for shift in saved_shifts:
        shifts_by_station.setdefault(shift.station_id, []).append(shift)

    definitions = []
    for station in stations:
        saved = shifts_by_station.get(station.id)
        if saved:
            definitions.extend(
                StationShift(
                    station_id=station.id,
                    station_name=station.name,
                    name=shift.shift_type,
                    start_time=shift.start_time,
                    end_time=shift.end_time,
                    required_count=shift.required_count,
                    minimum_crew=shift.minimum_crew if shift.minimum_crew is not None else shift.required_count,
                    enabled=shift.enabled,
                )
                for shift in saved
                if include_disabled or shift.enabled
            )
            continue

        for name in SHIFT_WINDOWS:
            start_time, end_time = station_shift_times(station, name)
            definitions.append(
                StationShift(
                    station_id=station.id,
                    station_name=station.name,
                    name=name,
                    start_time=start_time,
                    end_time=end_time,
                    required_count=DEFAULT_REQUIRED_COUNT,
                    minimum_crew=DEFAULT_REQUIRED_COUNT,
                    enabled=True,
                )
            )

    return sorted(
        definitions,
        key=lambda shift: (
            shift.station_name.casefold(),
            shift.start_time,
            shift.name.casefold(),
        ),
    )
