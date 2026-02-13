"""Pydantic models for request/response."""
from typing import Dict, List, Optional
from pydantic import BaseModel


class BookOdds(BaseModel):
    price: int


class MarketRequest(BaseModel):
    player: str = ''
    market_key: str = ''
    line: Optional[float] = None
    side: str = ''
    book_odds: Dict[str, BookOdds]
    opposite_odds: Optional[Dict[str, BookOdds]] = None


class FairValueRequest(BaseModel):
    markets: List[MarketRequest]


class MarketResult(BaseModel):
    player: str
    market_key: str
    line: Optional[float]
    side: str
    fair_probability: float
    fair_odds: int
    calc_type: str
    best_book: str
    best_odds: int
    edge_pct: float
    kelly_fraction: float
    coverage: int
    confidence_multiplier: float


class FairValueResponse(BaseModel):
    results: List[MarketResult]


class HealthResponse(BaseModel):
    status: str
    version: str
