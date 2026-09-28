"""Wipe the LOCAL development database and rebuild it from the migrations.

Usage:  python scripts/reset_local_db.py --yes

Needed once to move an old local database (created before migrations existed)
onto the migration-managed schema. DELETES ALL DATA in that database.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import MetaData, create_engine  # noqa: E402
from sqlalchemy.engine import make_url  # noqa: E402

from backend.config import settings  # noqa: E402

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", None}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--yes", action="store_true", help="confirm that all data may be deleted")
    parser.add_argument("--allow-remote", action="store_true", help="allow a non-localhost database")
    args = parser.parse_args()

    url = make_url(settings.database_url)
    if settings.is_production or settings.on_vercel:
        sys.exit("Refusing to run in production.")
    if url.host not in LOCAL_HOSTS and not args.allow_remote:
        sys.exit(f"Refusing to wipe non-local database host {url.host!r} (pass --allow-remote if you're sure).")
    if not args.yes:
        sys.exit(f"This deletes ALL data in {url.render_as_string(hide_password=True)}. Re-run with --yes.")

    engine = create_engine(url)
    existing = MetaData()
    existing.reflect(bind=engine)
    print(f"Dropping {len(existing.tables)} tables...")
    existing.drop_all(bind=engine)
    engine.dispose()

    print("Applying migrations...")
    command.upgrade(Config(str(Path(__file__).resolve().parents[1] / "alembic.ini")), "head")
    print("Done.")


if __name__ == "__main__":
    main()
