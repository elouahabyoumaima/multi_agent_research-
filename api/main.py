import json

from fastapi import Depends, FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from auth.database import get_db, init_db, User, ResearchHistory
from auth.schemas import SignupRequest, LoginRequest, TokenResponse, ResearchHistoryItem
from auth.security import hash_password, verify_password, create_access_token, decode_access_token
from core.orchestrator import run_research_pipeline
from pydantic import BaseModel

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


def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)) -> User:
    """Dependency: extrait et valide le JWT du header Authorization, renvoie l'utilisateur."""
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


@app.post("/auth/signup", response_model=TokenResponse)
def signup(request: SignupRequest, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == request.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="Ce nom d'utilisateur existe deja")

    user = User(username=request.username, hashed_password=hash_password(request.password))
    db.add(user)
    db.commit()

    token = create_access_token(user.username)
    return TokenResponse(access_token=token)


@app.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")

    token = create_access_token(user.username)
    return TokenResponse(access_token=token)


@app.post("/research")
def research_endpoint(
    request: ResearchRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
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