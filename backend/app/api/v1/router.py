from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    auth,
    dashboard,
    health,
    heatmap,
    instruments,
    notifications,
    profile,
    settings,
    signals,
    watchlists,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(settings.router)
api_router.include_router(instruments.router)    # Phase 2
api_router.include_router(dashboard.router)      # Phase 2
api_router.include_router(signals.router)        # Phase 3
api_router.include_router(heatmap.router)        # Phase 5
api_router.include_router(watchlists.router)     # Phase 5
api_router.include_router(notifications.router)  # Phase 6
api_router.include_router(admin.router)          # Phase 7 — ADMIN ONLY

# Registered in later phases (kept here so the route map is visible early):
#   signals      â€” Phase 3
#   watchlists   â€” Phase 5
#   heatmap      â€” Phase 5
#   notificationsâ€” Phase 6

