"""domain 자동 discovery — _integration-contract.md §4.

각 `app/domains/<name>/__init__.py`는 `router`, `JOB_HANDLERS`,
`EVENT_CONSUMERS`, `PURGE_HANDLER`를 expose한다. 이 module은 boot 시점에
`app/domains/`를 순회하고 모든 domain package를 import한 뒤, 이 네 symbol을
수집한다. 그래서 core가 domain마다 손으로 import+include_router line을 둘 필요가 없다.

Router prefix는 domain-exposed contract의 일부가 아니다(§3의 prefix table은 고정이며
domain 코드에서 파생할 수 없음). 따라서 `app/api/router.py`가 작은 static prefix lookup을
유지한다. 이 module은 *어떤* domain이 존재하는지만 discovery하고 해당 `router`를 돌려준다.
"""

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType

import app.domains as domains_package
from app.core.jobs.registry import DuplicateJobTypeError


def discover_domain_modules() -> list[ModuleType]:
    """app/domains/ 아래 모든 domain package를 import해 반환한다."""
    modules = []
    for module_info in pkgutil.iter_modules(domains_package.__path__):
        if module_info.ispkg:
            modules.append(importlib.import_module(f"app.domains.{module_info.name}"))
    return modules


def domain_name(module: ModuleType) -> str:
    return module.__name__.rsplit(".", 1)[-1]


def collect_routers(modules: list[ModuleType]) -> dict[str, object]:
    return {
        domain_name(module): module.router
        for module in modules
        if getattr(module, "router", None) is not None
    }


def collect_job_handlers(modules: list[ModuleType]) -> dict[str, Callable]:
    """모든 domain의 JOB_HANDLERS를 merge한다.

    두 domain이 같은 job_type을 claim하면 DuplicateJobTypeError를 발생시킨다.
    app.core.jobs.registry.register()와 같은 failure mode를 여기서도 강제해,
    discovery 자체가 마지막 writer를 조용히 유지하지 않고 명확히 실패하게 한다.
    """
    handlers: dict[str, Callable] = {}
    for module in modules:
        for job_type, handler in getattr(module, "JOB_HANDLERS", {}).items():
            if job_type in handlers:
                raise DuplicateJobTypeError(job_type)
            handlers[job_type] = handler
    return handlers


def collect_event_consumers(modules: list[ModuleType]) -> dict[str, list[str]]:
    consumers: dict[str, list[str]] = {}
    for module in modules:
        for event_type, job_types in getattr(module, "EVENT_CONSUMERS", {}).items():
            consumers.setdefault(event_type, []).extend(job_types)
    return consumers


def collect_purge_handlers(modules: list[ModuleType]) -> dict[str, Callable]:
    return {
        domain_name(module): module.PURGE_HANDLER
        for module in modules
        if getattr(module, "PURGE_HANDLER", None) is not None
    }


def register_discovered_jobs(modules: list[ModuleType] | None = None) -> dict[str, Callable]:
    """boot-time 진입점.

    test용 list가 전달되지 않으면 domain을 discovery하고 모든 job handler를 실제 job
    registry에 등록한다. inspection/test용으로 merged handler map을 반환한다.
    """
    from app.core.jobs import registry

    if modules is None:
        modules = discover_domain_modules()
    handlers = collect_job_handlers(modules)
    for job_type, handler in handlers.items():
        registry.register(job_type, handler)
    return handlers
