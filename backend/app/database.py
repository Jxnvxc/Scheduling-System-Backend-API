from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings

engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def migrate_station_operating_hours(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    with database_engine.begin() as connection:
        if inspector.has_table("stations"):
            station_columns = {
                column["name"] for column in inspector.get_columns("stations")
            }
            shift_columns = {
                "opening_start_time": "08:00:00",
                "opening_end_time": "16:00:00",
                "mid_start_time": "12:00:00",
                "mid_end_time": "20:00:00",
                "closing_start_time": "14:00:00",
                "closing_end_time": "22:00:00",
            }
            for column_name, default_time in shift_columns.items():
                if column_name not in station_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE stations ADD COLUMN {column_name} "
                            f"TIME NOT NULL DEFAULT '{default_time}'"
                        )
                    )

        if inspector.has_table("shift_assignments"):
            assignment_columns = {
                column["name"]
                for column in inspector.get_columns("shift_assignments")
            }
            for column_name in ("start_time", "end_time"):
                if column_name not in assignment_columns:
                    connection.execute(
                        text(
                            f"ALTER TABLE shift_assignments ADD COLUMN "
                            f"{column_name} TIME"
                        )
                    )

            connection.execute(
                text(
                    "UPDATE shift_assignments SET "
                    "start_time = CASE shift_name "
                    "WHEN 'Opening' THEN '08:00:00' "
                    "WHEN 'Mid' THEN '12:00:00' "
                    "WHEN 'Closing' THEN '14:00:00' "
                    "ELSE start_time END, "
                    "end_time = CASE shift_name "
                    "WHEN 'Opening' THEN '16:00:00' "
                    "WHEN 'Mid' THEN '20:00:00' "
                    "WHEN 'Closing' THEN '22:00:00' "
                    "ELSE end_time END "
                    "WHERE start_time IS NULL OR end_time IS NULL"
                )
            )


def migrate_shift_assignment_acknowledgment(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("shift_assignments"):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("shift_assignments")
    }
    if "acknowledged_at" not in columns:
        column_type = (
            "TIMESTAMP WITH TIME ZONE"
            if database_engine.dialect.name == "postgresql"
            else "DATETIME"
        )
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE shift_assignments ADD COLUMN "
                    f"acknowledged_at {column_type}"
                )
            )


def migrate_head_user_role(database_engine: Engine = engine):
    if database_engine.dialect.name != "postgresql":
        return

    with database_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as connection:
        enum_exists = connection.execute(
            text(
                "SELECT EXISTS ("
                "SELECT 1 FROM pg_type WHERE typname = 'userrole'"
                ")"
            )
        ).scalar_one()
        if enum_exists:
            connection.execute(text("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'HEAD'"))


def migrate_manager_id(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("users"):
        return

    user_columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    with database_engine.begin() as connection:
        if "manager_id" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN manager_id VARCHAR(32)")
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_manager_id "
                "ON users (manager_id)"
            )
        )


def migrate_employee_number(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("users"):
        return

    user_columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    with database_engine.begin() as connection:
        if "employee_number" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN employee_number VARCHAR(32)")
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_employee_number "
                "ON users (employee_number)"
            )
        )


