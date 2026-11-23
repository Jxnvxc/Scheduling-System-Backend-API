import unittest
from unittest.mock import Mock, patch

from app.database import Base
from app.models.user import UserRole
from create_manager import (
    assign_existing_crew,
    assign_existing_manager,
    create_head_account,
    create_manager,
)


class CreateManagerTests(unittest.TestCase):
    def setUp(self):
        self.db = Mock()
        self.query = self.db.query.return_value
        self.branch = Mock(id=7)
        self.query.filter.return_value.first.side_effect = [None, self.branch]

    def test_registers_branch_table_referenced_by_user_model(self):
        branch_id_foreign_key = next(
            iter(Base.metadata.tables["users"].c.branch_id.foreign_keys)
        )

        self.assertIn("branches", Base.metadata.tables)
        self.assertEqual(branch_id_foreign_key.column.table.name, "branches")

    @patch("create_manager.hash_password", return_value="hashed-password")
    def test_creates_first_manager_with_hashed_password(self, hash_password):
        manager = create_manager(
            self.db,
            "manager@example.com",
            "Branch Manager",
            "strong-password",
            7,
        )

        self.assertEqual(manager.role, UserRole.MANAGER)
        self.assertEqual(manager.email, "manager@example.com")
        self.assertEqual(manager.password_hash, "hashed-password")
        self.assertTrue(manager.is_active)
        self.assertEqual(manager.branch_id, 7)
        hash_password.assert_called_once_with("strong-password")
        self.db.add.assert_called_once_with(manager)
        self.db.commit.assert_called_once()

    def test_allows_multiple_managers_when_assigned_to_a_branch(self):
        manager = create_manager(
            self.db,
            "second@example.com",
            "Second Manager",
            "strong-password",
            7,
        )

        self.assertEqual(manager.branch_id, 7)
        self.db.commit.assert_called_once()

    @patch("create_manager.hash_password", return_value="hashed-password")
    def test_creates_head_account_without_branch_assignment(self, hash_password):
        self.query.filter.return_value.first.side_effect = [None]

        head = create_head_account(
            self.db,
            "head@example.com",
            "Head Account",
            "strong-password",
        )

        self.assertEqual(head.role, UserRole.HEAD)
        self.assertIsNone(head.branch_id)
        self.assertEqual(head.password_hash, "hashed-password")
        hash_password.assert_called_once_with("strong-password")
        self.db.commit.assert_called_once()

    def test_refuses_to_reuse_an_existing_email(self):
        self.query.filter.return_value.first.side_effect = [object()]

        with self.assertRaisesRegex(ValueError, "account with that email"):
            create_manager(
                self.db,
                "crew@example.com",
                "Crew Member",
                "strong-password",
                7,
            )

        self.db.add.assert_not_called()
        self.db.commit.assert_not_called()

    def test_assigns_existing_unassigned_manager_to_branch(self):
        manager = Mock(role=UserRole.MANAGER, branch_id=None, email="old@example.com")
        self.query.filter.return_value.first.side_effect = [manager, self.branch]

        result = assign_existing_manager(self.db, "OLD@example.com", 7)

        self.assertIs(result, manager)
        self.assertEqual(manager.branch_id, 7)
        self.db.commit.assert_called_once()

    def test_assigns_existing_unassigned_crew_to_branch(self):
        crew = Mock(role=UserRole.EMPLOYEE, branch_id=None, email="crew@example.com")
        self.query.filter.return_value.first.side_effect = [crew, self.branch]

        result = assign_existing_crew(self.db, "CREW@example.com", 7)

        self.assertIs(result, crew)
        self.assertEqual(crew.branch_id, 7)
        self.db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
