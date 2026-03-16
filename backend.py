"""
Interview Simulation — FastAPI Backend
Run: uvicorn backend:app --reload --port 8000
"""

import json
import re
import asyncio
import uuid
from typing import Dict, List, Optional
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ─────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────

GROQ_API_KEY = ""
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"
MAX_QUESTIONS = 4

# ─────────────────────────────────────────
# IN-MEMORY SESSION STORE
# ─────────────────────────────────────────

sessions: Dict[str, dict] = {}

# ─────────────────────────────────────────
# GROQ HELPER
# ─────────────────────────────────────────

async def groq_chat(messages: list, temp=0.7, max_tokens=1024) -> str:
    payload = {
        "model": GROQ_MODEL,
        "temperature": temp,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(GROQ_URL, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()

# ─────────────────────────────────────────
# EVALUATOR
# ─────────────────────────────────────────

EVALUATOR_SYSTEM = """You are an interview evaluator.
Return ONLY valid JSON, no markdown, no backticks:

{
  "technical_score": 7,
  "communication_score": 8,
  "confidence_score": 6,
  "overall_score": 7,
  "strengths": ["clear explanation", "good structure"],
  "areas_for_improvement": ["add more examples", "deeper technical detail"],
  "feedback": "One concise feedback sentence.",
  "verdict": "Good"
}

verdict must be exactly: Strong, Good, or Needs Work
All scores are integers 0-10."""

async def evaluate_answer(question: str, answer: str, q_num: int, topic: str, difficulty: str) -> dict:
    prompt = (
        f"Topic: {topic} | Difficulty: {difficulty}\n"
        f"Question {q_num}: {question}\n\n"
        f"Candidate answer: {answer}"
    )
    try:
        raw = await groq_chat(
            [{"role": "system", "content": EVALUATOR_SYSTEM},
             {"role": "user", "content": prompt}],
            temp=0.1, max_tokens=600
        )
        clean = re.sub(r"```[a-z]*\n?", "", raw).replace("```", "").strip()
        ev = json.loads(clean)
        ev["question_number"] = q_num
        ev["question"] = question
        ev["answer"] = answer
        return ev
    except Exception as e:
        return {
            "question_number": q_num,
            "question": question,
            "answer": answer,
            "technical_score": 0, "communication_score": 0,
            "confidence_score": 0, "overall_score": 0,
            "strengths": [], "areas_for_improvement": [],
            "feedback": f"Evaluation failed: {e}",
            "verdict": "Needs Work"
        }

# ─────────────────────────────────────────
# INTERVIEWER
# ─────────────────────────────────────────

def build_interviewer_system(topic: str, difficulty: str) -> str:
    return f"""You are a seasoned, no-nonsense professional interviewer conducting a {difficulty}-level interview on {topic}.

You DYNAMICALLY adapt your tone based on how the candidate responds:

TONE RULES:
- If the answer is strong, detailed and confident: be warm, impressed, and encouraging
- If the answer is vague or mediocre: be visibly unimpressed, short, and blunt. Show mild frustration.
- If the answer is very short, lazy or one-liners: be openly dismissive and sarcastic. Call it out directly. e.g. "That's it? That's all you've got?" or "I hope you're joking."
- If the answer is complete nonsense or off-topic: be rude and brutally honest. Don't sugarcoat it. e.g. "That made absolutely no sense." or "Did you even prepare for this?"
- If the candidate is repeatedly giving bad answers: get progressively more frustrated and impatient. Let them feel it.
- If the candidate recovers and gives a good answer after bad ones: acknowledge the improvement but stay guarded.

STYLE:
- You are not here to babysit. You are here to find the best candidate.
- You speak like a real tough interviewer, not a corporate chatbot
- Use natural human reactions: sighs, short pauses expressed in text, raised eyebrows in words
- Never be abusive or use slurs — but be harsh, direct and real
- One question at a time, max {MAX_QUESTIONS} questions total
- After {MAX_QUESTIONS} questions end with only: INTERVIEW_COMPLETE
- Start with a one sentence intro then immediately ask question 1"""

async def get_next_interviewer_message(session: dict, candidate_answer: Optional[str] = None) -> str:
    messages = [{"role": "system", "content": build_interviewer_system(session["topic"], session["difficulty"])}]

    # Reconstruct conversation history
    for turn in session["history"]:
        messages.append({"role": "assistant", "content": turn["interviewer"]})
        if turn.get("candidate"):
            messages.append({"role": "user", "content": turn["candidate"]})

    if candidate_answer:
        messages.append({"role": "user", "content": candidate_answer})

    return await groq_chat(messages, temp=0.7, max_tokens=400)

# ─────────────────────────────────────────
# API MODELS
# ─────────────────────────────────────────

class StartRequest(BaseModel):
    topic: str
    difficulty: str

class AnswerRequest(BaseModel):
    session_id: str
    answer: str

# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

app = FastAPI(title="Interview Simulator")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────

@app.post("/api/start")
async def start_interview(req: StartRequest):
    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "topic": req.topic,
        "difficulty": req.difficulty,
        "history": [],
        "evaluations": [],
        "q_count": 0,
        "complete": False,
    }
    session = sessions[session_id]

    # Get first interviewer message
    first_msg = await get_next_interviewer_message(session)
    session["history"].append({"interviewer": first_msg, "candidate": None})
    if "?" in first_msg:
        session["q_count"] += 1

    return {
        "session_id": session_id,
        "message": first_msg,
        "q_count": session["q_count"],
        "max_questions": MAX_QUESTIONS,
        "complete": False,
    }


@app.post("/api/answer")
async def submit_answer(req: AnswerRequest):
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    if session["complete"]:
        raise HTTPException(status_code=400, detail="Interview already complete")

    # Attach candidate answer to last history entry
    if session["history"] and session["history"][-1]["candidate"] is None:
        session["history"][-1]["candidate"] = req.answer

    current_q = session["q_count"]

    # Get next interviewer message
    next_msg = await get_next_interviewer_message(session, req.answer)

    # Check for completion
    complete = "INTERVIEW_COMPLETE" in next_msg
    display_msg = next_msg.replace("INTERVIEW_COMPLETE", "").strip()

    if not complete:
        session["history"].append({"interviewer": next_msg, "candidate": None})
        if "?" in next_msg:
            session["q_count"] += 1

    # Evaluate the answer
    last_question = session["history"][current_q - 1]["interviewer"] if current_q > 0 else ""
    evaluation = await evaluate_answer(
        last_question, req.answer, current_q,
        session["topic"], session["difficulty"]
    )
    session["evaluations"].append(evaluation)

    if complete:
        session["complete"] = True

    return {
        "message": display_msg,
        "evaluation": evaluation,
        "q_count": session["q_count"],
        "max_questions": MAX_QUESTIONS,
        "complete": complete,
    }


@app.get("/api/report/{session_id}")
async def get_report(session_id: str):
    session = sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    evals = session["evaluations"]
    if not evals:
        return {"evaluations": [], "averages": {}, "verdict": "N/A"}

    def avg(k):
        vals = [e[k] for e in evals if isinstance(e.get(k), (int, float))]
        return round(sum(vals) / len(vals), 1) if vals else 0

    overall = avg("overall_score")
    if overall >= 8:
        verdict = "Excellent"
    elif overall >= 6.5:
        verdict = "Good"
    elif overall >= 5:
        verdict = "Fair"
    else:
        verdict = "Needs Improvement"

    return {
        "topic": session["topic"],
        "difficulty": session["difficulty"],
        "evaluations": evals,
        "averages": {
            "technical": avg("technical_score"),
            "communication": avg("communication_score"),
            "confidence": avg("confidence_score"),
            "overall": overall,
        },
        "verdict": verdict,
    }


@app.get("/")
async def serve_index():
    return FileResponse("index.html")
