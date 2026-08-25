"""Watchlist endpoints (authenticated, user-scoped)."""

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies.auth import CurrentUser
from app.api.deps import DbSession
from app.models import Instrument
from app.schemas.common import ApiResponse, ok
from app.schemas.heatmap_watchlist import (
    WatchlistCreateRequest,
    WatchlistItemAddRequest,
    WatchlistItemResponse,
    WatchlistItemUpdateRequest,
    WatchlistRenameRequest,
    WatchlistResponse,
)
from app.services.instrument_service import parse_uuid
from app.services.watchlist_service import WatchlistService
from sqlalchemy import select

router = APIRouter(prefix="/watchlists", tags=["watchlists"])


def _wl_response(data: dict) -> WatchlistResponse:
    return WatchlistResponse(
        id=data["id"],
        name=data["name"],
        created_at=data["created_at"],
        items=[WatchlistItemResponse.model_validate(item) for item in data["items"]],
    )


@router.get(
    "",
    response_model=ApiResponse[list[WatchlistResponse]],
    summary="List the caller's watchlists with live quotes + BOF state",
)
async def list_watchlists(user: CurrentUser, db: DbSession) -> ApiResponse[list[WatchlistResponse]]:
    data = await WatchlistService(db).list_for_user(user.id)
    return ok([_wl_response(d) for d in data])


@router.post(
    "",
    response_model=ApiResponse[WatchlistResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create a watchlist",
)
async def create_watchlist(
    payload: WatchlistCreateRequest, user: CurrentUser, db: DbSession
) -> ApiResponse[WatchlistResponse]:
    data = await WatchlistService(db).create(user.id, payload.name)
    return ok(_wl_response(data))


@router.get(
    "/{watchlist_id}",
    response_model=ApiResponse[WatchlistResponse],
    summary="Fetch one watchlist (owner only)",
)
async def get_watchlist(
    watchlist_id: str, user: CurrentUser, db: DbSession
) -> ApiResponse[WatchlistResponse]:
    data = await WatchlistService(db).get(user.id, parse_uuid(watchlist_id, "watchlist_id"))
    return ok(_wl_response(data))


@router.patch(
    "/{watchlist_id}",
    response_model=ApiResponse[WatchlistResponse],
    summary="Rename a watchlist",
)
async def rename_watchlist(
    watchlist_id: str,
    payload: WatchlistRenameRequest,
    user: CurrentUser,
    db: DbSession,
) -> ApiResponse[WatchlistResponse]:
    if not payload.name:
        from app.core.errors import ValidationError

        raise ValidationError("name is required")
    data = await WatchlistService(db).rename(user.id, parse_uuid(watchlist_id, "watchlist_id"),
                                             payload.name)
    return ok(_wl_response(data))


@router.delete(
    "/{watchlist_id}",
    response_model=ApiResponse[dict],
    summary="Delete a watchlist (items cascade)",
)
async def delete_watchlist(
    watchlist_id: str, user: CurrentUser, db: DbSession
) -> ApiResponse[dict]:
    await WatchlistService(db).delete(user.id, parse_uuid(watchlist_id, "watchlist_id"))
    return ok({"deleted": True})


@router.post(
    "/{watchlist_id}/items",
    response_model=ApiResponse[WatchlistResponse],
    summary="Add an instrument to the watchlist",
)
async def add_item(
    watchlist_id: str,
    payload: WatchlistItemAddRequest,
    user: CurrentUser,
    db: DbSession,
) -> ApiResponse[WatchlistResponse]:
    data = await WatchlistService(db).add_item(
        user.id, parse_uuid(watchlist_id, "watchlist_id"),
        payload.instrument_id, payload.alert_enabled,
    )
    return ok(_wl_response(data))


@router.patch(
    "/{watchlist_id}/items/{instrument_id}",
    response_model=ApiResponse[WatchlistResponse],
    summary="Toggle per-item alerts and/or reorder",
)
async def update_item(
    watchlist_id: str,
    instrument_id: str,
    payload: WatchlistItemUpdateRequest,
    user: CurrentUser,
    db: DbSession,
) -> ApiResponse[WatchlistResponse]:
    data = await WatchlistService(db).update_item(
        user.id,
        parse_uuid(watchlist_id, "watchlist_id"),
        parse_uuid(instrument_id, "instrument_id"),
        alert_enabled=payload.alert_enabled,
        position=payload.position,
    )
    return ok(_wl_response(data))


@router.delete(
    "/{watchlist_id}/items/{instrument_id}",
    response_model=ApiResponse[dict],
    summary="Remove an instrument from the watchlist",
)
async def remove_item(
    watchlist_id: str,
    instrument_id: str,
    user: CurrentUser,
    db: DbSession,
) -> ApiResponse[dict]:
    await WatchlistService(db).remove_item(
        user.id,
        parse_uuid(watchlist_id, "watchlist_id"),
        parse_uuid(instrument_id, "instrument_id"),
    )
    return ok({"removed": True})


_ = select, Instrument  # reserved imports
