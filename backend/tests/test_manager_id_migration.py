import unittest

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.database import migrate_employee_number, migrate_manager_id


class ManagerIdMigrationTests(unittest.TestCase):
    def test_migration_adds_nullable_unique_manager_id_idempotently(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE users ("
                        "id INTEGER PRIMARY KEY, "
                        "email VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO users (id, email) VALUES (1, 'old@example.com')")
                )

            migrate_manager_id(engine)
            migrate_manager_id(engine)

            user_columns = {
                column["name"]: column
                for column in inspect(engine).get_columns("users")
            }
            indexes = inspect(engine).get_indexes("users")
            manager_id_index = next(
                index for index in indexes if index["name"] == "uq_users_manager_id"
            )
            self.assertTrue(user_columns["manager_id"]["nullable"])
            self.assertTrue(manager_id_index["unique"])

            with engine.connect() as connection:
                transaction = connection.begin()
                connection.execute(
                    text(
                        "INSERT INTO users (id, email, manager_id) "
                        "VALUES (2, 'new@example.com', '00127')"
                    )
                )
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO users (id, email, manager_id) "
                            "VALUES (3, 'duplicate@example.com', '00127')"
                        )
                    )
                transaction.rollback()
        finally:
            engine.dispose()

    def test_employee_number_migration_adds_nullable_unique_column(self):
        engine = create_engine("sqlite://")
        try:
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE users ("
                        "id INTEGER PRIMARY KEY, "
                        "email VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO users (id, email) VALUES (1, 'old@example.com')")
                )

            migrate_employee_number(engine)
            migrate_employee_number(engine)

            user_columns = {
                column["name"]: column
                for column in inspect(engine).get_columns("users")
            }
            indexes = inspect(engine).get_indexes("users")
            employee_number_index = next(
                index for index in indexes
                if index["name"] == "uq_users_employee_number"
            )
            self.assertTrue(user_columns["employee_number"]["nullable"])
            self.assertTrue(employee_number_index["unique"])

            with engine.connect() as connection:
                transaction = connection.begin()
                connection.execute(
                    text(
                        "INSERT INTO users (id, email, employee_number) "
                        "VALUES (2, 'crew@example.com', '00042')"
                    )
                )
                with self.assertRaises(IntegrityError):
                    connection.execute(
                        text(
                            "INSERT INTO users (id, email, employee_number) "
                            "VALUES (3, 'another@example.com', '00042')"
                        )
                    )
                transaction.rollback()
        finally:
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
