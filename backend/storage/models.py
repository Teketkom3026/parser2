"""Pydantic-модели данных."""
from typing import Optional
from pydantic import BaseModel, Field


class TaskCreate(BaseModel):
    mode: str = Field(..., pattern="^(mode_1|mode_2|quick_start)$")
    positions: list[str] = Field(default_factory=list)


class TaskResponse(BaseModel):
    task_id: str
    status: str
    mode: str
    total_urls: int = 0
    processed_urls: int = 0
    found_contacts: int = 0
    errors_count: int = 0
    created_at: Optional[str] = None
    output_file: Optional[str] = None


class QuickStartRequest(BaseModel):
    url: str
    positions: list[str] = Field(default_factory=list)
    mode: str = Field(default="mode_2", pattern="^(mode_1|mode_2)$")


class ContactOut(BaseModel):
    company_name: str = ""
    site_url: str = ""
    company_email: str = ""
    company_phone: str = ""
    person_name: str = ""
    last_name: str = ""
    first_name: str = ""
    patronymic: str = ""
    initials: str = ""
    position_raw: str = ""
    position_norm: str = ""
    role_category: str = ""
    person_email: str = ""
    person_phone: str = ""
    inn: str = ""
    kpp: str = ""
    social_links: str = ""
    page_url: str = ""
    page_language: str = ""
    scan_date: str = ""
    status: str = "OK"
    comment: str = ""


class BlacklistUploadResponse(BaseModel):
    entries_added: int
    total_entries: int


class ProgressMessage(BaseModel):
    task_id: str
    status: str
    processed: int
    total: int
    found_contacts: int
    errors: int
    current_url: str = ""
    message: str = ""
