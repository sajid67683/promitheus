from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from .models import User
from .database import SQLALCHEMY_DATABASE_URL
from .routers.users import LEAGUE_ORDER

engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def process_weekly_shuffle():
    db = SessionLocal()
    try:
        print("\n📸 Taking a snapshot of all users...")
        # 1. Fetch ALL users once to prevent the "Domino Effect"
        all_users = db.query(User).all()

        # 2. Group them by their CURRENT league in Python memory
        league_groups = {league: [] for league in LEAGUE_ORDER}
        for user in all_users:
            league_name = user.league or "Paper"
            if league_name in league_groups:
                league_groups[league_name].append(user)
            else:
                league_groups["Paper"].append(user)

        # 3. Process each group safely
        for league_name in LEAGUE_ORDER:
            print(f"\nProcessing {league_name} League...")

            # Sort the users in THIS league by weekly_xp (highest to lowest)
            users_in_league = sorted(
                league_groups[league_name],
                key=lambda u: (u.weekly_xp or 0),
                reverse=True
            )

            if not users_in_league:
                print("  No users found in this league.")
                continue

            for index, user in enumerate(users_in_league):
                rank = index + 1
                # Use their original league index
                current_index = LEAGUE_ORDER.index(league_name)

                # --- PROMOTION ZONE (Top 10) ---
                if rank <= 10 and current_index < len(LEAGUE_ORDER) - 1:
                    user.league = LEAGUE_ORDER[current_index + 1]
                    print(f"  🔼 {user.username} promoted to {user.league}")

                # --- DEMOTION ZONE (Rank 21+) ---
                elif rank > 20 and current_index > 0:
                    user.league = LEAGUE_ORDER[current_index - 1]
                    print(f"  🔽 {user.username} demoted to {user.league}")

                else:
                    print(f"  🛡️ {user.username} remains in {league_name}")

                # --- RESET WEEKLY & DAILY STATS ---
                user.weekly_xp = 0
                user.daily_xp = 0
                user.daily_lessons = 0

        # 4. Save ALL the calculated changes to the database at the very end
        db.commit()
        print("\n✅ Weekly shuffle completed! Everyone is reset for Monday. 🚀")

    except Exception as e:
        print(f"\n❌ Error during shuffle: {e}")
        db.rollback()
    finally:
        db.close()


if __name__ == "__main__":
    print("Starting Weekly League Shuffle...")
    process_weekly_shuffle()
