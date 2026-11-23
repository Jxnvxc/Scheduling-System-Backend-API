import unittest
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.assignment import ShiftAssignment
from app.models.availability import Availability
from app.models.branch import Branch
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.availability import (
    replace_crew_availability,
    get_crew_availability,
)
from app.schemas.availability import (
    AvailabilityWindow,
    CrewAvailabilityRequest,
)


class AvailabilityCrewRouteTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.branch = Branch(
            name="Test Branch",
            opening_time=time(10, 0),
            closing_time=time(22, 0),
        )
        self.session.add(self.branch)
        self.session.flush()
        self.station = Station(
            branch_id=self.branch.id,
            name="Cashier",
            opening_start_time=time(10, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )
        self.session.add(self.station)
        self.session.flush()
        self.manager = User(
            email="manager@example.com",
            password_hash="test-hash",
            full_name="Test Manager",
            role=UserRole.MANAGER,
            branch_id=self.branch.id,
        )
        self.session.add(self.manager)
        self.session.flush()
        self.crew = User(
            email="crew@example.com",
            password_hash="test-hash",
            full_name="Test Crew",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
        )
        self.session.add(self.crew)
        self.session.flush()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_get_crew_availability_returns_empty_when_none(self):
        result = get_crew_availability(self.crew.id, self.session, self.manager)
        self.assertEqual(result.employee_id, self.crew.id)
        self.assertEqual(result.full_name, "Test Crew")
        self.assertEqual(result.windows, [])

    def test_get_crew_availability_returns_active_windows(self):
        today = date.today()
        a = Availability(
            user_id=self.crew.id,
            day_of_week="Monday",
            start_time=time(8, 0),
            end_time=time(16, 0),
            valid_from=today,
            valid_to=today + timedelta(days=30),
        )
        self.session.add(a)
        self.session.commit()

        result = get_crew_availability(self.crew.id, self.session, self.manager)
        self.assertEqual(len(result.windows), 1)
        self.assertEqual(result.windows[0].day_of_week, "Monday")

    def test_get_crew_availability_excludes_expired(self):
        today = date.today()
        a = Availability(
            user_id=self.crew.id,
            day_of_week="Monday",
            start_time=time(8, 0),
            end_time=time(16, 0),
            valid_from=today - timedelta(days=30),
            valid_to=today - timedelta(days=1),
        )
        self.session.add(a)
        self.session.commit()

        result = get_crew_availability(self.crew.id, self.session, self.manager)
        self.assertEqual(result.windows, [])

    def test_put_replaces_availability_and_closes_old(self):
        today = date.today()
        old = Availability(
            user_id=self.crew.id,
            day_of_week="Monday",
            start_time=time(8, 0),
            end_time=time(16, 0),
            valid_from=today,
            valid_to=today + timedelta(days=30),
        )
        self.session.add(old)
        self.session.commit()

        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week="Monday",
                    start_time=time(9, 0),
                    end_time=time(17, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
                AvailabilityWindow(
                    day_of_week="Tuesday",
                    start_time=time(10, 0),
                    end_time=time(18, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=False,
        )

        result = replace_crew_availability(self.crew.id, request, self.session, self.manager)

        self.assertEqual(len(result.windows), 2)
        days = {w.day_of_week for w in result.windows}
        self.assertEqual(days, {"Monday", "Tuesday"})

        self.session.expire_all()
        closed = self.session.query(Availability).filter(
            Availability.user_id == self.crew.id,
            Availability.valid_to == today - timedelta(days=1),
        ).all()
        self.assertEqual(len(closed), 1)
        self.assertEqual(closed[0].start_time, time(8, 0))
        self.assertEqual(closed[0].end_time, time(16, 0))

    def test_put_rejects_end_before_start(self):
        today = date.today()
        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week="Monday",
                    start_time=time(16, 0),
                    end_time=time(8, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=False,
        )
        with self.assertRaises(HTTPException) as raised:
            replace_crew_availability(self.crew.id, request, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 400)

    def test_put_rejects_overlapping_windows(self):
        today = date.today()
        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week="Monday",
                    start_time=time(8, 0),
                    end_time=time(14, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
                AvailabilityWindow(
                    day_of_week="Monday",
                    start_time=time(12, 0),
                    end_time=time(18, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=False,
        )
        with self.assertRaises(HTTPException) as raised:
            replace_crew_availability(self.crew.id, request, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 400)

    def test_put_rejects_invalid_day(self):
        today = date.today()
        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week="Funday",
                    start_time=time(8, 0),
                    end_time=time(16, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=False,
        )
        with self.assertRaises(HTTPException) as raised:
            replace_crew_availability(self.crew.id, request, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 400)

    def test_put_conflict_returns_409_without_confirm(self):
        today = date.today()
        self.session.add(
            ShiftAssignment(
                user_id=self.crew.id,
                branch_id=self.branch.id,
                station_id=self.station.id,
                schedule_date=today,
                shift_name="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                status="Published",
            )
        )
        self.session.commit()

        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week=today.strftime("%A"),
                    start_time=time(10, 0),
                    end_time=time(14, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=False,
        )
        with self.assertRaises(HTTPException) as raised:
            replace_crew_availability(self.crew.id, request, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("conflicts", raised.exception.detail)

    def test_put_conflict_succeeds_with_confirm(self):
        today = date.today()
        self.session.add(
            ShiftAssignment(
                user_id=self.crew.id,
                branch_id=self.branch.id,
                station_id=self.station.id,
                schedule_date=today,
                shift_name="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                status="Published",
            )
        )
        self.session.commit()

        request = CrewAvailabilityRequest(
            windows=[
                AvailabilityWindow(
                    day_of_week=today.strftime("%A"),
                    start_time=time(10, 0),
                    end_time=time(14, 0),
                    valid_from=today,
                    valid_to=today + timedelta(days=30),
                ),
            ],
            confirm=True,
        )
        result = replace_crew_availability(self.crew.id, request, self.session, self.manager)
        self.assertEqual(len(result.windows), 1)

    def test_get_rejects_non_manager(self):
        employee = User(
            email="emp@example.com",
            password_hash="test-hash",
            full_name="Test Employee",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
        )
        self.session.add(employee)
        self.session.flush()
        with self.assertRaises(HTTPException) as raised:
            get_crew_availability(self.crew.id, self.session, employee)
        self.assertEqual(raised.exception.status_code, 403)

    def test_get_rejects_crew_from_other_branch(self):
        other_branch = Branch(name="Other Branch", opening_time=time(10, 0), closing_time=time(22, 0))
        self.session.add(other_branch)
        self.session.flush()
        other_crew = User(
            email="other@example.com",
            password_hash="test-hash",
            full_name="Other Crew",
            role=UserRole.EMPLOYEE,
            branch_id=other_branch.id,
        )
        self.session.add(other_crew)
        self.session.flush()
        with self.assertRaises(HTTPException) as raised:
            get_crew_availability(other_crew.id, self.session, self.manager)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
