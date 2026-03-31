"""
Portfolio router — per-user virtual portfolio tracker.

GET  /portfolio              — list all positions
POST /portfolio/positions    — add or upsert a position (same ticker merges)
PUT  /portfolio/positions/{id} — update shares or avg_cost
DELETE /portfolio/positions/{id} — remove a position
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.database import get_db
from core.models import PortfolioPosition, User

router = APIRouter()

VALID_ASSET_TYPES = {"stock", "etf", "crypto", "crypto_etf"}


# ── Schemas ───────────────────────────────────────────────────────────────────


class PositionOut(BaseModel):
    id: str
    ticker: str
    asset_type: str
    shares: float
    avg_cost_usd: float
    notes: Optional[str]
    added_at: str
    updated_at: str


class PositionIn(BaseModel):
    ticker: str = Field(..., min_length=1, max_length=20)
    asset_type: str = Field(default="stock")
    shares: float = Field(..., gt=0)
    avg_cost_usd: float = Field(..., ge=0)
    notes: Optional[str] = None


class PositionUpdate(BaseModel):
    shares: Optional[float] = Field(None, gt=0)
    avg_cost_usd: Optional[float] = Field(None, ge=0)
    notes: Optional[str] = None


def _to_out(p: PortfolioPosition) -> PositionOut:
    return PositionOut(
        id=str(p.id),
        ticker=p.ticker.upper(),
        asset_type=p.asset_type,
        shares=float(p.shares),
        avg_cost_usd=float(p.avg_cost_usd),
        notes=p.notes,
        added_at=p.added_at.isoformat(),
        updated_at=p.updated_at.isoformat(),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=List[PositionOut])
async def list_positions(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.user_id == current_user.id)
        .order_by(PortfolioPosition.added_at.desc())
    )
    return [_to_out(p) for p in result.scalars().all()]


@router.post("/positions", response_model=PositionOut, status_code=201)
async def add_position(
    body: PositionIn,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticker = body.ticker.strip().upper()
    asset_type = body.asset_type if body.asset_type in VALID_ASSET_TYPES else "stock"

    # Upsert: if ticker already exists for this user, update shares + avg_cost (weighted average)
    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.user_id == current_user.id)
        .where(PortfolioPosition.ticker == ticker)
    )
    existing = result.scalar_one_or_none()

    if existing:
        # Weighted average cost
        total_cost = float(existing.shares) * float(existing.avg_cost_usd) + body.shares * body.avg_cost_usd
        total_shares = float(existing.shares) + body.shares
        existing.shares = total_shares
        existing.avg_cost_usd = total_cost / total_shares
        existing.updated_at = datetime.utcnow()
        if body.notes:
            existing.notes = body.notes
        await db.commit()
        await db.refresh(existing)
        return _to_out(existing)

    pos = PortfolioPosition(
        id=uuid.uuid4(),
        user_id=current_user.id,
        ticker=ticker,
        asset_type=asset_type,
        shares=body.shares,
        avg_cost_usd=body.avg_cost_usd,
        notes=body.notes,
    )
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return _to_out(pos)


@router.put("/positions/{position_id}", response_model=PositionOut)
async def update_position(
    position_id: str,
    body: PositionUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.id == uuid.UUID(position_id))
        .where(PortfolioPosition.user_id == current_user.id)
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    if body.shares is not None:
        pos.shares = body.shares
    if body.avg_cost_usd is not None:
        pos.avg_cost_usd = body.avg_cost_usd
    if body.notes is not None:
        pos.notes = body.notes
    pos.updated_at = datetime.utcnow()

    await db.commit()
    await db.refresh(pos)
    return _to_out(pos)


@router.delete("/positions/{position_id}", status_code=204)
async def delete_position(
    position_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PortfolioPosition)
        .where(PortfolioPosition.id == uuid.UUID(position_id))
        .where(PortfolioPosition.user_id == current_user.id)
    )
    pos = result.scalar_one_or_none()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")
    await db.delete(pos)
    await db.commit()
