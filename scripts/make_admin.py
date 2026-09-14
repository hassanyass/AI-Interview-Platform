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
        # 1. Find user by email directly in Supabase's auth.users — this is the
        # source of truth for the UUID and doesn't depend on a candidate_profiles
        # row existing (that row is only created lazily by candidate-facing
        # endpoints, which the admin login path never calls).
        res = await session.execute(
            text("SELECT id FROM auth.users WHERE email = :email"),
            {"email": email}
        )
        row = res.fetchone()

        if not row:
            print(f"User '{email}' not found in auth.users.")
            print("Please log into the frontend at least once so Supabase creates your account.")
            return

        user_uuid = row[0]
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
