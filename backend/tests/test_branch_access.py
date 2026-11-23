import unittest
from types import SimpleNamespace

from fastapi import HTTPException

from app.auth.branch_access import require_manager_branch_id
from app.models.user import UserRole


class ManagerBranchAccessTests(unittest.TestCase):
    def test_returns_assigned_branch_id_for_manager(self):
        manager = SimpleNamespace(role=UserRole.MANAGER, branch_id=12)

        self.assertEqual(require_manager_branch_id(manager), 12)

    def test_rejects_non_manager(self):
        employee = SimpleNamespace(role=UserRole.EMPLOYEE, branch_id=12)

        with self.assertRaises(HTTPException) as raised:
            require_manager_branch_id(employee)

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Not authorized")

    def test_rejects_manager_without_branch(self):
        manager = SimpleNamespace(role=UserRole.MANAGER, branch_id=None)

        with self.assertRaises(HTTPException) as raised:
            require_manager_branch_id(manager)

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(
            raised.exception.detail,
            "Manager account is not assigned to a branch.",
        )

    def test_preserves_endpoint_specific_error_messages(self):
        employee = SimpleNamespace(role=UserRole.EMPLOYEE, branch_id=None)

        with self.assertRaises(HTTPException) as raised:
            require_manager_branch_id(
                employee,
                manager_detail="Only managers can manage crew.",
                unassigned_detail="Your manager account is not assigned to a branch.",
            )

        self.assertEqual(raised.exception.status_code, 403)
        self.assertEqual(raised.exception.detail, "Only managers can manage crew.")


if __name__ == "__main__":
    unittest.main()
