from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(100), nullable=True)
    email = Column(String(100), unique=True, index=True, nullable=False)
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, server_default=func.now())

    # Relationship to history
    history_records = relationship("History", back_populates="user", cascade="all, delete-orphan")

class History(Base):
    __tablename__ = "history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    image_url = Column(Text, nullable=False)
    overlay_image_url = Column(Text, nullable=True)
    extracted_text = Column(Text(length=16777215), nullable=True)  # MediumText/LongText
    summary = Column(Text(length=16777215), nullable=True)
    upload_time = Column(DateTime, server_default=func.now())

    # Relationship to user
    user = relationship("User", back_populates="history_records")
    
    # Relationship to segmented regions
    segmented_regions = relationship("SegmentedRegion", back_populates="history", cascade="all, delete-orphan")


class SegmentedRegion(Base):
    __tablename__ = "segmented_regions"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    history_id = Column(Integer, ForeignKey("history.id", ondelete="CASCADE"), nullable=False)
    region_type = Column(String(50), nullable=False)  # "text" or "diagram"
    image_url = Column(Text, nullable=False)  # Cloudinary URL for the cropped region
    x = Column(Integer, nullable=False)
    y = Column(Integer, nullable=False)
    width = Column(Integer, nullable=False)
    height = Column(Integer, nullable=False)

    # Relationship to history
    history = relationship("History", back_populates="segmented_regions")
