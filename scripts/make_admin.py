import sys
import asyncio
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, './backend')
from backend.db.session import engine  # reuses the same engine (and Windows DNS workaround) as the app

async def make_admin(email: str):
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    async with async_session() as session:
        # 1. Find user by email to get their Supabase UUID
        res = await session.execute(
            text("SELECT supabase_user_id FROM candidate_profiles WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()
        
        if not row:
            print(f"User '{email}' not found in the database.")
            print("Please log into the frontend at least once so your profile is created.")
            return
            
        user_uuid = row[0]
        if not user_uuid:
            print(f"User '{email}' exists but has no Supabase UUID attached.")
            print("Please log out and log back into the frontend to link your account.")
            return
            
        print(f"Found user {email} (UUID: {user_uuid})")
        
        # 2. Insert into users_roles
        try:
            await session.execute(
                text("""
                INSERT INTO users_roles (id, user_id, role) 
                VALUES (gen_random_uuid(), :uuid, 'admin')
                """),
                {"uuid": user_uuid}
            )
            await session.commit()
            print(f"Success! {email} is now an admin.")
            print("Refresh your browser to see the /admin routes!")
        except Exception as e:
            await session.rollback()
            if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                print(f"{email} is already an admin!")
            else:
                print(f"Error setting admin role: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/make_admin.py <your-email@example.com>")
    else:
        asyncio.run(make_admin(sys.argv[1]))
