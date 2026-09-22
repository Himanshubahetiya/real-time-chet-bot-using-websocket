from sqlalchemy import Column, Integer, String, DateTime
from database import Base
from datetime import datetime
class Users(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)


class Messages(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)
    sender = Column(String)
    receiver = Column(String, nullable=True)
    message = Column(String)
    message_type = Column(String, default="text")
    created_at = Column(DateTime, default=datetime.utcnow)