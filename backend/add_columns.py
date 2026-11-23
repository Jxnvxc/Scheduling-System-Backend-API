from sqlalchemy import text
from app.database import engine

def add_columns():
    with engine.connect() as conn:
        print("🔍 Checking existing columns in 'users' table...\n")
        
        # Kunin ang listahan ng columns
        result = conn.execute(text("""
            SELECT column_name 
            FROM information_schema.columns 
            WHERE table_name = 'users'
        """))
        existing_columns = [row[0] for row in result]
        print(f"📋 Existing columns: {existing_columns}\n")
        
        # Idagdag ang crew_type kung wala pa
        if "crew_type" not in existing_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN crew_type VARCHAR"))
            conn.commit()
            print("✅ Added column: crew_type")
        else:
            print("⏭️  Column 'crew_type' already exists")
        
        # Idagdag ang employment_type kung wala pa
        if "employment_type" not in existing_columns:
            conn.execute(text("ALTER TABLE users ADD COLUMN employment_type VARCHAR"))
            conn.commit()
            print("✅ Added column: employment_type")
        else:
            print("⏭️  Column 'employment_type' already exists")
        
        print("\n🎉 Done! Pwede mo nang i-restart ang backend at subukan ulit mag-add ng crew.")

if __name__ == "__main__":
    add_columns()