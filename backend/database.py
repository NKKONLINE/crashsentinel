"""
database.py — CrashSentinel
SQLAlchemy models and engine setup.
Set CRASHSENTINEL_ENV=production to use crashsentinel.db.
Default is development mode → crashsentinel_dev.db.
"""

import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Index
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

Base = declarative_base()

# ── DB Mode ───────────────────────────────────────────────────────────
ENV = os.environ.get("CRASHSENTINEL_ENV", "development")

if ENV == "production":
    DB_PATH = "crashsentinel.db"
    print("[database] Running in PRODUCTION mode → crashsentinel.db")
else:
    DB_PATH = "crashsentinel_dev.db"
    print("[database] Running in DEVELOPMENT mode → crashsentinel_dev.db (dummy DB)")

engine = create_engine(
    f"sqlite:///{DB_PATH}",
    connect_args={"check_same_thread": False},  # required for multi-threaded FastAPI
)
Session = sessionmaker(bind=engine)


# ── Models ────────────────────────────────────────────────────────────

class CrashReport(Base):
    __tablename__ = "crash_reports"
    id              = Column(Integer, primary_key=True)
    timestamp       = Column(DateTime, default=datetime.utcnow, nullable=False)
    crash_type      = Column(String, index=True)
    raw_log         = Column(Text)
    ai_explanation  = Column(Text)
    root_cause      = Column(Text)
    severity        = Column(String, index=True)     # low / medium / high / critical
    symptoms        = Column(Text)                   # JSON list
    recommendations = Column(Text)                   # JSON list
    source_os       = Column(String)                 # windows / linux / darwin
    is_simulated    = Column(Integer, default=0)     # 1 = fake/dev data


class SyslogEntry(Base):
    __tablename__ = "syslog_entries"
    id                 = Column(Integer, primary_key=True)
    timestamp          = Column(DateTime, default=datetime.utcnow, nullable=False)
    source             = Column(String)              # e.g. "linux-journald"
    source_os          = Column(String)
    level              = Column(String)              # WARN / ERROR
    message            = Column(Text)
    is_crash_precursor = Column(Integer, default=0, index=True)
    is_simulated       = Column(Integer, default=0)


class PredictionAlert(Base):
    __tablename__ = "prediction_alerts"
    id                 = Column(Integer, primary_key=True)
    timestamp          = Column(DateTime, default=datetime.utcnow, nullable=False)
    matched_symptom    = Column(Text)
    related_crash_id   = Column(Integer)
    prediction_message = Column(Text)
    confidence         = Column(Float)
    is_dismissed       = Column(Integer, default=0, index=True)
    is_simulated       = Column(Integer, default=0)


Base.metadata.create_all(engine)