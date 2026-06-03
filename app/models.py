from pydantic import BaseModel, Field
from typing import Literal, Optional


class PublicChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    session_id: Optional[str] = None
    visitor_name: Optional[str] = Field(default=None, max_length=120)
    visitor_email: Optional[str] = Field(default=None, max_length=254)
    llm_mode: Literal["api"] = "api"


class ChatResponse(BaseModel):
    answer: str
    confidence: float
    action: Literal["answered", "handoff", "clarify"]
    est_cost_usd: float
    llm_source: Optional[str] = None
    sources_used: int = 0
    session_id: Optional[str] = None
    booking_url: Optional[str] = None
    contact_email: Optional[str] = None
    proposal_hint: Optional[str] = None


class KnowledgeTextRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=50000)
    category: str = Field(default="infigo", max_length=64)


class RetrievalChunk(BaseModel):
    id: str
    source: str
    text: str
    score: float
