from sqlalchemy import text
from app.database import engine

def alter_users():
    with engine.connect() as conn:
        print("Checking 'users' table columns...")
        
        # Add branch_id
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN branch_id INTEGER REFERENCES branches(id)"))
            conn.commit()
            print("✅ Added branch_id")
        except Exception as e:
            print("⏭️ branch_id exists or error:", e)

        # Add min_hours
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN min_hours INTEGER DEFAULT 0"))
            conn.commit()
            print("✅ Added min_hours")
        except Exception as e:
            print("⏭️ min_hours exists or error:", e)

        # Add max_hours
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN max_hours INTEGER DEFAULT 40"))
            conn.commit()
            print("✅ Added max_hours")
        except Exception as e:
            print("⏭️ max_hours exists or error:", e)

        # Add qualified_stations
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN qualified_stations VARCHAR"))
            conn.commit()
            print("✅ Added qualified_stations")
        except Exception as e:
            print("⏭️ qualified_stations exists or error:", e)

if __name__ == "__main__":
    alter_users()
    print("Done! 🎉")