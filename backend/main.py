import os
import json
import re
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Depends, HTTPException
from fastapi.responses import FileResponse, RedirectResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.orm import Session
from google import genai
from dotenv import load_dotenv

# APScheduler Imports
from apscheduler.schedulers.background import BackgroundScheduler

# Absolute imports based on your project structure
from backend.database import engine, get_db
from backend import models
from backend.routers import upload, lessons, auth, users

# Import the reset function
from backend.weekly_reset import process_weekly_shuffle

# Load environment variables (API keys)
load_dotenv()

# Initialize the modern Gemini Client
client = genai.Client()

# 1. Automatically create/sync database tables
models.Base.metadata.create_all(bind=engine)


# ==========================================
# ⏰ LIFESPAN & SCHEDULER SETUP
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP LOGIC ---
    scheduler = BackgroundScheduler()

    # Schedule the job to run every Sunday at 11:59 PM (23:59)
    scheduler.add_job(
        process_weekly_shuffle,
        'cron',
        day_of_week='sun',
        hour=23,
        minute=59,
        id='weekly_league_reset',
        replace_existing=True
    )

    scheduler.start()
    print("⏰ Background Scheduler Started: Weekly reset queued for Sunday 11:59 PM.")

    yield  # This tells FastAPI to start serving web traffic now

    # --- SHUTDOWN LOGIC ---
    scheduler.shutdown()
    print("🛑 Background Scheduler Stopped.")


# 2. Initialize the FastAPI app (Now with the lifespan attached!)
app = FastAPI(
    title="Promitheus API",
    description="The backend engine for turning lectures into interactive lessons.",
    version="1.0.0",
    lifespan=lifespan  # ✨ ADDED THIS LINE
)


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serves the browser tab icon to prevent 404 errors."""
    return FileResponse("frontend/static/assets/favicon.ico")

# 3. Setup CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Mount Static Files (CSS, JS, Images)
app.mount("/static", StaticFiles(directory="frontend/static"), name="static")

# 5. Setup HTML Templates
templates = Jinja2Templates(directory="frontend/templates")

# 6. Register API routes
app.include_router(auth.router)
app.include_router(upload.router)
app.include_router(lessons.router)
app.include_router(users.router)


# ==========================================
# 🧠 AI GRADING ENDPOINT
# ==========================================

class GradingRequest(BaseModel):
    question: str
    student_answer: str
    ideal_answer: str = ""


@app.post("/api/grade-answer")
async def grade_student_answer(request: GradingRequest):
    try:
        prompt = f"""
        You are an expert teacher grading a student's short answer.
        Determine if the student's answer is correct based on the question.
        Be fair but accurate. Minor typos are fine if the core concept is right.
        
        You MUST respond ONLY with a valid JSON object matching this exact format:
        {{
            "is_correct": true,
            "feedback": "1 to 2 short sentences explaining why it is correct or incorrect."
        }}

        Question: {request.question}
        Ideal Answer (Reference): {request.ideal_answer}
        Student's Answer: {request.student_answer}
        """

        response = client.models.generate_content(
            model='gemini-3-flash-preview',
            contents=prompt,
        )

        raw_text = response.text.strip()
        json_match = re.search(r'\{.*\}', raw_text, re.DOTALL)
        clean_json_str = json_match.group(0) if json_match else raw_text

        return json.loads(clean_json_str)

    except Exception as e:
        print(f"AI Grading Error: {str(e)}")
        raise HTTPException(
            status_code=500, detail="Failed to grade answer via AI")


# ==========================================
# 🌐 WEB FRONTEND ROUTES
# ==========================================

@app.get("/")
async def serve_dashboard(request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user}
    )


@app.get("/dashboard")
async def dashboard_alias(request: Request, db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"user": user}
    )


@app.get("/quiz/{lesson_id}")
async def serve_quiz(request: Request, lesson_id: int, db: Session = Depends(get_db)):
    user = db.query(models.User).first()
    return templates.TemplateResponse(
        request,
        "quiz.html",
        {
            "lesson_id": lesson_id,
            "user": user
        }
    )


@app.get("/quests")
async def quests_page(request: Request):
    return templates.TemplateResponse(request=request, name="quests.html")


@app.get("/streaks")
async def streaks_page(request: Request):
    return templates.TemplateResponse(request=request, name="streaks.html")


@app.get("/login")
async def serve_login(request: Request):
    return templates.TemplateResponse(
        request,
        "login.html",
        {"user": None}
    )


@app.get("/profile", response_class=HTMLResponse)
async def get_profile_page(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="profile.html",
        context={"request": request}
    )
