import json
import time
from datetime import datetime, timedelta

from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.database import get_db, init_db, User, ResearchHistory
from auth.schemas import (
    SignupRequest, LoginRequest, TokenResponse, ResearchHistoryItem, VerifyRequest,
)
from auth.security import (
    hash_password, verify_password, create_access_token, decode_access_token,
    generate_verification_code, is_code_expired,
)
from auth.email_sender import send_verification_email
from agents.autonomous import run_agent
from agents.followup import answer_followup, MAX_QUESTION_CHARS
from core.orchestrator import run_research_pipeline

app = FastAPI(title="Multi-Agent Research Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    init_db()


class ResearchRequest(BaseModel):
    question: str


class ResendRequest(BaseModel):
    email: str


class FollowupRequest(BaseModel):
    question: str
    report: str
    original_question: str = ""
    history: list[dict] = []   # [{"q": "...", "a": "..."}]
    use_web: bool = False


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token manquant")

    token = authorization.split(" ")[1]
    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=401, detail="Token invalide ou expire")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=401, detail="Utilisateur introuvable")
    return user


@app.post("/auth/signup")
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    if request.password != request.password_confirm:
        raise HTTPException(status_code=400, detail="Les mots de passe ne correspondent pas")

    if db.query(User).filter(User.username == request.username).first():
        raise HTTPException(status_code=400, detail="Ce nom d'utilisateur existe deja")

    if db.query(User).filter(User.email == request.email).first():
        raise HTTPException(status_code=400, detail="Cet email est deja utilise")

    code = generate_verification_code()
    user = User(
        username=request.username,
        email=request.email,
        phone=request.phone,
        hashed_password=hash_password(request.password),
        is_verified=False,
        verification_code=code,
        verification_code_expiry=datetime.utcnow() + timedelta(minutes=10),
    )
    db.add(user)
    db.commit()

    email_sent = send_verification_email(request.email, code)

    return {
        "message": "Compte cree. Verifiez votre email pour activer le compte.",
        "email_sent": email_sent,
    }


@app.post("/auth/verify", response_model=TokenResponse)
def verify_email(request: VerifyRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")

    if user.is_verified:
        raise HTTPException(status_code=400, detail="Compte deja verifie")

    if is_code_expired(user.verification_code_expiry):
        raise HTTPException(status_code=400, detail="Code expire, demandez un nouveau code")

    if user.verification_code != request.code.strip():
        raise HTTPException(status_code=400, detail="Code incorrect")

    user.is_verified = True
    user.verification_code = None
    user.verification_code_expiry = None
    db.commit()

    return TokenResponse(access_token=create_access_token(user.username))


@app.post("/auth/resend")
def resend_code(request: ResendRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == request.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="Utilisateur introuvable")
    if user.is_verified:
        raise HTTPException(status_code=400, detail="Compte deja verifie")

    code = generate_verification_code()
    user.verification_code = code
    user.verification_code_expiry = datetime.utcnow() + timedelta(minutes=10)
    db.commit()

    return {"email_sent": send_verification_email(user.email, code)}


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    if not user.is_verified:
        raise HTTPException(status_code=403, detail="Compte non verifie. Verifiez votre email.")

    return TokenResponse(access_token=create_access_token(user.username))


@app.post("/research")
def research_endpoint(
    request: ResearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # agent autonome; si il plante completement, on retombe sur le pipeline fixe
    try:
        result = run_agent(request.question)
    except Exception:
        result = run_research_pipeline(request.question)

    history_item = ResearchHistory(
        user_id=current_user.id,
        question=result["question"],
        report=result["report"],
        sources=json.dumps(result["sources"]),
        duration_seconds=int(result["duration_seconds"]),
    )
    db.add(history_item)
    db.commit()

    return result


@app.post("/followup")
def followup_endpoint(request: FollowupRequest, current_user: User = Depends(get_current_user)):
    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question vide")
    if len(question) > MAX_QUESTION_CHARS:
        raise HTTPException(status_code=400, detail="Question trop longue")

    start = time.time()
    if request.use_web:
        context = (
            "Contexte : recherche precedente sur \u00ab " + request.original_question[:300] + " \u00bb. "
            "Question de suivi : " + question
        )
        result = run_agent(context)
        return {
            "answer": result["report"],
            "sources": result["sources"],
            "steps": result["steps"],
            "duration_seconds": round(time.time() - start, 1),
        }

    try:
        answer = answer_followup(question, request.report, request.history)
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"answer": answer, "sources": [], "steps": [], "duration_seconds": round(time.time() - start, 1)}


@app.get("/history", response_model=list[ResearchHistoryItem])
def get_history(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = (
        db.query(ResearchHistory)
        .filter(ResearchHistory.user_id == current_user.id)
        .order_by(ResearchHistory.created_at.desc())
        .all()
    )
    return [
        ResearchHistoryItem(
            id=item.id,
            question=item.question,
            report=item.report,
            sources=json.loads(item.sources or "[]"),
            duration_seconds=item.duration_seconds,
            created_at=item.created_at.isoformat(),
        )
        for item in items
    ]


@app.get("/health")
def health():
    return {"status": "ok"}