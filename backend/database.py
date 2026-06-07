from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

Base = declarative_base()
engine = create_engine("sqlite:///crashsentinel.db")
Session = sessionmaker(bind=engine)

class CrashReport(Base):
    __tablename__ = "crash_reports"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    crash_type = Column(String)
    raw_log = Column(Text)
    ai_explanation = Column(Text)
    root_cause = Column(Text)
    severity = Column(String)
    symptoms = Column(Text)

class SyslogEntry(Base):
    __tablename__ = "syslog_entries"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime)
    source = Column(String)
    level = Column(String)
    message = Column(Text)
    is_crash_precursor = Column(Integer, default=0)

class PredictionAlert(Base):
    __tablename__ = "prediction_alerts"
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    matched_symptom = Column(Text)
    related_crash_id = Column(Integer)
    prediction_message = Column(Text)
    confidence = Column(Float)
    is_dismissed = Column(Integer, default=0)

Base.metadata.create_all(engine)
print("Database created successfully!")