def migrate_branch_name_ci_unique(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("branches"):
        return

    with database_engine.begin() as connection:
        duplicate_name = connection.execute(
            text(
                "SELECT lower(trim(name)) "
                "FROM branches "
                "GROUP BY lower(trim(name)) "
                "HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        ).first()
        if duplicate_name:
            raise RuntimeError(
                "Cannot enforce case-insensitive branch name uniqueness: "
                "duplicate branch names exist after trimming whitespace."
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_branches_name_ci "
                "ON branches (lower(trim(name)))"
            )
        )


def migrate_staffing_requirement_unique(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("staffing_requirements"):
        return

    with database_engine.begin() as connection:
        duplicate = connection.execute(
            text(
                "SELECT branch_id, station_id, shift_type "
                "FROM staffing_requirements "
                "GROUP BY branch_id, station_id, shift_type "
                "HAVING COUNT(*) > 1 "
                "LIMIT 1"
            )
        ).first()
        if duplicate:
            raise RuntimeError(
                "Cannot enforce unique staffing requirements: duplicate "
                "branch, station, and shift entries exist."
            )
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS "
                "uq_staffing_requirement_shift "
                "ON staffing_requirements (branch_id, station_id, shift_type)"
            )
        )


def migrate_station_shift_templates(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("staffing_requirements"):
        return

    requirement_columns = {
        column["name"]
        for column in inspector.get_columns("staffing_requirements")
    }
    with database_engine.begin() as connection:
        if "start_time" not in requirement_columns:
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN "
                    "start_time TIME NOT NULL DEFAULT '08:00:00'"
                )
            )
        if "end_time" not in requirement_columns:
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN "
                    "end_time TIME NOT NULL DEFAULT '16:00:00'"
                )
            )
        if (
            database_engine.dialect.name == "postgresql"
            and any(
                column["name"] == "shift_type"
                and column.get("type") is not None
                and getattr(column["type"], "length", 0) != 100
                for column in inspector.get_columns("staffing_requirements")
            )
        ):
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements "
                    "ALTER COLUMN shift_type TYPE VARCHAR(100)"
                )
            )

        if not inspector.has_table("stations"):
            return
        stations = connection.execute(
            text(
                "SELECT id, opening_start_time, opening_end_time, "
                "mid_start_time, mid_end_time, closing_start_time, "
                "closing_end_time FROM stations"
            )
        ).mappings().all()
        defaults = {
            "Opening": ("opening_start_time", "opening_end_time"),
            "Mid": ("mid_start_time", "mid_end_time"),
            "Closing": ("closing_start_time", "closing_end_time"),
        }
        for station in stations:
            existing = connection.execute(
                text(
                    "SELECT shift_type, start_time, end_time "
                    "FROM staffing_requirements WHERE station_id = :station_id"
                ),
                {"station_id": station["id"]},
            ).mappings().all()
            existing_names = {row["shift_type"] for row in existing}
            for shift in existing:
                time_columns = defaults.get(shift["shift_type"])
                if time_columns and (
                    "start_time" not in requirement_columns
                    or "end_time" not in requirement_columns
                ):
                    connection.execute(
                        text(
                            "UPDATE staffing_requirements "
                            "SET start_time = :start_time, end_time = :end_time "
                            "WHERE station_id = :station_id AND shift_type = :shift_type"
                        ),
                        {
                            "start_time": station[time_columns[0]],
                            "end_time": station[time_columns[1]],
                            "station_id": station["id"],
                            "shift_type": shift["shift_type"],
                        },
                    )

            for name, (start_column, end_column) in defaults.items():
                if name not in existing_names:
                    connection.execute(
                        text(
                            "INSERT INTO staffing_requirements "
                            "(branch_id, station_id, shift_type, required_count, "
                            "start_time, end_time) "
                            "SELECT branch_id, id, :shift_type, :required_count, "
                            f"{start_column}, {end_column} FROM stations WHERE id = :station_id"
                        ),
                        {
                            "shift_type": name,
                            "required_count": 1,
                            "station_id": station["id"],
                        },
                    )


