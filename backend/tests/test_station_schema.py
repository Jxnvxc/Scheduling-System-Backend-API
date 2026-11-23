import unittest
from datetime import time

from pydantic import ValidationError
from sqlalchemy import create_engine, inspect, text

from app.routers.station import _remove_station_qualification, router
from app.database import migrate_station_operating_hours
from app.schemas.station import StationCreate


class StationSchemaTests(unittest.TestCase):
    def test_accepts_valid_station_hours(self):
        station = StationCreate(
            name="Cashier",
            closing_start_time=time(14, 0),
            closing_end_time=time(20, 0),
        )

        self.assertEqual(station.closing_start_time, time(14, 0))
        self.assertEqual(station.closing_end_time, time(20, 0))

    def test_rejects_end_time_before_or_equal_to_start_time(self):
        with self.assertRaises(ValidationError):
            StationCreate(
                name="Cashier",
                closing_start_time=time(20, 0),
                closing_end_time=time(14, 0),
            )

    def test_strips_station_name_and_rejects_blank_names(self):
        station = StationCreate(name="  Cashier  ")
        self.assertEqual(station.name, "Cashier")

        with self.assertRaises(ValidationError):
            StationCreate(name="   ")

    def test_client_cannot_set_station_branch_in_create_schema(self):
        with self.assertRaises(ValidationError):
            StationCreate(name="Kitchen", branch_id=123)

    def test_removing_station_qualification_only_removes_matching_id(self):
        self.assertEqual(
            _remove_station_qualification("1, 12, 3", 1),
            "12,3",
        )
        self.assertIsNone(_remove_station_qualification("4", 4))

    def test_station_router_exposes_edit_and_remove_endpoints(self):
        route_methods = {
            (route.path, method)
            for route in router.routes
            for method in route.methods
        }

        self.assertIn(("/stations/{station_id}", "PUT"), route_methods)
        self.assertIn(("/stations/{station_id}", "DELETE"), route_methods)

    def test_migration_adds_station_shifts_and_assignment_time_snapshots(self):
        test_engine = create_engine("sqlite://")
        try:
            with test_engine.begin() as connection:
                connection.execute(
                    text(
                        "CREATE TABLE stations ("
                        "id INTEGER PRIMARY KEY, "
                        "branch_id INTEGER NOT NULL, "
                        "name VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO stations VALUES (1, 1, 'Kitchen')")
                )
                connection.execute(
                    text(
                        "CREATE TABLE shift_assignments ("
                        "id INTEGER PRIMARY KEY, "
                        "shift_name VARCHAR NOT NULL)"
                    )
                )
                connection.execute(
                    text("INSERT INTO shift_assignments VALUES (1, 'Closing')")
                )

            migrate_station_operating_hours(test_engine)
            migrate_station_operating_hours(test_engine)

            with test_engine.connect() as connection:
                station_columns = {
                    column["name"]
                    for column in inspect(test_engine).get_columns("stations")
                }
                station_row = connection.execute(
                    text(
                        "SELECT closing_start_time, closing_end_time "
                        "FROM stations WHERE id = 1"
                    )
                ).one()
                assignment_row = connection.execute(
                    text(
                        "SELECT start_time, end_time FROM shift_assignments "
                        "WHERE id = 1"
                    )
                ).one()

            self.assertIn("opening_start_time", station_columns)
            self.assertEqual(station_row.closing_start_time, "14:00:00")
            self.assertEqual(station_row.closing_end_time, "22:00:00")
            self.assertEqual(assignment_row.start_time, "14:00:00")
            self.assertEqual(assignment_row.end_time, "22:00:00")
        finally:
            test_engine.dispose()


if __name__ == "__main__":
    unittest.main()
