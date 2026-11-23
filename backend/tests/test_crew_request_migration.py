import unittest

from sqlalchemy import create_engine, text

from app.database import migrate_crew_request_branch


class CrewRequestBranchMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(text(
                "CREATE TABLE branches (id INTEGER PRIMARY KEY)"
            ))
            connection.execute(text(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, branch_id INTEGER)"
            ))
            connection.execute(text(
                "CREATE TABLE crew_requests ("
                "id INTEGER PRIMARY KEY, requester_id INTEGER NOT NULL, "
                "status VARCHAR(24) NOT NULL)"
            ))
            connection.execute(text("INSERT INTO branches (id) VALUES (10), (20)"))
            connection.execute(text(
                "INSERT INTO users (id, branch_id) VALUES (1, 10), (2, 20)"
            ))
            connection.execute(text(
                "INSERT INTO crew_requests (id, requester_id, status) "
                "VALUES (100, 1, 'pending_manager'), (200, 2, 'approved')"
            ))

    def tearDown(self):
        self.engine.dispose()

    def test_migration_populates_branch_and_is_idempotent(self):
        migrate_crew_request_branch(self.engine)
        migrate_crew_request_branch(self.engine)

        with self.engine.connect() as connection:
            rows = connection.execute(
                text("SELECT id, branch_id FROM crew_requests ORDER BY id")
            ).all()
            indexes = connection.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type = 'index' "
                    "AND name = 'ix_crew_requests_branch_status'"
                )
            ).all()

        self.assertEqual(rows, [(100, 10), (200, 20)])
        self.assertEqual(len(indexes), 1)

    def test_migration_fails_explicitly_for_unassigned_requester(self):
        with self.engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO users (id, branch_id) VALUES (3, NULL)"
            ))
            connection.execute(text(
                "INSERT INTO crew_requests (id, requester_id, status) "
                "VALUES (300, 3, 'pending_manager')"
            ))

        with self.assertRaisesRegex(RuntimeError, "not assigned to a branch"):
            migrate_crew_request_branch(self.engine)


if __name__ == "__main__":
    unittest.main()
