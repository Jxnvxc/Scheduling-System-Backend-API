import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.user import User, UserRole
from app.routers.user import login_user
from app.schemas.user import UserLogin


class LoginIdentifierTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()
        self.crew = User(
            email="crew@example.com",
            employee_number="000123",
            password_hash="crew-hash",
            full_name="Crew Member",
            role=UserRole.EMPLOYEE,
            is_active=True,
        )
        self.manager = User(
            email="manager@example.com",
            manager_id="000456",
            password_hash="manager-hash",
            full_name="Branch Manager",
            role=UserRole.MANAGER,
            is_active=True,
        )
        self.head = User(
            email="head@example.com",
            password_hash="head-hash",
            full_name="Head Account",
            role=UserRole.HEAD,
            is_active=True,
        )
        self.session.add_all([self.crew, self.manager, self.head])
        self.session.commit()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_crew_login_requires_matching_employee_number_and_password(self):
        payload = UserLogin(
            email="crew@example.com",
            password="crew-password",
            account_type="employee",
            employee_number="000123",
        )
        with (
            patch("app.routers.user.verify_password", return_value=True),
            patch("app.routers.user.create_access_token", return_value="token"),
        ):
            result = login_user(payload, self.session)

        self.assertEqual(result["user"]["role"], "employee")

    def test_manager_login_requires_matching_manager_id(self):
        payload = UserLogin(
            email="manager@example.com",
            password="manager-password",
            account_type="manager",
            manager_id="000456",
        )
        with (
            patch("app.routers.user.verify_password", return_value=True),
            patch("app.routers.user.create_access_token", return_value="token"),
        ):
            result = login_user(payload, self.session)

        self.assertEqual(result["user"]["role"], "manager")

    def test_head_login_remains_available_without_staff_id(self):
        payload = UserLogin(
            email="head@example.com",
            password="head-password",
            account_type="head",
        )
        with (
            patch("app.routers.user.verify_password", return_value=True),
            patch("app.routers.user.create_access_token", return_value="token"),
        ):
            result = login_user(payload, self.session)

        self.assertEqual(result["user"]["role"], "head")

    def test_wrong_role_or_identifier_is_rejected(self):
        payload = UserLogin(
            email="crew@example.com",
            password="crew-password",
            account_type="manager",
            manager_id="000123",
        )
        with self.assertRaises(HTTPException) as raised:
            login_user(payload, self.session)

        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(raised.exception.detail, "Invalid login details")

    def test_login_schema_requires_role_specific_identifier(self):
        invalid_payloads = (
            {
                "email": "crew@example.com",
                "password": "password",
                "account_type": "employee",
            },
            {
                "email": "manager@example.com",
                "password": "password",
                "account_type": "manager",
                "manager_id": "not-numeric",
            },
            {
                "email": "head@example.com",
                "password": "password",
                "account_type": "head",
                "employee_number": "000123",
            },
        )
        for payload in invalid_payloads:
            with self.subTest(payload=payload), self.assertRaises(ValidationError):
                UserLogin(**payload)


if __name__ == "__main__":
    unittest.main()
