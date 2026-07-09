from fastapi import APIRouter

from app.core.discovery import collect_routers, discover_domain_modules

# Router prefixes per docs/goals/backend-plans/_integration-contract.md §3 —
# this table is the one piece of per-domain config that still needs a manual
# entry when a new domain is added (prefixes aren't derivable from domain
# code). Everything else (which domains exist, their router object, their
# job handlers) is discovered automatically — see app/core/discovery.py.
_PREFIX_BY_DOMAIN = {
    "identity": "/auth",
    "mail_sources": "/sources",
    "mail_intake": "/intake",
    # labels.router declares full paths itself (/labels, /messages/{id}/move) —
    # see app/domains/labels/router.py for why a blanket prefix doesn't fit.
    "labels": "",
    "gmail_actions": "/actions",
    # briefing.router declares full paths itself (/briefing/*, /messages/{id},
    # /storage/*) — _integration-contract.md §3 lists three top-level path
    # groups for this domain, same reasoning as labels above.
    "briefing": "",
}

api_router = APIRouter()
for domain, router in collect_routers(discover_domain_modules()).items():
    api_router.include_router(router, prefix=_PREFIX_BY_DOMAIN.get(domain, ""), tags=[domain])
