"""One-off: create the shared demo admin account for the 2-week free-tier
test (docs/deployment-guide.md), then grant it the 'admin' role the same
way scripts/make_admin.py does for a real signup.

Unlike make_admin.py (which only grants a role to an ALREADY-signed-up
Supabase user), this creates the auth.users row itself via Supabase's
Admin REST API (service-role key as a bearer token) with email_confirm
=True, since there's no real person who will ever click a confirmation
email for a shared demo account.

Deliberately calls the REST API directly with httpx rather than the
supabase-py SDK's own client: create_client() in the installed version
(2.31.0) validates supabase_key against a regex that only matches the
old three-segment JWT key format, and unconditionally rejects this
project's newer "sb_secret_..." key with "Invalid API key" -- a real SDK
limitation (the same call already exists, unguarded, in
resume_service.py -- worth a look separately, not fixed here).

Usage:
    python scripts/create_demo_admin.py <email> <password>
"""
import sys
import asyncio

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

sys.path.insert(0, "./backend")
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from backend.db.session import engine  # reuses the same engine (and Windows DNS workaround) as the app
from backend.core.config import settings


async def create_demo_admin(email: str, password: str):
    admin_headers = {
        "apikey": settings.SUPABASE_SECRET_KEY,
        "Authorization": f"Bearer {settings.SUPABASE_SECRET_KEY}",
        "Content-Type": "application/json",
    }

    user_id = None
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            f"{settings.SUPABASE_URL}/auth/v1/admin/users",
            headers=admin_headers,
            json={"email": email, "password": password, "email_confirm": True},
        )
        if resp.status_code in (200, 201):
            user_id = resp.json()["id"]
            print(f"Created new Supabase auth user {email} (id={user_id})")
        elif resp.status_code == 422 or "already" in resp.text.lower() or "exists" in resp.text.lower():
            print(f"{email} already exists in auth.users — looking up its id instead.")
        else:
            print(f"Unexpected error creating user ({resp.status_code}): {resp.text}")
            return

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        if user_id is None:
            res = await session.execute(
                text("SELECT id FROM auth.users WHERE email = :email"),
                {"email": email},
            )
            row = res.fetchone()
            if not row:
                print(f"Could not find or create {email}. Aborting.")
                return
            user_id = row[0]
            print(f"Found existing user {email} (id={user_id})")

        try:
            await session.execute(
                text("""
                INSERT INTO users_roles (id, user_id, role)
                VALUES (gen_random_uuid(), :uuid, 'admin')
                """),
                {"uuid": str(user_id)},
            )
            await session.commit()
            print(f"Success! {email} is now an admin.")
        except Exception as e:
            await session.rollback()
            if "unique constraint" in str(e).lower() or "duplicate key" in str(e).lower():
                print(f"{email} is already an admin!")
            else:
                print(f"Error setting admin role: {e}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python scripts/create_demo_admin.py <email> <password>")
    else:
        asyncio.run(create_demo_admin(sys.argv[1], sys.argv[2]))
