from sqlalchemy import Column, Integer, String, Text, Boolean, ForeignKey, Date, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .database import Base
from datetime import datetime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)

    # --- LIFETIME STATS ---
    xp = Column(Integer, default=0)
    streak = Column(Integer, default=0)

    # --- DAILY STATS (Reset Every Midnight) ---
    daily_xp = Column(Integer, default=0)
    daily_lessons = Column(Integer, default=0)
    last_active_date = Column(Date, server_default=func.current_date())

    # --- ✨ WEEKLY STATS (Reset Every Sunday) ---
    weekly_xp = Column(Integer, default=0)

    # Paper -> Iron -> Bronze -> Silver -> Gold -> Platinum -> Diamond
    league = Column(String, default="Paper")

    quests_completed = Column(Integer, default=0)

    materials = relationship("SourceMaterial", back_populates="owner")


class SourceMaterial(Base):
    __tablename__ = "source_materials"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    owner = relationship("User", back_populates="materials")
    lessons = relationship(
        "Lesson", back_populates="material", cascade="all, delete-orphan")


class Lesson(Base):
    __tablename__ = "lessons"

    id = Column(Integer, primary_key=True, index=True)
    material_id = Column(Integer, ForeignKey("source_materials.id"))
    title = Column(String, index=True)

    # --- GAMIFICATION FIELDS ---
    section_number = Column(Integer, default=1)
    unit_number = Column(Integer, default=1)
    order_in_unit = Column(Integer, default=1)
    is_completed = Column(Boolean, default=False)

    # --- RELATIONSHIPS ---
    material = relationship("SourceMaterial", back_populates="lessons")
    questions = relationship(
        "Question", back_populates="lesson", cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    lesson_id = Column(Integer, ForeignKey("lessons.id"))
    question_type = Column(String, nullable=False)

    # PostgreSQL JSONB stores our prompt, options, and answer
    content = Column(JSONB, nullable=False)

    lesson = relationship("Lesson", back_populates="questions")
