from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, index=True)
    ticker = Column(String, index=True)
    signal = Column(String)  # BUY, HOLD, SELL
    confidence = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    price_at_signal = Column(Float, nullable=True)   # stock price when signal created
    composite_score = Column(Float, nullable=True)    # raw composite score -1.0 to +1.0