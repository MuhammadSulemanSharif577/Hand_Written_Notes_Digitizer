from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class UserCreate(BaseModel):
    full_name: str
    email: str
    password: str

class UserLogin(BaseModel):
    email: str
    password: str

class UserResponse(BaseModel):
    id: int
    full_name: Optional[str] = None
    email: str
    created_at: datetime

    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    user_id: Optional[int] = None

class SegmentedRegionResponse(BaseModel):
    id: int
    history_id: int
    region_type: str
    image_url: str
    x: int
    y: int
    width: int
    height: int

    class Config:
        from_attributes = True

class HistoryResponse(BaseModel):
    id: int
    user_id: int
    image_url: str
    overlay_image_url: Optional[str] = None
    extracted_text: Optional[str] = None
    summary: Optional[str] = None
    upload_time: datetime
    segmented_regions: list[SegmentedRegionResponse] = []

    class Config:
        from_attributes = True
