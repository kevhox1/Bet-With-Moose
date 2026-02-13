"""
FastAPI fair value calculation microservice for Moose Bets.
"""
from fastapi import FastAPI
from models.schemas import FairValueRequest, FairValueResponse, HealthResponse, MarketResult
from services.market import process_market

app = FastAPI(title="Moose Bets Calculator", version="1.0.0")


@app.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "version": "1.0.0"}


@app.post("/v1/fair-value")
def fair_value(request: FairValueRequest):
    results = {}
    for i, market in enumerate(request.markets):
        # Convert Pydantic models to plain dicts for processing
        book_odds = {k: {"price": v.price} for k, v in market.book_odds.items()}
        opposite_odds = None
        if market.opposite_odds:
            opposite_odds = {k: {"price": v.price} for k, v in market.opposite_odds.items()}

        market_dict = {
            "player": market.player,
            "market_key": market.market_key,
            "line": market.line,
            "side": market.side,
            "book_odds": book_odds,
            "opposite_odds": opposite_odds,
        }
        result = process_market(market_dict)
        # Key by index so the caller (Node server) can map back via keyMap
        results[str(i)] = result

    return {"results": results}
