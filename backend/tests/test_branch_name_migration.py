import unittest

from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.database import migrate_branch_name_ci_unique


class BranchNameMigrationTests(unittest.TestCase):
    def test_migration_adds_idempotent_case_insensitive_unique_index(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE branches ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO branches (id, name) VALUES (1, 'North Branch')")
                )

            migrate_branch_name_ci_unique(engine)
            migrate_branch_name_ci_unique(engine)

            with engine.begin() as connection:
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        text("INSERT INTO branches (id, name) VALUES (2, ' north branch ')")
                    )
        finally:
            engine.dispose()

    def test_migration_fails_explicitly_for_existing_duplicate_names(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE branches ("
                        "id INTEGER PRIMARY KEY, "
                        "name VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text(
                        "INSERT INTO branches (id, name) VALUES "
                        "(1, 'North Branch'), (2, ' north branch ')"
                    )
                )

            with self.assertRaisesRegex(RuntimeError, "duplicate branch names"):
                migrate_branch_name_ci_unique(engine)
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
