import unittest

from pydantic import ValidationError

from app.schemas.user import ChangePassword, UserCreate


class UserSchemaTests(unittest.TestCase):
    def test_public_signup_accepts_employee_fields(self):
        user = UserCreate(
            email="crew@example.com",
            password="strongpass",
            full_name="Crew Member",
        )

        self.assertEqual(user.full_name, "Crew Member")

    def test_public_signup_rejects_role_override(self):
        with self.assertRaises(ValidationError):
            UserCreate(
                email="manager@example.com",
                password="strongpass",
                full_name="Manager",
                role="manager",
            )

    def test_signup_rejects_password_shorter_than_eight_characters(self):
        with self.assertRaises(ValidationError):
            UserCreate(
                email="crew@example.com",
                password="short",
                full_name="Crew Member",
            )

    def test_change_password_requires_eight_characters(self):
        with self.assertRaises(ValidationError):
            ChangePassword(old_password="oldpassword", new_password="short")


if __name__ == "__main__":
    unittest.main()
