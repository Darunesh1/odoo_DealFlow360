from datetime import datetime
from typing import Optional
import uuid

from pydantic import BaseModel, ConfigDict, Field


class CustomerTierBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    max_discount_percent: float
    is_active: bool = True


class CustomerTierRead(CustomerTierBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime


class CustomerTierCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    max_discount_percent: float = Field(ge=0, le=100)
    is_active: bool = True


class CustomerTierUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    max_discount_percent: Optional[float] = Field(default=None, ge=0, le=100)
    is_active: Optional[bool] = None


class CustomerBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    tier_id: uuid.UUID
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    is_active: bool = True


class CustomerRead(CustomerBase):
    id: uuid.UUID
    created_at: datetime
    updated_at: datetime
    tier: CustomerTierRead


class CustomerCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    tier_id: uuid.UUID
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    is_active: bool = True


class CustomerUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    tier_id: Optional[uuid.UUID] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    billing_address: Optional[str] = None
    is_active: Optional[bool] = None
