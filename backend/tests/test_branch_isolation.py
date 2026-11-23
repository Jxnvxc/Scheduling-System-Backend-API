import unittest
from datetime import date, time
from inspect import signature
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.availability import Availability
from app.models.assignment import ShiftAssignment
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.schedule import Schedule
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.branch import get_my_branch
from app.routers.crew import (
    assign_employee_number,
    create_crew,
    delete_crew,
    get_all_crew,
    update_qualified_stations,
)
from app.routers.head import (
    assign_manager_branch,
    create_branch,
    create_manager,
    list_branches,
    list_managers,
    update_manager,
)
from app.routers.schedule import (
    PublishRequest,
    acknowledge_my_schedule,
    generate_full_day,
    get_manager_schedule_tracking,
    get_my_schedule,
    get_schedule_draft,
    get_all_schedules,
    publish_schedule,
    save_schedule_draft,
    validate_schedule_draft,
)
from app.routers.station import (
    create_station,
    delete_station,
    get_all_stations,
    update_station,
)
from app.schemas.crew import (
    CrewCreate,
    CrewEmployeeNumberUpdate,
    CrewQualifiedStationsUpdate,
)
from app.schemas.head import (
    HeadManagerCreate,
    HeadManagerUpdate,
    ManagerBranchAssignment,
)
from app.schemas.branch import BranchCreate
from app.schemas.station import StationCreate, StationUpdate


class BranchIsolationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.branch_a = self._branch("North Branch")
        self.branch_b = self._branch("South Branch")
        self.manager_a = self._manager("manager-a@example.com", self.branch_a.id)
        self.manager_b = self._manager("manager-b@example.com", self.branch_b.id)
        self.head = User(
            email="head@example.com",
            password_hash="hash",
            full_name="Head Account",
            role=UserRole.HEAD,
            branch_id=None,
        )
        self.session.add(self.head)
        self.station_a = self._station("Cashier A", self.branch_a.id)
        self.station_b = self._station("Cashier B", self.branch_b.id)
        self.crew_b = User(
            email="crew-b@example.com",
            password_hash="hash",
            full_name="Crew B",
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_b.id,
        )
        self.session.add(self.crew_b)
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _branch(self, name):
        branch = Branch(
            name=name,
            opening_time=time(10, 0),
            closing_time=time(22, 0),
        )
        self.session.add(branch)
        self.session.flush()
        return branch

    def _manager(self, email, branch_id):
        manager = User(
            email=email,
            password_hash="hash",
            full_name="Manager",
            role=UserRole.MANAGER,
            branch_id=branch_id,
        )
        self.session.add(manager)
        self.session.flush()
        return manager

    def _station(self, name, branch_id):
        station = Station(
            branch_id=branch_id,
            name=name,
            opening_start_time=time(8, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )
        self.session.add(station)
        self.session.flush()
        return station

    def test_manager_can_only_read_the_assigned_branch(self):
        branches = get_my_branch(self.session, self.manager_a)
        self.assertEqual([branch.id for branch in branches], [self.branch_a.id])

    def test_schedule_generation_uses_only_assigned_branch_requirements(self):
        crew_a = User(
            email="crew-a@example.com",
            password_hash="hash",
            full_name="Ana Santos",
            crew_type="Crew Trainer",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew_a)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew_a.id,
                day_of_week="Tuesday",
                start_time=time(8, 0),
                end_time=time(22, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_b.id,
                station_id=self.station_b.id,
                shift_type="Opening",
                required_count=4,
            )
        )
        self.session.commit()

        result = generate_full_day(date(2026, 11, 3), self.session, self.manager_a)

        self.assertEqual(result["branch_id"], self.branch_a.id)
        opening = next(
            row for row in result["schedule"]
            if row["station_id"] == self.station_a.id and row["shift"] == "Opening"
        )
        self.assertEqual(opening["needed"], 1)
        self.assertEqual(
            opening["assigned"],
            [{"id": crew_a.id, "name": "Ana Santos", "crew_type": "Crew Trainer"}],
        )

    def test_schedule_generation_uses_standard_shift_with_configured_hours(self):
        crew = User(
            email="custom-shift-crew@example.com",
            password_hash="hash",
            full_name="Custom Shift Crew",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew.id,
                day_of_week="Tuesday",
                start_time=time(9, 0),
                end_time=time(17, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(9, 0),
                end_time=time(17, 0),
                required_count=1,
            )
        )
        self.session.commit()

        result = generate_full_day(date(2026, 11, 3), self.session, self.manager_a)

        self.assertEqual(len(result["schedule"]), 1)
        self.assertEqual(result["schedule"][0]["shift"], "Opening")
        self.assertEqual(result["schedule"][0]["time"], "09:00 - 17:00")
        self.assertEqual(result["schedule"][0]["needed"], 1)
        self.assertEqual(result["schedule"][0]["assigned"][0]["id"], crew.id)

    def test_schedule_generation_uses_new_crew_and_latest_station_skills(self):
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                required_count=1,
            )
        )
        self.session.commit()
        payload = CrewCreate(
            full_name="New Crew",
            email="new-crew@example.com",
            employee_number="000222",
            employment_type="Full-time",
            crew_type="Service crew",
        )
        with patch("app.routers.crew.hash_password", return_value="hashed"):
            crew = create_crew(payload, self.session, self.manager_a)
        self.session.add(
            Availability(
                user_id=crew["id"],
                day_of_week="Tuesday",
                start_time=time(8, 0),
                end_time=time(22, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.commit()

        before_skill_update = generate_full_day(
            date(2026, 11, 3), self.session, self.manager_a
        )
        opening = next(
            row for row in before_skill_update["schedule"]
            if row["station_id"] == self.station_a.id and row["shift"] == "Opening"
        )
        self.assertEqual(opening["assigned"], [])
        self.assertEqual(opening["qualified_crew"], [])

        update_qualified_stations(
            crew["id"],
            CrewQualifiedStationsUpdate(station_ids=[self.station_a.id]),
            self.session,
            self.manager_a,
        )
        after_skill_update = generate_full_day(
            date(2026, 11, 3), self.session, self.manager_a
        )
        opening = next(
            row for row in after_skill_update["schedule"]
            if row["station_id"] == self.station_a.id and row["shift"] == "Opening"
        )
        self.assertEqual(opening["assigned"][0]["id"], crew["id"])
        self.assertEqual(
            opening["qualified_crew"],
            [{"id": crew["id"], "name": "New Crew", "crew_type": "Service crew"}],
        )

    def test_draft_validation_rejects_assignments_from_another_branch(self):
        result = validate_schedule_draft(
            PublishRequest(
                schedule_date=date(2026, 11, 3),
                assignments=[
                    {
                        "user_id": self.crew_b.id,
                        "station_id": self.station_b.id,
                        "shift_name": "Opening",
                    }
                ],
            ),
            self.session,
            self.manager_a,
        )

        self.assertFalse(result["valid"])
        self.assertTrue(any(
            "active crew and stations from your branch" in error["message"]
            for error in result["errors"]
        ))

    def test_publishing_standard_shift_saves_configured_time_snapshot(self):
        crew = User(
            email="publish-custom-crew@example.com",
            password_hash="hash",
            full_name="Custom Shift Crew",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew.id,
                day_of_week="Tuesday",
                start_time=time(6, 30),
                end_time=time(11, 45),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(6, 30),
                end_time=time(11, 45),
                required_count=1,
            )
        )
        self.session.commit()

        draft = PublishRequest(
            schedule_date=date(2026, 11, 3),
            assignments=[
                {
                    "user_id": crew.id,
                    "station_id": self.station_a.id,
                    "shift_name": "Opening",
                }
            ],
        )
        validation = validate_schedule_draft(draft, self.session, self.manager_a)
        self.assertTrue(validation["valid"])
        self.assertEqual(validation["errors"], [])
        self.assertEqual(self.session.query(ShiftAssignment).count(), 0)

        incomplete_validation = validate_schedule_draft(
            PublishRequest(schedule_date=date(2026, 11, 3), assignments=[]),
            self.session,
            self.manager_a,
        )
        self.assertFalse(incomplete_validation["valid"])
        self.assertTrue(
            any("staffing shortage" in error["message"] for error in incomplete_validation["errors"])
        )

        result = publish_schedule(
            draft,
            self.session,
            self.manager_a,
        )

        assignment = self.session.query(ShiftAssignment).one()
        self.assertIn("successfully", result["message"])
        self.assertEqual(assignment.shift_name, "Opening")
        self.assertEqual(assignment.start_time, time(6, 30))
        self.assertEqual(assignment.end_time, time(11, 45))

    def test_saved_draft_is_hidden_until_publish_and_tracks_crew_acknowledgment(self):
        crew = User(
            email="schedule-ack-crew@example.com",
            password_hash="hash",
            full_name="Schedule Ack Crew",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew.id,
                day_of_week="Tuesday",
                start_time=time(8, 0),
                end_time=time(16, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                required_count=1,
            )
        )
        self.session.commit()
        payload = PublishRequest(
            schedule_date=date(2026, 11, 3),
            assignments=[
                {
                    "user_id": crew.id,
                    "station_id": self.station_a.id,
                    "shift_name": "Opening",
                }
            ],
        )

        saved = save_schedule_draft(payload, self.session, self.manager_a)

        self.assertIn("not visible to crew", saved["message"])
        self.assertEqual(
            self.session.query(ShiftAssignment).one().status,
            "Draft",
        )
        self.assertEqual(get_my_schedule(self.session, crew), [])
        self.assertEqual(
            get_manager_schedule_tracking(self.session, self.manager_a)[0]["status"],
            "Draft",
        )
        loaded_draft = get_schedule_draft(
            date(2026, 11, 3),
            self.session,
            self.manager_a,
        )
        self.assertEqual(loaded_draft["schedule"][0]["assigned"][0]["id"], crew.id)

        publish_schedule(payload, self.session, self.manager_a)
        published_schedule = get_my_schedule(self.session, crew)
        self.assertEqual(len(published_schedule), 1)
        self.assertFalse(published_schedule[0]["acknowledged"])
        self.assertEqual(
            self.session.query(ShiftAssignment).one().status,
            "Published",
        )

        acknowledgment = acknowledge_my_schedule(
            date(2026, 11, 3),
            self.session,
            crew,
        )

        self.assertTrue(acknowledgment["acknowledged"])
        self.assertTrue(get_my_schedule(self.session, crew)[0]["acknowledged"])
        tracking = get_manager_schedule_tracking(self.session, self.manager_a)
        self.assertEqual(tracking[0]["acknowledged_count"], 1)
        self.assertTrue(tracking[0]["crew"][0]["acknowledged"])

    def test_draft_save_cannot_replace_published_schedule(self):
        crew = User(
            email="published-schedule-crew@example.com",
            password_hash="hash",
            full_name="Published Schedule Crew",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew.id,
                day_of_week="Tuesday",
                start_time=time(8, 0),
                end_time=time(16, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                required_count=1,
            )
        )
        self.session.commit()
        payload = PublishRequest(
            schedule_date=date(2026, 11, 3),
            assignments=[
                {
                    "user_id": crew.id,
                    "station_id": self.station_a.id,
                    "shift_name": "Opening",
                }
            ],
        )
        publish_schedule(payload, self.session, self.manager_a)

        with self.assertRaises(HTTPException) as raised:
            save_schedule_draft(payload, self.session, self.manager_a)

        self.assertEqual(raised.exception.status_code, 409)
        assignment = self.session.query(ShiftAssignment).one()
        self.assertEqual(assignment.status, "Published")

    def test_draft_assignments_do_not_block_published_schedule_generation(self):
        crew = User(
            email="draft-rest-crew@example.com",
            password_hash="hash",
            full_name="Draft Rest Crew",
            qualified_stations=str(self.station_a.id),
            role=UserRole.EMPLOYEE,
            branch_id=self.branch_a.id,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        self.session.add(
            Availability(
                user_id=crew.id,
                day_of_week="Tuesday",
                start_time=time(8, 0),
                end_time=time(16, 0),
                valid_from=date(2026, 11, 3),
                valid_to=date(2026, 11, 3),
            )
        )
        self.session.add(
            StaffingRequirement(
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                shift_type="Opening",
                start_time=time(8, 0),
                end_time=time(16, 0),
                required_count=1,
            )
        )
        self.session.add(
            ShiftAssignment(
                user_id=crew.id,
                branch_id=self.branch_a.id,
                station_id=self.station_a.id,
                schedule_date=date(2026, 11, 2),
                shift_name="Closing",
                start_time=time(14, 0),
                end_time=time(22, 0),
                status="Draft",
            )
        )
        self.session.commit()

        generated = generate_full_day(
            date(2026, 11, 3),
            self.session,
            self.manager_a,
        )

        self.assertEqual(generated["schedule"][0]["assigned"][0]["id"], crew.id)
        validation = validate_schedule_draft(
            PublishRequest(
                schedule_date=date(2026, 11, 3),
                assignments=[
                    {
                        "user_id": crew.id,
                        "station_id": self.station_a.id,
                        "shift_name": "Opening",
                    }
                ],
            ),
            self.session,
            self.manager_a,
        )
        self.assertTrue(validation["valid"])

    def test_head_can_list_all_branches_and_manager_accounts(self):
        branches = list_branches(self.session, self.head)
        managers = list_managers(self.session, self.head)

        self.assertEqual({branch.id for branch in branches}, {self.branch_a.id, self.branch_b.id})
        self.assertEqual({manager.id for manager in managers}, {self.manager_a.id, self.manager_b.id})

    def test_head_can_create_branch_with_validated_operating_hours(self):
        payload = BranchCreate(
            name="  West Branch  ",
            opening_time=time(9, 0),
            closing_time=time(21, 0),
            prep_time_minutes=20,
            closing_time_minutes=25,
        )

        branch = create_branch(payload, self.session, self.head)

        self.assertEqual(branch.name, "West Branch")
        self.assertEqual(branch.opening_time, time(9, 0))
        self.assertEqual(branch.closing_time, time(21, 0))
        self.assertEqual(branch.prep_time_minutes, 20)
        self.assertEqual(branch.closing_time_minutes, 25)

    def test_head_cannot_create_duplicate_branch_name(self):
        payload = BranchCreate(
            name="north branch",
            opening_time=time(9, 0),
            closing_time=time(21, 0),
        )

        with self.assertRaises(HTTPException) as raised:
            create_branch(payload, self.session, self.head)

        self.assertEqual(raised.exception.status_code, 409)

    def test_manager_cannot_create_branch(self):
        payload = BranchCreate(
            name="Unauthorized Branch",
            opening_time=time(9, 0),
            closing_time=time(21, 0),
        )

        with self.assertRaises(HTTPException) as raised:
            create_branch(payload, self.session, self.manager_a)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertIsNone(
            self.session.query(Branch).filter(
                Branch.name == "Unauthorized Branch",
            ).first()
        )

    def test_branch_creation_rejects_bad_operating_hours_and_extra_fields(self):
        with self.assertRaises(ValidationError):
            BranchCreate(
                name="Invalid Branch",
                opening_time=time(22, 0),
                closing_time=time(10, 0),
            )
        with self.assertRaises(ValidationError):
            BranchCreate(
                name="Invalid Branch",
                opening_time=time(9, 0),
                closing_time=time(21, 0),
                branch_id=self.branch_a.id,
            )

    def test_head_can_create_manager_assigned_to_existing_branch(self):
        payload = HeadManagerCreate(
            full_name="  New Manager  ",
            email="New.Manager@example.com",
            manager_id="00127",
            password="secure-pass-123",
            branch_id=self.branch_a.id,
        )

        with patch("app.routers.head.hash_password", return_value="hashed-password"):
            manager = create_manager(payload, self.session, self.head)

        self.assertEqual(manager.full_name, "New Manager")
        self.assertEqual(manager.email, "new.manager@example.com")
        self.assertEqual(manager.manager_id, "00127")
        self.assertEqual(manager.role, UserRole.MANAGER)
        self.assertEqual(manager.branch_id, self.branch_a.id)
        self.assertEqual(manager.password_hash, "hashed-password")
        self.assertTrue(manager.is_active)

    def test_head_cannot_create_manager_for_nonexistent_branch(self):
        payload = HeadManagerCreate(
            full_name="New Manager",
            email="new.manager@example.com",
            manager_id="00128",
            password="secure-pass-123",
            branch_id=999,
        )

        with patch("app.routers.head.hash_password", return_value="hashed-password"):
            with self.assertRaises(HTTPException) as raised:
                create_manager(payload, self.session, self.head)

        self.assertEqual(raised.exception.status_code, 404)
        self.assertIsNone(
            self.session.query(User)
            .filter(User.email == "new.manager@example.com")
            .first()
        )

    def test_head_cannot_create_duplicate_email(self):
        payload = HeadManagerCreate(
            full_name="Duplicate",
            email=self.manager_a.email,
            manager_id="00129",
            password="secure-pass-123",
            branch_id=self.branch_b.id,
        )

        with self.assertRaises(HTTPException) as raised:
            create_manager(payload, self.session, self.head)

        self.assertEqual(raised.exception.status_code, 409)

    def test_manager_cannot_create_manager(self):
        payload = HeadManagerCreate(
            full_name="Unauthorized",
            email="unauthorized@example.com",
            manager_id="00130",
            password="secure-pass-123",
            branch_id=self.branch_a.id,
        )

        with patch("app.routers.head.hash_password", return_value="hashed-password"):
            with self.assertRaises(HTTPException) as raised:
                create_manager(payload, self.session, self.manager_a)

        self.assertEqual(raised.exception.status_code, 403)

    def test_head_cannot_create_duplicate_manager_id(self):
        self.manager_a.manager_id = "00042"
        self.session.commit()
        payload = HeadManagerCreate(
            full_name="Another Manager",
            email="another.manager@example.com",
            manager_id="00042",
            password="secure-pass-123",
            branch_id=self.branch_b.id,
        )

        with self.assertRaises(HTTPException) as raised:
            create_manager(payload, self.session, self.head)

        self.assertEqual(raised.exception.status_code, 409)

    def test_manager_id_must_be_digits_and_preserves_leading_zero(self):
        payload = HeadManagerCreate(
            full_name="New Manager",
            email="new.manager@example.com",
            manager_id="00007",
            password="secure-pass-123",
            branch_id=self.branch_a.id,
        )
        self.assertEqual(payload.manager_id, "00007")

        with self.assertRaises(ValidationError):
            HeadManagerCreate(
                full_name="Invalid ID",
                email="invalid@example.com",
                manager_id="ID-123",
                password="secure-pass-123",
                branch_id=self.branch_a.id,
            )

    def test_head_reassigns_manager_without_moving_branch_data(self):
        self.session.add(
            Schedule(
                manager_id=self.manager_a.id,
                branch_name=self.branch_a.name,
                status="Published",
            )
        )
        self.session.commit()
        previous_branch_id = self.manager_a.branch_id
        crew_branch_id = self.crew_b.branch_id
        station_branch_id = self.station_a.branch_id

        updated = assign_manager_branch(
            self.manager_a.id,
            ManagerBranchAssignment(branch_id=self.branch_b.id),
            self.session,
            self.head,
        )

        self.assertEqual(updated.branch_id, self.branch_b.id)
        self.assertNotEqual(updated.branch_id, previous_branch_id)
        self.assertEqual(self.crew_b.branch_id, crew_branch_id)
        self.assertEqual(self.station_a.branch_id, station_branch_id)
        self.assertEqual(get_all_schedules(self.session, self.manager_a), [])

    def test_head_updates_manager_settings_and_hashes_new_password(self):
        payload = HeadManagerUpdate(
            full_name=" Updated Manager ",
            email="UPDATED@example.com",
            manager_id="00043",
            branch_id=self.branch_b.id,
            password="new-password",
        )

        with patch("app.routers.head.hash_password", return_value="new-hash") as hash_mock:
            updated = update_manager(self.manager_a.id, payload, self.session, self.head)

        hash_mock.assert_called_once_with("new-password")
        self.assertEqual(updated.full_name, "Updated Manager")
        self.assertEqual(updated.email, "updated@example.com")
        self.assertEqual(updated.manager_id, "00043")
        self.assertEqual(updated.branch_id, self.branch_b.id)
        self.assertEqual(updated.password_hash, "new-hash")

    def test_head_updates_manager_without_changing_password_when_omitted(self):
        self.manager_a.password_hash = "existing-hash"
        self.session.commit()
        payload = HeadManagerUpdate(full_name="Corrected Name")

        updated = update_manager(self.manager_a.id, payload, self.session, self.head)

        self.assertEqual(updated.full_name, "Corrected Name")
        self.assertEqual(updated.password_hash, "existing-hash")

    def test_manager_settings_branch_change_does_not_move_branch_data(self):
        schedule = Schedule(
            manager_id=self.manager_a.id,
            branch_name=self.branch_a.name,
            status="Published",
        )
        self.session.add(schedule)
        self.session.commit()
        crew_branch_id = self.crew_b.branch_id
        station_branch_id = self.station_a.branch_id

        updated = update_manager(
            self.manager_a.id,
            HeadManagerUpdate(branch_id=self.branch_b.id),
            self.session,
            self.head,
        )

        self.assertEqual(updated.branch_id, self.branch_b.id)
        self.assertEqual(self.crew_b.branch_id, crew_branch_id)
        self.assertEqual(self.station_a.branch_id, station_branch_id)
        self.assertEqual(self.session.query(Schedule).count(), 1)
        self.assertEqual(get_all_schedules(self.session, self.manager_a), [])

    def test_head_cannot_update_manager_with_duplicate_email_or_manager_id(self):
        self.manager_b.manager_id = "00044"
        self.session.commit()

        duplicate_email = HeadManagerUpdate(email=self.manager_b.email)
        with self.assertRaises(HTTPException) as raised_email:
            update_manager(self.manager_a.id, duplicate_email, self.session, self.head)
        self.assertEqual(raised_email.exception.status_code, 409)

        duplicate_manager_id = HeadManagerUpdate(manager_id="00044")
        with self.assertRaises(HTTPException) as raised_manager_id:
            update_manager(self.manager_a.id, duplicate_manager_id, self.session, self.head)
        self.assertEqual(raised_manager_id.exception.status_code, 409)

    def test_head_cannot_update_manager_to_nonexistent_branch(self):
        payload = HeadManagerUpdate(branch_id=999)

        with self.assertRaises(HTTPException) as raised:
            update_manager(self.manager_a.id, payload, self.session, self.head)

        self.assertEqual(raised.exception.status_code, 404)

    def test_manager_cannot_update_manager_settings(self):
        payload = HeadManagerUpdate(full_name="Unauthorized")

        with self.assertRaises(HTTPException) as raised:
            update_manager(self.manager_a.id, payload, self.session, self.manager_a)

        self.assertEqual(raised.exception.status_code, 403)

    def test_manager_update_rejects_empty_payload_null_and_invalid_password(self):
        for values in ({}, {"full_name": None}, {"password": "short"}):
            with self.subTest(values=values), self.assertRaises(ValidationError):
                HeadManagerUpdate(**values)

    def test_manager_cannot_use_head_branch_assignment_endpoints(self):
        with self.assertRaises(HTTPException) as raised:
            list_branches(self.session, self.manager_a)
        self.assertEqual(raised.exception.status_code, 403)

    def test_head_cannot_assign_inactive_manager(self):
        inactive_manager = self._manager("inactive-manager@example.com", self.branch_a.id)
        inactive_manager.is_active = False
        self.session.commit()

        with self.assertRaises(HTTPException) as raised:
            assign_manager_branch(
                inactive_manager.id,
                ManagerBranchAssignment(branch_id=self.branch_b.id),
                self.session,
                self.head,
            )
        self.assertEqual(raised.exception.status_code, 404)

        with self.assertRaises(HTTPException) as raised:
            assign_manager_branch(
                self.manager_a.id,
                ManagerBranchAssignment(branch_id=self.branch_b.id),
                self.session,
                self.manager_a,
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_unassigned_manager_cannot_read_all_branches(self):
        manager = self._manager("unassigned@example.com", None)
        with self.assertRaises(HTTPException) as raised:
            get_my_branch(self.session, manager)
        self.assertEqual(raised.exception.status_code, 409)

    def test_station_list_and_create_are_limited_to_manager_branch(self):
        stations = get_all_stations(self.session, self.manager_a)
        self.assertEqual([station["branch_id"] for station in stations], [self.branch_a.id])

        created = create_station(
            StationCreate(name="Grill"),
            self.session,
            self.manager_a,
        )
        self.assertEqual(created["branch_id"], self.branch_a.id)

    def test_manager_cannot_edit_or_remove_another_branch_station(self):
        with self.assertRaises(HTTPException) as edit_error:
            update_station(
                self.station_b.id,
                StationUpdate(name="Changed"),
                self.session,
                self.manager_a,
            )
        self.assertEqual(edit_error.exception.status_code, 404)

        with self.assertRaises(HTTPException) as delete_error:
            delete_station(self.station_b.id, self.session, self.manager_a)
        self.assertEqual(delete_error.exception.status_code, 404)
        self.assertIsNotNone(self.session.get(Station, self.station_b.id))

    def test_crew_list_and_delete_are_limited_to_manager_branch(self):
        crew = get_all_crew(self.session, self.manager_a)
        self.assertEqual(crew, [])

        with self.assertRaises(HTTPException) as raised:
            delete_crew(self.crew_b.id, self.session, self.manager_a)
        self.assertEqual(raised.exception.status_code, 404)
        self.assertIsNotNone(self.session.get(User, self.crew_b.id))

    def test_crew_creation_uses_manager_branch_not_request_branch(self):
        payload = CrewCreate(
            full_name="Crew A",
            email="crew-a@example.com",
            employee_number="000123",
            employment_type="Full-time",
            crew_type="Service crew",
            qualified_stations=str(self.station_a.id),
        )

        with patch("app.routers.crew.hash_password", return_value="hashed"):
            result = create_crew(payload, self.session, self.manager_a)

        self.assertEqual(result["branch_id"], self.branch_a.id)
        created = self.session.query(User).filter(User.email == payload.email).one()
        self.assertEqual(created.branch_id, self.branch_a.id)
        self.assertEqual(created.employee_number, "000123")

    def test_crew_creation_rejects_duplicate_employee_id_case_insensitive_email_and_bad_hours(self):
        self.crew_b.employee_number = "000123"
        self.session.commit()
        duplicate_id = CrewCreate(
            full_name="Crew Duplicate",
            email="another@example.com",
            employee_number="000123",
            employment_type="Full-time",
            crew_type="Service crew",
        )
        with self.assertRaises(HTTPException) as duplicate_error:
            create_crew(duplicate_id, self.session, self.manager_a)
        self.assertEqual(duplicate_error.exception.status_code, 409)

        with self.assertRaises(ValidationError):
            CrewCreate(
                full_name="Crew A",
                email="crew-a@example.com",
                employee_number="000124",
                employment_type="Full-time",
                crew_type="Service crew",
                min_hours=41,
                max_hours=40,
            )
        with self.assertRaises(ValidationError):
            CrewCreate(
                full_name="Crew A",
                email="crew-a@example.com",
                employee_number="EMP-124",
                employment_type="Full-time",
                crew_type="Service crew",
            )

    def test_crew_creation_normalizes_employee_id_and_email(self):
        payload = CrewCreate(
            full_name=" Crew A ",
            email="Crew-A@Example.com",
            employee_number=" 000126 ",
            employment_type="Full-time",
            crew_type="Service crew",
        )
        with patch("app.routers.crew.hash_password", return_value="hashed"):
            result = create_crew(payload, self.session, self.manager_a)

        self.assertEqual(result["full_name"], "Crew A")
        self.assertEqual(result["email"], "crew-a@example.com")
        self.assertEqual(result["employee_number"], "000126")

    def test_manager_can_assign_employee_number_to_existing_branch_crew(self):
        updated = assign_employee_number(
            self.crew_b.id,
            CrewEmployeeNumberUpdate(employee_number=" 000987 "),
            self.session,
            self.manager_b,
        )
        self.assertEqual(updated.employee_number, "000987")

    def test_manager_cannot_assign_duplicate_employee_number_or_other_branch_crew(self):
        self.manager_b.employee_number = "000987"
        self.session.commit()
        with self.assertRaises(HTTPException) as duplicate:
            assign_employee_number(
                self.crew_b.id,
                CrewEmployeeNumberUpdate(employee_number="000987"),
                self.session,
                self.manager_b,
            )
        self.assertEqual(duplicate.exception.status_code, 409)

        with self.assertRaises(HTTPException) as other_branch:
            assign_employee_number(
                self.crew_b.id,
                CrewEmployeeNumberUpdate(employee_number="000988"),
                self.session,
                self.manager_a,
            )
        self.assertEqual(other_branch.exception.status_code, 404)

    def test_only_manager_can_assign_employee_number(self):
        with self.assertRaises(HTTPException) as raised:
            assign_employee_number(
                self.crew_b.id,
                CrewEmployeeNumberUpdate(employee_number="000988"),
                self.session,
                self.crew_b,
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_manager_can_update_and_clear_crew_qualified_stations(self):
        updated = update_qualified_stations(
            self.crew_b.id,
            CrewQualifiedStationsUpdate(station_ids=[self.station_b.id]),
            self.session,
            self.manager_b,
        )
        self.assertEqual(updated.qualified_stations, str(self.station_b.id))

        cleared = update_qualified_stations(
            self.crew_b.id,
            CrewQualifiedStationsUpdate(station_ids=[]),
            self.session,
            self.manager_b,
        )
        self.assertIsNone(cleared.qualified_stations)

    def test_manager_cannot_assign_crew_a_station_or_member_from_another_branch(self):
        with self.assertRaises(HTTPException) as station_error:
            update_qualified_stations(
                self.crew_b.id,
                CrewQualifiedStationsUpdate(station_ids=[self.station_a.id]),
                self.session,
                self.manager_b,
            )
        self.assertEqual(station_error.exception.status_code, 422)

        with self.assertRaises(HTTPException) as crew_error:
            update_qualified_stations(
                self.crew_b.id,
                CrewQualifiedStationsUpdate(station_ids=[self.station_a.id]),
                self.session,
                self.manager_a,
            )
        self.assertEqual(crew_error.exception.status_code, 404)

    def test_only_manager_can_update_crew_qualified_stations(self):
        with self.assertRaises(HTTPException) as raised:
            update_qualified_stations(
                self.crew_b.id,
                CrewQualifiedStationsUpdate(station_ids=[self.station_b.id]),
                self.session,
                self.crew_b,
            )
        self.assertEqual(raised.exception.status_code, 403)

    def test_crew_cannot_be_qualified_for_another_branch_station(self):
        payload = CrewCreate(
            full_name="Crew A",
            email="crew-a@example.com",
            employee_number="000124",
            employment_type="Full-time",
            crew_type="Service crew",
            qualified_stations=str(self.station_b.id),
        )

        with self.assertRaises(HTTPException) as raised:
            with patch("app.routers.crew.hash_password", return_value="hashed"):
                create_crew(payload, self.session, self.manager_a)

        self.assertEqual(raised.exception.status_code, 422)
        self.assertIsNone(
            self.session.query(User).filter(User.email == payload.email).first()
        )

    def test_operational_payloads_reject_client_selected_branch_ids(self):
        crew_data = {
            "full_name": "Crew A",
            "email": "crew-a@example.com",
            "employee_number": "000125",
            "employment_type": "Full-time",
            "crew_type": "Service crew",
            "branch_id": self.branch_b.id,
        }
        with self.assertRaises(ValidationError):
            CrewCreate(**crew_data)

        with self.assertRaises(ValidationError):
            PublishRequest(
                branch_id=self.branch_b.id,
                schedule_date=date(2026, 11, 3),
                assignments=[],
            )

        self.assertNotIn("branch_id", signature(generate_full_day).parameters)


if __name__ == "__main__":
    unittest.main()
