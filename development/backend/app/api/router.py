from fastapi import APIRouter

from app.core.discovery import collect_routers, discover_domain_modules

# docs/goals/backend-plans/_integration-contract.md §3의 router prefix.
# 새 domain을 추가할 때 아직 수동 entry가 필요한 domain별 설정은 이 표뿐이다
# (prefix는 domain 코드에서 파생할 수 없음). 그 외 항목(domain 존재 여부,
# router 객체, job handler)은 모두 자동 discovery된다. app/core/discovery.py 참고.
_PREFIX_BY_DOMAIN = {
    "identity": "/auth",
    "mail_sources": "/sources",
    "mail_intake": "/intake",
    # labels.router는 full path를 직접 선언한다(/labels, /messages/{id}/move).
    # blanket prefix가 맞지 않는 이유는 app/domains/labels/router.py 참고.
    "labels": "",
    "gmail_actions": "/actions",
    # briefing.router는 full path를 직접 선언한다(/briefing/*, /messages/{id},
    # /storage/*). _integration-contract.md §3은 이 domain에 대해 top-level path
    # group 3개를 나열하며, 위 labels와 같은 이유다.
    "briefing": "",
    # assistant_decisions.router는 full path를 직접 선언한다(/rules, /cleanup).
    # 위 labels/briefing과 같은 패턴이다.
    "assistant_decisions": "",
    "notifications": "/notifications",
}

api_router = APIRouter()
for domain, router in collect_routers(discover_domain_modules()).items():
    api_router.include_router(router, prefix=_PREFIX_BY_DOMAIN.get(domain, ""), tags=[domain])
