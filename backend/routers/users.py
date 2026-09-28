from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from datetime import datetime

# Navigation: reaching out of the 'routers' folder into the 'backend' folder
from ..database import get_db
from .. import models
from ..deps import get_current_user

# --- GLOBAL CONSTANTS ---
LEAGUE_ORDER = ["Paper", "Iron", "Bronze",
                "Silver", "Gold", "Platinum", "Diamond"]

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

# --- PYDANTIC MODELS ---


class XPUpdate(BaseModel):
    xp: int

# --- API ENDPOINTS ---


@router.get("/me")
def get_user_stats(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Handles the midnight reset for daily goals and returns 
    comprehensive profile and gamification data.
    """
    today = datetime.now().date()

    # ✨ THE MIDNIGHT RESET ✨
    if current_user.last_active_date != today:
        current_user.daily_xp = 0
        current_user.daily_lessons = 0
        current_user.last_active_date = today
        db.commit()
        db.refresh(current_user)

    return {
        "username": current_user.username,
        "email": current_user.email,
        "xp": current_user.xp or 0,
        "streak": current_user.streak or 0,
        "daily_xp": current_user.daily_xp or 0,
        "daily_lessons": current_user.daily_lessons or 0,
        "weekly_xp": current_user.weekly_xp or 0,
        "league": current_user.league or "Paper",
        "quests_completed": current_user.quests_completed or 0
    }


@router.post("/update_xp")
async def update_xp(data: XPUpdate, db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)):
    """
    Increments XP across all three trackers: Lifetime, Weekly (Leaderboard), and Daily.
    """
    points = data.xp
    today = datetime.now().date()

    # Reset daily stats if the user has crossed into a new day
    if current_user.last_active_date != today:
        current_user.daily_xp = 0
        current_user.daily_lessons = 0
        current_user.last_active_date = today
        # Inside update_xp
        current_user.quests_completed = (
            current_user.quests_completed or 0) + 1
    # Update all XP fields (ensuring None types are treated as 0)
    current_user.xp = (current_user.xp or 0) + points
    current_user.daily_xp = (current_user.daily_xp or 0) + points
    current_user.weekly_xp = (current_user.weekly_xp or 0) + points
    current_user.daily_lessons = (current_user.daily_lessons or 0) + 1

    db.commit()
    db.refresh(current_user)

    return {"success": True, "new_total": current_user.xp, "weekly_xp": current_user.weekly_xp}


@router.get("/leaderboard/data")
def get_leaderboard_data(league: str = "Paper", db: Session = Depends(get_db)):
    """
    Fetches users only in the specified league, sorted by Weekly XP.
    Defaults to 'Paper' if no league is provided in the URL.
    """
    # 1. 🎯 THE CRITICAL FIX: Filter by the league passed in the URL
    users = db.query(models.User)\
              .filter(models.User.league == league)\
              .order_by(models.User.weekly_xp.desc())\
              .limit(30)\
              .all()

    leaderboard = []
    for index, user in enumerate(users):
        rank = index + 1

        # 2. Determine Zone Logic (Top 10 / Mid 10 / Bottom 10)
        if rank <= 10:
            zone = "promote"
        elif rank <= 20:
            zone = "safe"
        else:
            zone = "demote"

        # 3. League Progression Logic
        # Ensure we have a valid current league string
        user_league_name = user.league or "Paper"

        try:
            current_idx = LEAGUE_ORDER.index(user_league_name)
        except ValueError:
            current_idx = 0  # Fallback to Paper if index fails

        # Determine next tier name for the UI
        if current_idx < len(LEAGUE_ORDER) - 1:
            next_league = LEAGUE_ORDER[current_idx + 1]
        else:
            next_league = "Diamond"  # Or your highest tier

        # 4. Compile User Record
        leaderboard.append({
            "username": user.username,
            "xp": user.weekly_xp or 0,
            "streak": user.streak or 0,
            "rank": rank,
            "zone": zone,
            "current_league": user_league_name,
            "next_tier": next_league
        })

    return leaderboard


# --- PAGE ROUTES (TEMPLATES) ---

@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    """
    Serves the Leaderboard HTML. 
    Importing 'templates' locally inside the function prevents Circular Imports.
    """
    from ..main import templates
    return templates.TemplateResponse(request=request, name="leaderboard.html")


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request):
    """Serves the User Profile HTML."""
    from ..main import templates
    return templates.TemplateResponse(request=request, name="profile.html")
