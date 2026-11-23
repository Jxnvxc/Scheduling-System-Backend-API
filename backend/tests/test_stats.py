import unittest
from datetime import time

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models.branch import Branch
from app.models.user import User, UserRole
from app.routers.stats import get_manager_stats


class ManagerStatsTests(unittest.TestCase):
    def test_manager_stats_counts_only_crew_in_assigned_branch(self):
        engine = create_engine("sqlite://")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        try:
            branch = Branch(
                name="Stats branch",
                opening_time=time(8, 0),
                closing_time=time(22, 0),
            )
            other_branch = Branch(
                name="Other stats branch",
                opening_time=time(8, 0),
                closing_time=time(22, 0),
            )
            session.add_all([branch, other_branch])
            session.flush()
            manager = User(
                email="stats-manager@example.com",
                password_hash="hash",
                full_name="Manager",
                role=UserRole.MANAGER,
                branch_id=branch.id,
            )
            session.add_all([
                manager,
                User(
                    email="stats-crew@example.com",
                    password_hash="hash",
                    full_name="Crew",
                    role=UserRole.EMPLOYEE,
                    branch_id=branch.id,
                ),
                User(
                    email="other-stats-crew@example.com",
                    password_hash="hash",
                    full_name="Other Crew",
                    role=UserRole.EMPLOYEE,
                    branch_id=other_branch.id,
                ),
            ])
            session.commit()

            result = get_manager_stats(session, manager)

            self.assertEqual(result["team_members"], 1)
        finally:
            session.close()
            Base.metadata.drop_all(engine)
            engine.dispose()


if __name__ == "__main__":
    unittest.main()
