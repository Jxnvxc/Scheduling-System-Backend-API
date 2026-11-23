import unittest
from datetime import date, time, timedelta
from types import SimpleNamespace

from app.services.scheduling import (
    ScheduleCandidate,
    employee_is_available,
    fairness_priority,
    shift_hours,
    unfilled_slot_reason,
    validate_schedule,
)


class ScheduleValidationTests(unittest.TestCase):
    def setUp(self):
        self.schedule_date = date(2026, 10, 26)
        self.employee = SimpleNamespace(
            id=1,
            full_name="Crew Member",
            qualified_stations="7",
            min_hours=16,
            max_hours=40,
        )
        self.station = SimpleNamespace(
            id=7,
            name="Kitchen",
            opening_start_time=time(8, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )
        self.availability = SimpleNamespace(
            user_id=1,
            day_of_week="Monday",
            valid_from=self.schedule_date - timedelta(days=7),
            valid_to=self.schedule_date + timedelta(days=30),
            start_time=time(8, 0),
            end_time=time(22, 0),
        )
        self.candidate = ScheduleCandidate(
            user_id=1,
            station_id=7,
            shift_name="Opening",
        )

    def validate(self, candidates=None, existing=None, requirements=None, employee=None):
        return validate_schedule(
            candidates=candidates if candidates is not None else [self.candidate],
            employees={1: employee or self.employee},
            stations={7: self.station},
            availabilities={1: [self.availability]},
            existing_assignments=existing or [],
            requirements=requirements if requirements is not None else {(7, "Opening"): 1},
            schedule_date=self.schedule_date,
        )

    def test_accepts_available_qualified_employee_within_hour_limit(self):
        self.assertEqual(self.validate(), [])

    def test_fairness_priority_first_favors_minimum_hours_then_lower_hours(self):
        below_minimum = SimpleNamespace(id=1, min_hours=16)
        at_minimum = SimpleNamespace(id=2, min_hours=16)
        higher_hours = SimpleNamespace(id=3, min_hours=0)

        self.assertLess(fairness_priority(below_minimum, 8), fairness_priority(at_minimum, 16))
        self.assertLess(fairness_priority(at_minimum, 16), fairness_priority(higher_hours, 24))

    def test_rejects_employee_without_station_qualification(self):
        employee = SimpleNamespace(
            id=1,
            full_name="Crew Member",
            qualified_stations="8",
            min_hours=0,
            max_hours=40,
        )

        errors = self.validate(employee=employee)

        self.assertTrue(any("not qualified" in error for error in errors))

    def test_rejects_employee_outside_availability(self):
        self.availability.end_time = time(15, 0)

        errors = self.validate()

        self.assertTrue(any("not available" in error for error in errors))

    def test_rejects_weekly_maximum_hours_exceeded(self):
        existing = [
            SimpleNamespace(
                user_id=1,
                station_id=7,
                shift_name="Opening",
                schedule_date=self.schedule_date + timedelta(days=offset),
            )
            for offset in range(1, 6)
        ]

        errors = self.validate(existing=existing)

        self.assertTrue(any("weekly maximum" in error for error in errors))

    def test_rejects_insufficient_rest_between_consecutive_shifts(self):
        existing = [
            SimpleNamespace(
                user_id=1,
                station_id=7,
                shift_name="Closing",
                schedule_date=self.schedule_date - timedelta(days=1),
            )
        ]

        errors = self.validate(existing=existing)

        self.assertTrue(any("11-hour minimum rest" in error for error in errors))

    def test_rejects_overlapping_shifts_on_same_day(self):
        candidates = [
            self.candidate,
            ScheduleCandidate(user_id=1, station_id=7, shift_name="Mid"),
        ]

        errors = self.validate(
            candidates=candidates,
            requirements={(7, "Opening"): 1, (7, "Mid"): 1},
        )

        self.assertTrue(any("11-hour minimum rest" in error for error in errors))

    def test_rejects_schedule_with_staffing_shortage(self):
        errors = self.validate(requirements={(7, "Opening"): 2})

        self.assertTrue(any("staffing shortage (1/2)" in error for error in errors))

    def test_station_specific_closing_hours_drive_duration_and_availability(self):
        self.station.closing_start_time = time(14, 0)
        self.station.closing_end_time = time(20, 0)
        self.availability.start_time = time(14, 0)
        self.availability.end_time = time(20, 0)

        self.assertEqual(shift_hours("Closing", station=self.station), 6)
        self.assertTrue(
            self.validate(
                candidates=[
                    ScheduleCandidate(
                        user_id=1,
                        station_id=7,
                        shift_name="Closing",
                    )
                ],
                requirements={(7, "Closing"): 1},
            ) == []
        )

    def test_assignment_time_snapshot_preserves_published_hours(self):
        existing = [
            SimpleNamespace(
                user_id=1,
                station_id=7,
                shift_name="Closing",
                schedule_date=self.schedule_date - timedelta(days=1),
                start_time=time(14, 0),
                end_time=time(22, 0),
            )
        ]
        self.station.closing_start_time = time(16, 0)
        self.station.closing_end_time = time(18, 0)
        candidate = ScheduleCandidate(user_id=1, station_id=7, shift_name="Opening")
        self.availability.start_time = time(8, 0)
        self.availability.end_time = time(16, 0)

        errors = self.validate(candidates=[candidate], existing=existing)

        self.assertTrue(any("11-hour minimum rest" in error for error in errors))


class AvailabilityUnionTests(unittest.TestCase):
    def setUp(self):
        self.schedule_date = date(2026, 11, 12)  # Thursday
        self.station = SimpleNamespace(
            id=7,
            name="Kitchen",
            opening_start_time=time(8, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )

    def availability(self, day, start, end, valid_from=None, valid_to=None):
        return SimpleNamespace(
            user_id=1,
            day_of_week=day,
            valid_from=valid_from or self.schedule_date,
            valid_to=valid_to or self.schedule_date,
            start_time=start,
            end_time=end,
        )

    def test_available_when_shift_covered_by_union_of_split_windows(self):
        # Opening 08:00-16:00 covered by 08:00-14:00 + 10:00-16:00
        availabilities = [
            self.availability("Thursday", time(8, 0), time(14, 0)),
            self.availability("Thursday", time(10, 0), time(16, 0)),
        ]
        self.assertTrue(
            employee_is_available(
                availabilities, self.schedule_date, "Opening", self.station
            )
        )

    def test_not_available_when_windows_have_gap_inside_shift(self):
        # Opening 08:00-16:00 NOT covered by 08:00-14:00 + 16:00-22:00 (gap 14:00-16:00)
        availabilities = [
            self.availability("Thursday", time(8, 0), time(14, 0)),
            self.availability("Thursday", time(16, 0), time(22, 0)),
        ]
        self.assertFalse(
            employee_is_available(
                availabilities, self.schedule_date, "Opening", self.station
            )
        )

    def test_not_available_wrong_day(self):
        availabilities = [
            self.availability("Friday", time(8, 0), time(22, 0)),
        ]
        self.assertFalse(
            employee_is_available(
                availabilities, self.schedule_date, "Opening", self.station
            )
        )

    def test_not_available_outside_valid_range(self):
        availabilities = [
            SimpleNamespace(
                user_id=1,
                day_of_week="Thursday",
                valid_from=self.schedule_date + timedelta(days=1),
                valid_to=self.schedule_date + timedelta(days=30),
                start_time=time(8, 0),
                end_time=time(22, 0),
            ),
        ]
        self.assertFalse(
            employee_is_available(
                availabilities, self.schedule_date, "Opening", self.station
            )
        )


class UnfilledSlotReasonTests(unittest.TestCase):
    def setUp(self):
        self.schedule_date = date(2026, 11, 12)
        self.station = SimpleNamespace(id=7, name="Kitchen")
        self.start = time(8, 0)
        self.end = time(16, 0)
        self.employee = SimpleNamespace(id=1, full_name="Crew", max_hours=40)
        self.assignments_for_rest = []
        self.stations = {7: self.station}

    def _reason(self, qualified, available, **overrides):
        kwargs = dict(
            assigned_employee_ids_today=set(),
            scheduled_hours={},
            shift_name="Opening",
            station=self.station,
            start_time=self.start,
            end_time=self.end,
            schedule_date=self.schedule_date,
            assignments_for_rest=self.assignments_for_rest,
            stations=self.stations,
        )
        kwargs.update(overrides)
        return unfilled_slot_reason(qualified, available, **kwargs)

    def test_reason_no_qualified_crew(self):
        self.assertEqual(
            self._reason([], []),
            "Walang qualified na crew para sa station na ito.",
        )

    def test_reason_qualified_but_none_available(self):
        self.assertEqual(
            self._reason([self.employee], []),
            "Walang crew na available sa oras ng shift na ito.",
        )

    def test_reason_all_assigned_today(self):
        self.assertEqual(
            self._reason(
                [self.employee],
                [self.employee],
                assigned_employee_ids_today={1},
            ),
            "Lahat ng kwalipikadong at available na crew ay may schedule na "
            "ngayong araw (isa lang ang shift bawat araw).",
        )

    def test_reason_weekly_max_hours(self):
        employee = SimpleNamespace(id=1, full_name="Crew", max_hours=8)
        self.assertEqual(
            self._reason(
                [employee],
                [employee],
                scheduled_hours={1: 40},
            ),
            "Lampas sa weekly maximum na oras ng mga kwalipikadong crew.",
        )

    def test_reason_rest_rule(self):
        yesterday = self.schedule_date - timedelta(days=1)
        self.assignments_for_rest = [
            SimpleNamespace(
                user_id=1,
                station_id=7,
                shift_name="Closing",
                schedule_date=yesterday,
                start_time=time(14, 0),
                end_time=time(22, 0),
            )
        ]
        self.assertEqual(
            self._reason([self.employee], [self.employee]),
            "Kulang sa 11-hour minimum rest pagkatapos ng nakaraang shift.",
        )


if __name__ == "__main__":
    unittest.main()
