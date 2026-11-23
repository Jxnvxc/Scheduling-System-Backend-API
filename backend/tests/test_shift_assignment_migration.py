import unittest

from sqlalchemy import create_engine, text

from app.database import migrate_shift_assignment_acknowledgment


class ShiftAssignmentAcknowledgmentMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE shift_assignments ("
                    "id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL)"
                )
            )

    def tearDown(self):
        self.engine.dispose()

    def test_migration_adds_acknowledgment_timestamp_and_is_idempotent(self):
        migrate_shift_assignment_acknowledgment(self.engine)
        migrate_shift_assignment_acknowledgment(self.engine)

        with self.engine.connect() as connection:
            columns = {
                column["name"]
                for column in connection.execute(
                    text("PRAGMA table_info('shift_assignments')")
                ).mappings()
            }

        self.assertIn("acknowledged_at", columns)


if __name__ == "__main__":
    unittest.main()