def migrate_standard_station_shift_names(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("staffing_requirements"):
        return
    has_stations = inspector.has_table("stations")
    has_assignments = inspector.has_table("shift_assignments")
    if not has_stations:
        return

    standard_names = ("Opening", "Mid", "Closing")
    defaults = {
        "Opening": ("opening_start_time", "opening_end_time"),
        "Mid": ("mid_start_time", "mid_end_time"),
        "Closing": ("closing_start_time", "closing_end_time"),
    }

    with database_engine.begin() as connection:
        stations = connection.execute(
            text(
                "SELECT id, opening_start_time, opening_end_time, "
                "mid_start_time, mid_end_time, closing_start_time, "
                "closing_end_time FROM stations"
            )
        ).mappings().all()
        requirement_rows = connection.execute(
            text(
                "SELECT id, station_id, shift_type, required_count, "
                "start_time, end_time FROM staffing_requirements"
            )
        ).mappings().all()
        rows_by_station: dict[int, list[dict]] = {}
        for row in requirement_rows:
            rows_by_station.setdefault(row["station_id"], []).append(dict(row))

        assignment_aliases: dict[tuple[int, str], str] = {}
        for station in stations:
            rows = rows_by_station.get(station["id"], [])
            if len(rows) > len(standard_names):
                raise RuntimeError(
                    "Cannot migrate station shift names: station "
                    f"{station['id']} has more than three configured shifts."
                )

            rows_by_name: dict[str, dict] = {}
            for row in rows:
                normalized = row["shift_type"].strip().casefold()
                if normalized in rows_by_name:
                    raise RuntimeError(
                        "Cannot migrate station shift names: station "
                        f"{station['id']} has duplicate shift labels ignoring case."
                    )
                rows_by_name[normalized] = row

            assigned_rows: dict[str, dict] = {}
            for name in standard_names:
                row = rows_by_name.pop(name.casefold(), None)
                if row is not None:
                    assigned_rows[name] = row

            available_names = [
                name for name in standard_names if name not in assigned_rows
            ]
            custom_rows = sorted(
                rows_by_name.values(),
                key=lambda row: (str(row["start_time"]), str(row["end_time"]), row["id"]),
            )
            assigned_rows.update(zip(available_names, custom_rows))

            for index, (name, row) in enumerate(assigned_rows.items()):
                old_name = row["shift_type"]
                assignment_aliases[(station["id"], old_name.casefold())] = name
                connection.execute(
                    text(
                        "UPDATE staffing_requirements SET shift_type = :temporary_name "
                        "WHERE id = :requirement_id"
                    ),
                    {
                        "temporary_name": f"__shift_migration_{station['id']}_{index}__",
                        "requirement_id": row["id"],
                    },
                )

            for name, row in assigned_rows.items():
                connection.execute(
                    text(
                        "UPDATE staffing_requirements SET shift_type = :shift_name "
                        "WHERE id = :requirement_id"
                    ),
                    {"shift_name": name, "requirement_id": row["id"]},
                )

            for name, (start_column, end_column) in defaults.items():
                if name not in assigned_rows:
                    connection.execute(
                        text(
                            "INSERT INTO staffing_requirements "
                            "(branch_id, station_id, shift_type, required_count, "
                            "start_time, end_time) "
                            "SELECT branch_id, id, :shift_name, 1, "
                            f"{start_column}, {end_column} FROM stations WHERE id = :station_id"
                        ),
                        {"shift_name": name, "station_id": station["id"]},
                    )

        if has_assignments:
            for (station_id, old_name), new_name in assignment_aliases.items():
                connection.execute(
                    text(
                        "UPDATE shift_assignments SET shift_name = :new_name "
                        "WHERE station_id = :station_id AND lower(trim(shift_name)) = :old_name"
                    ),
                    {
                        "new_name": new_name,
                        "station_id": station_id,
                        "old_name": old_name,
                    },
                )


def migrate_crew_request_branch(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("crew_requests"):
        return
    if not inspector.has_table("users"):
        raise RuntimeError("Cannot migrate crew requests without the users table.")

    request_columns = {
        column["name"] for column in inspector.get_columns("crew_requests")
    }
    if "requester_id" not in request_columns:
        raise RuntimeError("Cannot migrate crew requests without requester_id.")

    if "branch_id" not in request_columns:
        with database_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE crew_requests ADD COLUMN branch_id INTEGER")
            )

    with database_engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE crew_requests SET branch_id = ("
                "SELECT branch_id FROM users "
                "WHERE users.id = crew_requests.requester_id"
                ") WHERE branch_id IS NULL"
            )
        )
        unresolved = connection.execute(
            text("SELECT id FROM crew_requests WHERE branch_id IS NULL LIMIT 1")
        ).first()
        if unresolved:
            raise RuntimeError(
                "Cannot migrate crew requests: at least one requester is not "
                "assigned to a branch."
            )

        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_crew_requests_branch_status "
                "ON crew_requests (branch_id, status)"
            )
        )

        if database_engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "ALTER TABLE crew_requests "
                    "ALTER COLUMN branch_id SET NOT NULL"
                )
            )
            foreign_keys = inspector.get_foreign_keys("crew_requests")
            if not any(
                foreign_key.get("constrained_columns") == ["branch_id"]
                and foreign_key.get("referred_table") == "branches"
                for foreign_key in foreign_keys
            ):
                connection.execute(
                    text(
                        "ALTER TABLE crew_requests "
                        "ADD CONSTRAINT fk_crew_requests_branch "
                        "FOREIGN KEY (branch_id) REFERENCES branches(id) "
                        "ON DELETE CASCADE"
                    )
                )


def migrate_staffing_requirement_enabled(database_engine: Engine = engine):
    inspector = inspect(database_engine)
    if not inspector.has_table("staffing_requirements"):
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("staffing_requirements")
    }
    if "enabled" not in columns:
        with database_engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE staffing_requirements ADD COLUMN "
                    "enabled BOOLEAN NOT NULL DEFAULT TRUE"
                )
            )


