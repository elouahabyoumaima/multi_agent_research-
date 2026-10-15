import os
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Text, ForeignKey, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, relationship

load_dotenv()  # lit .env AVANT de lire DATABASE_URL

# En local: SQLite. En cloud / Docker: PostgreSQL via la variable d'environnement DATABASE_URL.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./research_app.db")

# certains hebergeurs donnent "postgres://..." ou "postgresql://...": on force le driver psycopg2
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    phone = Column(String, nullable=True)
    hashed_password = Column(String, nullable=False)
    is_verified = Column(Boolean, default=False)
    verification_code = Column(String, nullable=True)
    verification_code_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    research_items = relationship("ResearchHistory", back_populates="owner")

class ResearchHistory(Base):
    __tablename__ = "research_history"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    question = Column(Text, nullable=False)
    report = Column(Text, nullable=False)
    sources = Column(Text)  # JSON serialise en texte
    duration_seconds = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="research_items")


def init_db():
    """Cree les tables si elles n'existent pas encore."""
    Base.metadata.create_all(bind=engine)


def get_db():
    """Fournit une session DB, utilisable comme dependency FastAPI."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()