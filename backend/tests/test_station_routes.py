import unittest
from datetime import date, time

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.assignment import ShiftAssignment
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.station import delete_station, update_station
from app.schemas.station import StationUpdate


class StationRouteTests(unittest.TestCase):
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
        self.manager = User(
            email="manager@example.com",
            password_hash="test-hash",
            full_name="Test Manager",
            role=UserRole.MANAGER,
            branch_id=self.branch.id,
        )
        self.session.add(self.manager)
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
        self.crew_member = User(
            email="crew@example.com",
            password_hash="test-hash",
            full_name="Test Crew",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
            qualified_stations=f"{self.station.id},15",
        )
        self.session.add(self.crew_member)
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch.id,
                station_id=self.station.id,
                shift_type="Closing",
                required_count=1,
            )
        )
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_edit_updates_name_and_shift_hours(self):
        result = update_station(
            self.station.id,
            StationUpdate(
                name="Front Cashier",
                closing_start_time=time(14, 0),
                closing_end_time=time(20, 0),
            ),
            self.session,
            self.manager,
        )

        self.assertEqual(result["name"], "Front Cashier")
        self.assertEqual(result["closing_end_time"], time(20, 0))
        self.assertEqual(result["branch_id"], self.branch.id)

    def test_edit_allows_opening_and_mid_times_outside_store_hours(self):
        result = update_station(
            self.station.id,
            StationUpdate(
                name="Cashier",
                opening_start_time=time(7, 15),
                opening_end_time=time(9, 45),
                mid_start_time=time(11, 10),
                mid_end_time=time(13, 35),
            ),
            self.session,
            self.manager,
        )

        self.assertEqual(result["opening_start_time"], time(7, 15))
        self.assertEqual(result["opening_end_time"], time(9, 45))
        self.assertEqual(result["mid_start_time"], time(11, 10))
        self.assertEqual(result["mid_end_time"], time(13, 35))

    def test_create_station_requires_manager_branch_assignment(self):
        unassigned_manager = User(
            email="unassigned@example.com",
            password_hash="test-hash",
            full_name="Unassigned Manager",
            role=UserRole.MANAGER,
            branch_id=None,
        )
        self.session.add(unassigned_manager)
        self.session.commit()

        from app.routers.station import create_station
        from app.schemas.station import StationCreate

        with self.assertRaises(HTTPException) as raised:
            create_station(
                StationCreate(name="Grill"),
                self.session,
                unassigned_manager,
            )

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIn("authorized operator", raised.exception.detail)

    def test_remove_deletes_station_and_cleans_related_setup(self):
        delete_station(self.station.id, self.session, self.manager)

        self.assertIsNone(self.session.get(Station, self.station.id))
        self.assertEqual(self.crew_member.qualified_stations, "15")
        self.assertEqual(
            self.session.query(StaffingRequirement)
            .filter(StaffingRequirement.station_id == self.station.id)
            .count(),
            0,
        )

    def test_remove_refuses_station_used_in_a_schedule(self):
        self.session.add(
            ShiftAssignment(
                user_id=self.crew_member.id,
                branch_id=self.branch.id,
                station_id=self.station.id,
                schedule_date=date(2026, 10, 29),
                shift_name="Closing",
                start_time=time(14, 0),
                end_time=time(22, 0),
                status="Published",
            )
        )
        self.session.commit()

        with self.assertRaises(HTTPException) as raised:
            delete_station(self.station.id, self.session, self.manager)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertIsNotNone(self.session.get(Station, self.station.id))


if __name__ == "__main__":
    unittest.main()