def migrate_crew_worked_hours(database_engine: Engine = engine):
    """Add the cached worked_hours column and backfill it from the active
    15-day pay-period window. Never touches historical schedule records."""
    inspector = inspect(database_engine)
    if not inspector.has_table("users"):
        return

    from datetime import date
    from sqlalchemy.orm import sessionmaker

    user_columns = {
        column["name"] for column in inspector.get_columns("users")
    }
    SessionLocal = sessionmaker(bind=database_engine)
    with SessionLocal() as session:
        if "worked_hours" not in user_columns:
            session.execute(
                text("ALTER TABLE users ADD COLUMN worked_hours FLOAT DEFAULT 0.0")
            )
            session.commit()

        from app.services.scheduling import period_bounds, shift_hours
        from app.models.user import User
        from app.models.assignment import ShiftAssignment

        today = date.today()
        period_start, period_end = period_bounds(today)
        assignments = session.query(ShiftAssignment).filter(
            ShiftAssignment.status == "Published",
            ShiftAssignment.schedule_date >= period_start,
            ShiftAssignment.schedule_date <= period_end,
        ).all()

        hours_by_user: dict[int, float] = {}
        for assignment in assignments:
            try:
                hours_by_user[assignment.user_id] = (
                    hours_by_user.get(assignment.user_id, 0.0)
                    + shift_hours(
                        assignment.shift_name,
                        start_time=assignment.start_time,
                        end_time=assignment.end_time,
                    )
                )
            except Exception:
                # Unknown shift or unparsable time: ignore for the cache.
                hours_by_user.setdefault(assignment.user_id, 0.0)

        for user_id, hours in hours_by_user.items():
            session.query(User).filter(User.id == user_id).update(
                {User.worked_hours: round(hours, 2)},
                synchronize_session=False,
            )
        session.commit()


def migrate_holidays_table(database_engine: Engine = engine):
    """Create the holidays table if it does not exist."""
    inspector = inspect(database_engine)
    if inspector.has_table("holidays"):
        return
    with database_engine.begin() as connection:
        if database_engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "CREATE TABLE holidays ("
                    "id SERIAL PRIMARY KEY, "
                    "holiday_date DATE NOT NULL, "
                    "name VARCHAR(255) NOT NULL, "
                    "holiday_type VARCHAR(50) NOT NULL, "
                    "branch_id INTEGER, "
                    "created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), "
                    "CONSTRAINT fk_holidays_branch FOREIGN KEY (branch_id) "
                    "REFERENCES branches(id) ON DELETE CASCADE"
                    ")"
                )
            )
        else:
            connection.execute(
                text(
                    "CREATE TABLE holidays ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "holiday_date DATE NOT NULL, "
                    "name VARCHAR(255) NOT NULL, "
                    "holiday_type VARCHAR(50) NOT NULL, "
                    "branch_id INTEGER, "
                    "created_at DATETIME DEFAULT CURRENT_TIMESTAMP, "
                    "FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE"
                    ")"
                )
            )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_holidays_date ON holidays (holiday_date)")
        )


def migrate_system_settings_table(database_engine: Engine = engine):
    """Create the system_settings table if it does not exist."""
    inspector = inspect(database_engine)
    if inspector.has_table("system_settings"):
        return
    with database_engine.begin() as connection:
        if database_engine.dialect.name == "postgresql":
            connection.execute(
                text(
                    "CREATE TABLE system_settings ("
                    "id SERIAL PRIMARY KEY, "
                    "branch_id INTEGER, "
                    "key VARCHAR(255) NOT NULL, "
                    "value VARCHAR(255) NOT NULL, "
                    "updated_at TIMESTAMP WITH TIME ZONE, "
                    "CONSTRAINT fk_system_settings_branch FOREIGN KEY (branch_id) "
                    "REFERENCES branches(id) ON DELETE CASCADE"
                    ")"
                )
            )
        else:
            connection.execute(
                text(
                    "CREATE TABLE system_settings ("
                    "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                    "branch_id INTEGER, "
                    "key VARCHAR(255) NOT NULL, "
                    "value VARCHAR(255) NOT NULL, "
                    "updated_at DATETIME, "
                    "FOREIGN KEY (branch_id) REFERENCES branches(id) ON DELETE CASCADE"
                    ")"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_system_settings_key "
                "ON system_settings (key)"
            )
        )


def migrate_station_priority(database_engine: Engine = engine):
    """Add a priority column (1=critical, 2=important, 3=can be empty) to
    the stations table. Existing stations default to priority 2."""
    inspector = inspect(database_engine)
    if not inspector.has_table("stations"):
        return
    columns = {column["name"] for column in inspector.get_columns("stations")}
    if "priority" not in columns:
        with database_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE stations ADD COLUMN priority INTEGER DEFAULT 2")
            )


def migrate_shift_minimum_crew(database_engine: Engine = engine):
    """Add a minimum_crew column to staffing_requirements. NULL means
    "use required crew" (existing behavior unchanged)."""
    inspector = inspect(database_engine)
    if not inspector.has_table("staffing_requirements"):
        return
    columns = {column["name"] for column in inspector.get_columns("staffing_requirements")}
    if "minimum_crew" not in columns:
        with database_engine.begin() as connection:
            connection.execute(
                text("ALTER TABLE staffing_requirements ADD COLUMN minimum_crew INTEGER")
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()