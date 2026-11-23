import unittest
from datetime import date, time, timedelta

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.assignment import ShiftAssignment
from app.models.availability import Availability
from app.models.branch import Branch
from app.models.requirement import StaffingRequirement
from app.models.station import Station
from app.models.user import User, UserRole
from app.routers.crew_requests import (
    create_leave_request,
    create_swap_request,
    decide_request,
    get_pending_manager_requests,
    respond_to_swap,
)
from app.routers.schedule import PublishRequest, PublishItem, _validate_schedule_request
from app.routers.schedule import generate_full_day
from app.schemas.crew_request import (
    LeaveRequestCreate,
    ManagerDecision,
    SwapRequestCreate,
    SwapResponse,
)


class CrewRequestTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.today = date.today()
        self.branch = Branch(
            name="Requests branch",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.session.add(self.branch)
        self.session.flush()
        self.manager = User(
            email="manager@example.com",
            password_hash="hash",
            full_name="Branch Manager",
            role=UserRole.MANAGER,
            branch_id=self.branch.id,
        )
        self.crew_a = self._crew("crew-a@example.com", "Crew A")
        self.crew_b = self._crew("crew-b@example.com", "Crew B")
        self.station = Station(
            branch_id=self.branch.id,
            name="Cashier",
            opening_start_time=time(8, 0),
            opening_end_time=time(16, 0),
            mid_start_time=time(12, 0),
            mid_end_time=time(20, 0),
            closing_start_time=time(14, 0),
            closing_end_time=time(22, 0),
        )
        self.session.add_all([self.manager, self.station])
        self.session.flush()
        self.manager.branch_id = self.branch.id
        self.session.add(StaffingRequirement(
            branch_id=self.branch.id,
            station_id=self.station.id,
            shift_type="Opening",
            start_time=time(8, 0),
            end_time=time(16, 0),
            required_count=1,
        ))
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def _crew(self, email, name):
        crew = User(
            email=email,
            password_hash="hash",
            full_name=name,
            role=UserRole.EMPLOYEE,
            branch_id=self.branch.id,
            qualified_stations="1",
            max_hours=40,
            is_active=True,
        )
        self.session.add(crew)
        self.session.flush()
        return crew

    def _availability(self, employee, shift_date):
        day = shift_date.strftime("%A")
        exists = self.session.query(Availability).filter(
            Availability.user_id == employee.id,
            Availability.day_of_week == day,
        ).first()
        if exists is None:
            self.session.add(Availability(
                user_id=employee.id,
                day_of_week=day,
                start_time=time(0, 0),
                end_time=time(23, 59),
                valid_from=self.today,
                valid_to=shift_date + timedelta(days=14),
            ))

    def _assignment(self, employee, shift_date):
        self._availability(employee, shift_date)
        assignment = ShiftAssignment(
            user_id=employee.id,
            branch_id=self.branch.id,
            station_id=self.station.id,
            schedule_date=shift_date,
            shift_name="Opening",
            start_time=time(8, 0),
            end_time=time(16, 0),
            status="Published",
        )
        self.session.add(assignment)
        self.session.flush()
        return assignment

    def test_leave_request_can_be_approved_and_blocks_schedule_validation(self):
        leave_date = self.today + timedelta(days=3)
        request = create_leave_request(
            LeaveRequestCreate(start_date=leave_date, end_date=leave_date),
            self.session,
            self.crew_a,
        )
        self.assertEqual(request["status"], "pending_manager")

        pending = get_pending_manager_requests(self.session, self.manager)
        self.assertEqual([item["id"] for item in pending], [request["id"]])
        decided = decide_request(
            request["id"],
            ManagerDecision(decision="approve"),
            self.session,
            self.manager,
        )
        self.assertEqual(decided["status"], "approved")

        self._availability(self.crew_a, leave_date)
        self._availability(self.crew_b, leave_date)
        generated = generate_full_day(leave_date, self.session, self.manager)
        scheduled_ids = {
            employee["id"]
            for row in generated["schedule"]
            for employee in row["assigned"]
        }
        self.assertNotIn(self.crew_a.id, scheduled_ids)
        self.assertIn(self.crew_b.id, scheduled_ids)

        payload = PublishRequest(
            schedule_date=leave_date,
            assignments=[
                PublishItem(
                    user_id=self.crew_a.id,
                    station_id=self.station.id,
                    shift_name="Opening",
                )
            ],
        )
        _, _, errors = _validate_schedule_request(payload, self.session, self.manager)
        self.assertTrue(any("approved leave" in error for error in errors))

    def test_leave_request_rejects_overlapping_active_leave(self):
        leave_date = self.today + timedelta(days=5)
        create_leave_request(
            LeaveRequestCreate(start_date=leave_date, end_date=leave_date),
            self.session,
            self.crew_a,
        )
        with self.assertRaises(HTTPException) as context:
            create_leave_request(
                LeaveRequestCreate(start_date=leave_date, end_date=leave_date + timedelta(days=1)),
                self.session,
                self.crew_a,
            )
        self.assertEqual(context.exception.status_code, 409)

    def test_manager_inbox_warns_about_published_leave_conflicts(self):
        leave_date = self.today + timedelta(days=4)
        self._assignment(self.crew_a, leave_date)
        self.session.commit()
        request = create_leave_request(
            LeaveRequestCreate(start_date=leave_date, end_date=leave_date),
            self.session,
            self.crew_a,
        )

        pending = get_pending_manager_requests(self.session, self.manager)

        self.assertEqual(pending[0]["id"], request["id"])
        self.assertEqual(pending[0]["conflicting_assignments"], 1)

    def test_manager_inbox_is_limited_to_its_branch(self):
        leave_date = self.today + timedelta(days=4)
        create_leave_request(
            LeaveRequestCreate(start_date=leave_date, end_date=leave_date),
            self.session,
            self.crew_a,
        )
        other_branch = Branch(
            name="Other requests branch",
            opening_time=time(8, 0),
            closing_time=time(22, 0),
        )
        self.session.add(other_branch)
        self.session.flush()
        other_manager = User(
            email="other-manager@example.com",
            password_hash="hash",
            full_name="Other Manager",
            role=UserRole.MANAGER,
            branch_id=other_branch.id,
        )
        self.session.add(other_manager)
        self.session.commit()

        self.assertEqual(get_pending_manager_requests(self.session, other_manager), [])

    def test_swap_waits_for_recipient_then_manager_and_supports_cross_date(self):
        next_monday = self.today + timedelta(days=(7 - self.today.weekday()))
        first_date = next_monday + timedelta(days=1)
        second_date = next_monday + timedelta(days=8)
        for employee in (self.crew_a, self.crew_b):
            self._availability(employee, first_date)
            self._availability(employee, second_date)
        first = self._assignment(self.crew_a, first_date)
        second = self._assignment(self.crew_b, second_date)
        self.session.commit()

        request = create_swap_request(
            SwapRequestCreate(
                requester_assignment_id=first.id,
                target_assignment_id=second.id,
            ),
            self.session,
            self.crew_a,
        )
        self.assertEqual(request["status"], "pending_recipient")
        accepted = respond_to_swap(
            request["id"],
            SwapResponse(accept=True),
            self.session,
            self.crew_b,
        )
        self.assertEqual(accepted["status"], "pending_manager")

        approved = decide_request(
            request["id"],
            ManagerDecision(decision="approve"),
            self.session,
            self.manager,
        )
        self.assertEqual(approved["status"], "approved")
        self.session.refresh(first)
        self.session.refresh(second)
        self.assertEqual(first.user_id, self.crew_b.id)
        self.assertEqual(second.user_id, self.crew_a.id)

    def test_swap_cannot_be_approved_when_recipient_is_not_qualified(self):
        next_monday = self.today + timedelta(days=(7 - self.today.weekday()))
        first_date = next_monday + timedelta(days=1)
        second_date = next_monday + timedelta(days=3)
        for employee in (self.crew_a, self.crew_b):
            self._availability(employee, first_date)
            self._availability(employee, second_date)
        first = self._assignment(self.crew_a, first_date)
        second = self._assignment(self.crew_b, second_date)
        self.crew_b.qualified_stations = ""
        self.session.commit()
        request = create_swap_request(
            SwapRequestCreate(
                requester_assignment_id=first.id,
                target_assignment_id=second.id,
            ),
            self.session,
            self.crew_a,
        )
        respond_to_swap(
            request["id"],
            SwapResponse(accept=True),
            self.session,
            self.crew_b,
        )

        with self.assertRaises(HTTPException) as context:
            decide_request(
                request["id"],
                ManagerDecision(decision="approve"),
                self.session,
                self.manager,
            )
        self.assertEqual(context.exception.status_code, 409)
        self.session.refresh(first)
        self.assertEqual(first.user_id, self.crew_a.id)

    def test_only_the_requested_recipient_can_accept_swap(self):
        next_monday = self.today + timedelta(days=(7 - self.today.weekday()))
        first_date = next_monday + timedelta(days=1)
        second_date = next_monday + timedelta(days=3)
        for employee in (self.crew_a, self.crew_b):
            self._availability(employee, first_date)
            self._availability(employee, second_date)
        first = self._assignment(self.crew_a, first_date)
        second = self._assignment(self.crew_b, second_date)
        self.session.commit()
        request = create_swap_request(
            SwapRequestCreate(
                requester_assignment_id=first.id,
                target_assignment_id=second.id,
            ),
            self.session,
            self.crew_a,
        )

        with self.assertRaises(HTTPException) as context:
            respond_to_swap(
                request["id"],
                SwapResponse(accept=True),
                self.session,
                self.crew_a,
            )
        self.assertEqual(context.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
