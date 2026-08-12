from sqlalchemy import Column, Integer, String
from database import Base
from sqlalchemy import Integer

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from datetime import datetime

class Video(Base):
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True, index=True)

    original_filename = Column(String)
    stored_filename = Column(String)

    thumbnail = Column(String)

    cloudinary_video_url = Column(String, nullable=True)
    cloudinary_thumbnail_url = Column(String, nullable=True)

    owner_id = Column(Integer, ForeignKey("users.id"))

    uploaded_at = Column(DateTime, default=datetime.utcnow)

    expires_at = Column(DateTime)

    views = Column(Integer, default=0)
    cloudinary_public_id = Column(String, nullable=True)