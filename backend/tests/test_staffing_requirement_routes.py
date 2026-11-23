import unittest
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.availability import Availability
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.staffing_requirement import (
    get_staffing_requirements,
    update_staffing_requirements,
)
from app.routers.schedule import generate_full_day
from app.schemas.staffing_requirement import (
    StaffingRequirementBulkUpdate,
    StaffingRequirementUpdate,
)
from app.services.station_shifts import effective_station_shifts


class StaffingRequirementRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

        self.branch = Branch(
            name="Branch A",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.other_branch = Branch(
            name="Branch B",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.session.add_all([self.branch, self.other_branch])
        self.session.flush()
        self.manager = User(
            email="manager@example.com",
            password_hash="test-hash",
            full_name="Branch Manager",
            role=UserRole.MANAGER,
            branch_id=self.branch.id,
        )
        self.employee = User(
            email="crew@example.com",
            password_hash="test-hash",
            full_name="Crew Member",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
        )
        self.station = Station(branch_id=self.branch.id, name="Cashier")
        self.other_station = Station(branch_id=self.other_branch.id, name="Kitchen")
        self.session.add_all(
            [self.manager, self.employee, self.station, self.other_station]
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _requirements_payload(self, mid_enabled=True):
        return StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type=shift_name,
                    start_time=start,
                    end_time=end,
                    required_count=1,
                    enabled=mid_enabled if shift_name == "Mid" else True,
                )
                for shift_name, start, end in (
                    ("Opening", time(8, 0), time(16, 0)),
                    ("Mid", time(12, 0), time(20, 0)),
                    ("Closing", time(14, 0), time(22, 0)),
                )
            ]
        )

    def test_get_returns_all_station_shifts_with_default_count(self):
        requirements = get_staffing_requirements(self.session, self.manager)

        self.assertEqual(len(requirements), 3)
        self.assertEqual(
            [
                (item.shift_type, item.start_time, item.end_time, item.required_count)
                for item in requirements
            ],
            [
                ("Opening", time(8, 0), time(16, 0), 1),
                ("Mid", time(12, 0), time(20, 0), 1),
                ("Closing", time(14, 0), time(22, 0), 1),
            ],
        )

    def test_update_creates_and_updates_branch_requirements(self):
        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Opening",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    required_count=2,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Mid",
                    start_time=time(12, 0),
                    end_time=time(20, 0),
                    required_count=1,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Closing",
                    start_time=time(14, 0),
                    end_time=time(22, 0),
                    required_count=0,
                ),
            ]
        )

        result = update_staffing_requirements(payload, self.session, self.manager)
        by_shift = {item.shift_type: item.required_count for item in result}

        self.assertEqual(by_shift["Opening"], 2)
        self.assertEqual(by_shift["Mid"], 1)
        self.assertEqual(by_shift["Closing"], 0)
        self.assertEqual(
            self.session.query(StaffingRequirement)
            .filter(StaffingRequirement.branch_id == self.branch.id)
            .count(),
            3,
        )
        payload.requirements[0].required_count = 3
        updated = update_staffing_requirements(payload, self.session, self.manager)
        self.assertEqual(
            next(item.required_count for item in updated if item.shift_type == "Opening"),
            3,
        )
        self.assertEqual(
            self.session.query(StaffingRequirement)
            .filter(StaffingRequirement.branch_id == self.branch.id)
            .count(),
            3,
        )

    def test_manager_can_disable_mid_for_one_station_without_removing_it(self):
        updated = update_staffing_requirements(
            self._requirements_payload(mid_enabled=False),
            self.session,
            self.manager,
        )
        mid_settings = next(item for item in updated if item.shift_type == "Mid")
        saved = self.session.query(StaffingRequirement).filter(
            StaffingRequirement.station_id == self.station.id,
            StaffingRequirement.shift_type == "Mid",
        ).one()
        active_shifts = effective_station_shifts(
            [self.station],
            self.session.query(StaffingRequirement).filter(
                StaffingRequirement.station_id == self.station.id
            ).all(),
        )

        self.assertFalse(mid_settings.enabled)
        self.assertFalse(saved.enabled)
        self.assertEqual(
            {shift.name for shift in active_shifts},
            {"Opening", "Closing"},
        )

    def test_manager_can_reenable_mid_for_only_selected_station(self):
        update_staffing_requirements(
            self._requirements_payload(mid_enabled=False),
            self.session,
            self.manager,
        )
        updated = update_staffing_requirements(
            self._requirements_payload(mid_enabled=True),
            self.session,
            self.manager,
        )

        self.assertTrue(next(item for item in updated if item.shift_type == "Mid").enabled)

    def test_schedule_generation_omits_disabled_mid_shift(self):
        update_staffing_requirements(
            self._requirements_payload(mid_enabled=False),
            self.session,
            self.manager,
        )
        schedule_date = date.today() + timedelta(days=1)
        crew = User(
            email="scheduler-crew@example.com",
            password_hash="test-hash",
            full_name="Available Crew",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
            qualified_stations=str(self.station.id),
            max_hours=40,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(Availability(
            user_id=crew.id,
            day_of_week=schedule_date.strftime("%A"),
            start_time=time(0, 0),
            end_time=time(23, 59),
            valid_from=schedule_date,
            valid_to=schedule_date,
        ))
        self.session.commit()

        result = generate_full_day(schedule_date, self.session, self.manager)

        self.assertEqual(
            {row["shift"] for row in result["schedule"]},
            {"Opening", "Closing"},
        )

    def test_update_rejects_station_from_another_branch(self):
        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.other_station.id,
                    shift_type="Opening",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    required_count=2,
                )
            ]
        )

        with self.assertRaises(HTTPException) as raised:
            update_staffing_requirements(payload, self.session, self.manager)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(
            self.session.query(StaffingRequirement).count(),
            0,
        )

    def test_update_rejects_nonstandard_shift_names(self):
        with self.assertRaises(ValueError):
            StaffingRequirementUpdate(
                station_id=self.station.id,
                shift_type="Breakfast Rush",
                start_time=time(6, 30),
                end_time=time(11, 45),
                required_count=4,
            )

    def test_update_requires_all_standard_shift_settings_for_each_station(self):
        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Opening",
                    start_time=time(6, 30),
                    end_time=time(11, 45),
                    required_count=1,
                )
            ]
        )

        with self.assertRaises(HTTPException) as raised:
            update_staffing_requirements(payload, self.session, self.manager)

        self.assertEqual(raised.exception.status_code, 422)

    def test_non_manager_cannot_read_or_update_requirements(self):
        with self.assertRaises(HTTPException) as get_error:
            get_staffing_requirements(self.session, self.employee)
        self.assertEqual(get_error.exception.status_code, 403)

        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Opening",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    required_count=2,
                )
            ]
        )
        with self.assertRaises(HTTPException) as update_error:
            update_staffing_requirements(payload, self.session, self.employee)
        self.assertEqual(update_error.exception.status_code, 403)

    def test_bulk_schema_rejects_duplicate_station_shifts(self):
        with self.assertRaises(ValueError):
            StaffingRequirementBulkUpdate(
                requirements=[
                    StaffingRequirementUpdate(
                        station_id=1,
                        shift_type="Opening",
                        start_time=time(8, 0),
                        end_time=time(16, 0),
                        required_count=1,
                    ),
                    StaffingRequirementUpdate(
                        station_id=1,
                        shift_type="Opening",
                        start_time=time(8, 0),
                        end_time=time(16, 0),
                        required_count=2,
                    ),
                ]
            )

    def test_bulk_schema_rejects_invalid_counts_and_shifts(self):
        for item in (
            {
                "station_id": 1, "shift_type": "Opening",
                "start_time": "08:00", "end_time": "16:00", "required_count": -1,
            },
            {
                "station_id": 1, "shift_type": "Overnight",
                "start_time": "22:00", "end_time": "06:00", "required_count": 1,
            },
            {
                "station_id": 1, "shift_type": "Mid",
                "start_time": "12:00", "end_time": "20:00", "required_count": 101,
            },
        ):
            with self.subTest(item=item), self.assertRaises(ValueError):
                StaffingRequirementUpdate(**item)

    def test_any_shift_can_be_disabled(self):
        # Opening, Mid, at Closing ay puwedeng i-disable.
        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Opening",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    required_count=1,
                    enabled=True,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Mid",
                    start_time=time(12, 0),
                    end_time=time(20, 0),
                    required_count=1,
                    enabled=False,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Closing",
                    start_time=time(14, 0),
                    end_time=time(22, 0),
                    required_count=1,
                    enabled=False,
                ),
            ]
        )
        result = update_staffing_requirements(payload, self.session, self.manager)
        enabled = {item.shift_type: item.enabled for item in result}
        self.assertTrue(enabled["Opening"])
        self.assertFalse(enabled["Mid"])
        self.assertFalse(enabled["Closing"])

    def test_update_rejects_station_with_zero_enabled_shifts(self):
        # Bawat station kailangang may o kusa ang isang enabled shift.
        payload = StaffingRequirementBulkUpdate(
            requirements=[
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Opening",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    required_count=1,
                    enabled=False,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Mid",
                    start_time=time(12, 0),
                    end_time=time(20, 0),
                    required_count=1,
                    enabled=False,
                ),
                StaffingRequirementUpdate(
                    station_id=self.station.id,
                    shift_type="Closing",
                    start_time=time(14, 0),
                    end_time=time(22, 0),
                    required_count=1,
                    enabled=False,
                ),
            ]
        )
        with self.assertRaises(HTTPException) as raised:
            update_staffing_requirements(payload, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 422)
        self.assertIn("at least one enabled shift", raised.exception.detail.lower())


if __name__ == "__main__":
    unittest.main()
