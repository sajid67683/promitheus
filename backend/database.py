import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Load the environment variables from your .env file
load_dotenv()

# Get the database URL
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

# Create the SQLAlchemy engine
# Change this line in backend/database.py
engine = create_engine(
    SQLALCHEMY_DATABASE_URL, 
    connect_args={"connect_timeout": 10} 
)

# Create a sessionmaker to talk to the database
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# This Base class is what all our database models will inherit from
Base = declarative_base()

# A helper function to get the database session for our API routes


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
