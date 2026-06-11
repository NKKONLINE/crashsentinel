import os
from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()

# ── DB Mode ──────────────────────────────────────────────────────────
# Set ENV variable CRASHSENTINEL_ENV=production to use the real DB.
# In dev mode (default), uses crashsentinel_dev.db so real data is never touched.
ENV = os.environ.get("CRASHSENTINEL_ENV", "development")

if ENV == "production":
    DB_PATH = "crashsentinel.db"
    print("[database] Running in PRODUCTION mode → crashsentinel.db")
else:
    DB_PATH = "crashsentinel_dev.db"
    print("[database] Running in DEVELOPMENT mode → crashsentinel_dev.db (dummy DB)")

engine = create_engine(f"sqlite:///{DB_PATH}")
Session = sessionmaker(bind=engine)


# ── Models ───────────────────────────────────────────────────────────

class CrashReport(Base):
    __tablename__ = "crash_reports"
    id               = Column(Integer, primary_key=True)
    timestamp        = Column(DateTime, default=datetime.utcnow)
    crash_type       = Column(String)
    raw_log          = Column(Text)
    ai_explanation   = Column(Text)
    root_cause       = Column(Text)
    severity         = Column(String)
    symptoms         = Column(Text)                    # JSON list
    recommendations  = Column(Text)                    # JSON list — was missing before
    source_os        = Column(String)                  # "windows" / "linux" / "darwin"
    is_simulated     = Column(Integer, default=0)      # 1 = came from fake/dev data


class SyslogEntry(Base):
    __tablename__ = "syslog_entries"
    id                  = Column(Integer, primary_key=True)
    timestamp           = Column(DateTime)
    source              = Column(String)               # e.g. "windows-eventlog", "linux-journald"
    source_os           = Column(String)               # "windows" / "linux" / "darwin"
    level               = Column(String)               # "WARN" / "ERROR"
    message             = Column(Text)
    is_crash_precursor  = Column(Integer, default=0)
    is_simulated        = Column(Integer, default=0)   # 1 = fake data


class PredictionAlert(Base):
    __tablename__ = "prediction_alerts"
    id                  = Column(Integer, primary_key=True)
    timestamp           = Column(DateTime, default=datetime.utcnow)
    matched_symptom     = Column(Text)
    related_crash_id    = Column(Integer)
    prediction_message  = Column(Text)
    confidence          = Column(Float)
    is_dismissed        = Column(Integer, default=0)
    is_simulated        = Column(Integer, default=0)   # 1 = came from simulated log scan


Base.metadata.create_all(engine)