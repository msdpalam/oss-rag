"""
Investor Profile router — per-user investment profile.

GET  /profile   — return current user's profile (or empty defaults)
PUT  /profile   — upsert the profile
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth import get_current_user
from core.database import get_db
from core.models import InvestorProfile, User

router = APIRouter()

VALID_GOALS = {"retirement", "growth", "income", "preservation"}
VALID_TAX_ACCOUNTS = {"401k", "roth_ira", "traditional_ira", "taxable"}
VALID_AGENTS = {"auto", "equity_analyst", "technical_trader", "macro_strategist",
                "retirement_planner", "crypto_analyst", "portfolio_strategist"}


# ── Schemas ───────────────────────────────────────────────────────────────────


class ProfileResponse(BaseModel):
    age: Optional[int]
    risk_tolerance: Optional[int]
    horizon_years: Optional[int]
    goals: List[str]
    portfolio_size_usd: Optional[int]
    monthly_contribution_usd: Optional[int]
    tax_accounts: List[str]
    preferred_agent: str
    updated_at: Optional[str]


class ProfileUpdate(BaseModel):
    age: Optional[int] = Field(None, ge=18, le=100)
    risk_tolerance: Optional[int] = Field(None, ge=1, le=5)
    horizon_years: Optional[int] = Field(None, ge=1, le=50)
    goals: Optional[List[str]] = None
    portfolio_size_usd: Optional[int] = Field(None, ge=0)
    monthly_contribution_usd: Optional[int] = Field(None, ge=0)
    tax_accounts: Optional[List[str]] = None
    preferred_agent: Optional[str] = None


def _to_response(p: InvestorProfile) -> ProfileResponse:
    return ProfileResponse(
        age=p.age,
        risk_tolerance=p.risk_tolerance,
        horizon_years=p.horizon_years,
        goals=p.goals or [],
        portfolio_size_usd=p.portfolio_size_usd,
        monthly_contribution_usd=p.monthly_contribution_usd,
        tax_accounts=p.tax_accounts or [],
        preferred_agent=p.preferred_agent or "auto",
        updated_at=p.updated_at.isoformat() if p.updated_at else None,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("", response_model=ProfileResponse)
async def get_profile(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(InvestorProfile).where(InvestorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()
    if profile is None:
        # Return empty defaults — profile not yet set
        return ProfileResponse(
            age=None,
            risk_tolerance=None,
            horizon_years=None,
            goals=[],
            portfolio_size_usd=None,
            monthly_contribution_usd=None,
            tax_accounts=[],
            preferred_agent="auto",
            updated_at=None,
        )
    return _to_response(profile)


@router.put("", response_model=ProfileResponse)
async def upsert_profile(
    body: ProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Sanitise array fields
    goals = [g for g in (body.goals or []) if g in VALID_GOALS]
    tax_accounts = [t for t in (body.tax_accounts or []) if t in VALID_TAX_ACCOUNTS]
    preferred_agent = body.preferred_agent if body.preferred_agent in VALID_AGENTS else "auto"

    result = await db.execute(
        select(InvestorProfile).where(InvestorProfile.user_id == current_user.id)
    )
    profile = result.scalar_one_or_none()

    if profile is None:
        profile = InvestorProfile(user_id=current_user.id)
        db.add(profile)

    if body.age is not None:
        profile.age = body.age
    if body.risk_tolerance is not None:
        profile.risk_tolerance = body.risk_tolerance
    if body.horizon_years is not None:
        profile.horizon_years = body.horizon_years
    if body.goals is not None:
        profile.goals = goals
    if body.portfolio_size_usd is not None:
        profile.portfolio_size_usd = body.portfolio_size_usd
    if body.monthly_contribution_usd is not None:
        profile.monthly_contribution_usd = body.monthly_contribution_usd
    if body.tax_accounts is not None:
        profile.tax_accounts = tax_accounts
    if body.preferred_agent is not None:
        profile.preferred_agent = preferred_agent

    profile.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(profile)
    return _to_response(profile)
