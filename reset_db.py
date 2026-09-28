from backend.database import engine
from backend.models import Base

print("Dropping old PostgreSQL tables...")
Base.metadata.drop_all(bind=engine)

print("Creating new PostgreSQL tables with updated schema...")
Base.metadata.create_all(bind=engine)

print("Database reset complete! You can delete this script now.")