import unittest

from sqlalchemy import create_engine, text

from app.database import (
    migrate_staffing_requirement_enabled,
    migrate_staffing_requirement_unique,
    migrate_station_shift_templates,
    migrate_standard_station_shift_names,
)


class StaffingRequirementMigrationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite://")
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE staffing_requirements ("
                    "id INTEGER PRIMARY KEY, "
                    "branch_id INTEGER NOT NULL, "
                    "station_id INTEGER NOT NULL, "
                    "shift_type VARCHAR(16) NOT NULL, "
                    "required_count INTEGER NOT NULL)"
                )
            )

    def tearDown(self):
        self.engine.dispose()

    def test_migration_adds_unique_index_and_is_idempotent(self):
        migrate_staffing_requirement_unique(self.engine)
        migrate_staffing_requirement_unique(self.engine)

        with self.engine.connect() as connection:
            indexes = connection.execute(
                text("PRAGMA index_list('staffing_requirements')")
            ).mappings().all()
        self.assertTrue(
            any(index["name"] == "uq_staffing_requirement_shift" for index in indexes)
        )

    def test_enabled_migration_adds_true_default_and_is_idempotent(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staffing_requirements "
                    "(branch_id, station_id, shift_type, required_count) "
                    "VALUES (2, 1, 'Mid', 1)"
                )
            )

        migrate_staffing_requirement_enabled(self.engine)
        migrate_staffing_requirement_enabled(self.engine)

        with self.engine.begin() as connection:
            self.assertTrue(
                connection.execute(
                    text(
                        "SELECT enabled FROM staffing_requirements "
                        "WHERE shift_type = 'Mid'"
                    )
                ).scalar_one()
            )
            connection.execute(
                text(
                    "UPDATE staffing_requirements SET enabled = FALSE "
                    "WHERE shift_type = 'Mid'"
                )
            )
        migrate_staffing_requirement_enabled(self.engine)
        with self.engine.connect() as connection:
            enabled = connection.execute(
                text(
                    "SELECT enabled FROM staffing_requirements "
                    "WHERE shift_type = 'Mid'"
                )
            ).scalar_one()
        self.assertFalse(enabled)

    def test_migration_fails_explicitly_when_duplicate_requirements_exist(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO staffing_requirements "
                    "(branch_id, station_id, shift_type, required_count) "
                    "VALUES (1, 2, 'Opening', 1), (1, 2, 'Opening', 2)"
                )
            )

        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            migrate_staffing_requirement_unique(self.engine)

    def test_shift_template_migration_preserves_station_hours_and_adds_defaults(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE stations ("
                    "id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL, "
                    "opening_start_time TIME NOT NULL, opening_end_time TIME NOT NULL, "
                    "mid_start_time TIME NOT NULL, mid_end_time TIME NOT NULL, "
                    "closing_start_time TIME NOT NULL, closing_end_time TIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO stations VALUES "
                    "(1, 2, '07:30:00', '15:30:00', '11:00:00', '19:00:00', "
                    "'14:00:00', '22:00:00')"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO staffing_requirements "
                    "(branch_id, station_id, shift_type, required_count) "
                    "VALUES (2, 1, 'Opening', 3)"
                )
            )

        migrate_station_shift_templates(self.engine)
        migrate_station_shift_templates(self.engine)

        with self.engine.connect() as connection:
            shifts = connection.execute(
                text(
                    "SELECT shift_type, required_count, start_time, end_time "
                    "FROM staffing_requirements ORDER BY shift_type"
                )
            ).mappings().all()
        self.assertEqual(
            [
                (
                    row["shift_type"],
                    row["required_count"],
                    str(row["start_time"]),
                    str(row["end_time"]),
                )
                for row in shifts
            ],
            [
                ("Closing", 1, "14:00:00", "22:00:00"),
                ("Mid", 1, "11:00:00", "19:00:00"),
                ("Opening", 3, "07:30:00", "15:30:00"),
            ],
        )

    def test_standard_shift_migration_renames_templates_and_assignments_by_time(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE stations ("
                    "id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL, "
                    "opening_start_time TIME NOT NULL, opening_end_time TIME NOT NULL, "
                    "mid_start_time TIME NOT NULL, mid_end_time TIME NOT NULL, "
                    "closing_start_time TIME NOT NULL, closing_end_time TIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO stations VALUES "
                    "(1, 2, '08:00:00', '16:00:00', '12:00:00', '20:00:00', "
                    "'14:00:00', '22:00:00')"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN start_time TIME "
                    "NOT NULL DEFAULT '08:00:00'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN end_time TIME "
                    "NOT NULL DEFAULT '16:00:00'"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO staffing_requirements "
                    "(branch_id, station_id, shift_type, required_count, start_time, end_time) "
                    "VALUES "
                    "(2, 1, 'Dinner', 1, '17:00:00', '22:00:00'), "
                    "(2, 1, 'Breakfast', 2, '06:00:00', '11:00:00'), "
                    "(2, 1, 'Lunch', 3, '11:00:00', '17:00:00')"
                )
            )
            connection.execute(
                text(
                    "CREATE TABLE shift_assignments ("
                    "id INTEGER PRIMARY KEY, station_id INTEGER NOT NULL, "
                    "shift_name VARCHAR(100) NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO shift_assignments VALUES "
                    "(1, 1, 'Breakfast'), (2, 1, 'Lunch'), (3, 1, 'Dinner')"
                )
            )
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX uq_staffing_requirement_shift "
                    "ON staffing_requirements (branch_id, station_id, shift_type)"
                )
            )

        migrate_standard_station_shift_names(self.engine)
        migrate_standard_station_shift_names(self.engine)

        with self.engine.connect() as connection:
            shifts = connection.execute(
                text(
                    "SELECT shift_type, required_count, start_time, end_time "
                    "FROM staffing_requirements ORDER BY start_time"
                )
            ).mappings().all()
            assignments = connection.execute(
                text(
                    "SELECT shift_name FROM shift_assignments "
                    "ORDER BY id"
                )
            ).scalars().all()
        self.assertEqual(
            [
                (row["shift_type"], row["required_count"], str(row["start_time"]), str(row["end_time"]))
                for row in shifts
            ],
            [
                ("Opening", 2, "06:00:00", "11:00:00"),
                ("Mid", 3, "11:00:00", "17:00:00"),
                ("Closing", 1, "17:00:00", "22:00:00"),
            ],
        )
        self.assertEqual(assignments, ["Opening", "Mid", "Closing"])

    def test_standard_shift_migration_refuses_to_drop_excess_templates(self):
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    "CREATE TABLE stations ("
                    "id INTEGER PRIMARY KEY, branch_id INTEGER NOT NULL, "
                    "opening_start_time TIME NOT NULL, opening_end_time TIME NOT NULL, "
                    "mid_start_time TIME NOT NULL, mid_end_time TIME NOT NULL, "
                    "closing_start_time TIME NOT NULL, closing_end_time TIME NOT NULL)"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO stations VALUES "
                    "(1, 2, '08:00:00', '16:00:00', '12:00:00', '20:00:00', "
                    "'14:00:00', '22:00:00')"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN start_time TIME "
                    "NOT NULL DEFAULT '08:00:00'"
                )
            )
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN end_time TIME "
                    "NOT NULL DEFAULT '16:00:00'"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO staffing_requirements "
                    "(branch_id, station_id, shift_type, required_count) "
                    "VALUES (2, 1, 'Opening', 1), (2, 1, 'Mid', 1), "
                    "(2, 1, 'Closing', 1), (2, 1, 'Extra', 1)"
                )
            )

        with self.assertRaisesRegex(RuntimeError, "more than three"):
            migrate_standard_station_shift_names(self.engine)

        with self.engine.connect() as connection:
            names = connection.execute(
                text("SELECT shift_type FROM staffing_requirements ORDER BY id")
            ).scalars().all()
        self.assertEqual(names, ["Opening", "Mid", "Closing", "Extra"])


if __name__ == "__main__":
    unittest.main()
