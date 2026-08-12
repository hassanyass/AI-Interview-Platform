from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.core.security import get_current_user

# Re-export for convenience
db_dependency = Depends(get_db)
current_user_dependency = Depends(get_current_user)
