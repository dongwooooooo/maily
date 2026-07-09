"""Domain auto-discovery — _integration-contract.md §4.

Each `app/domains/<name>/__init__.py` exposes `router`, `JOB_HANDLERS`,
`EVENT_CONSUMERS`, `PURGE_HANDLER`. This module walks `app/domains/` at
boot, imports every domain package, and collects those four symbols so
core never needs a hand-written import+include_router line per domain.

Router prefixes are NOT part of the domain-exposed contract (§3's
prefix table is fixed, not derivable from domain code), so
`app/api/router.py` keeps a small static prefix lookup — this module
only discovers *which* domains exist and hands back their `router`.
"""

import importlib
import pkgutil
from collections.abc import Callable
from types import ModuleType

import app.domains as domains_package
from app.core.jobs.registry import DuplicateJobTypeError


def discover_domain_modules() -> list[ModuleType]:
    """Import every domain package under app/domains/ and return them."""
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
    """Merge every domain's JOB_HANDLERS. Raises DuplicateJobTypeError if
    two domains claim the same job_type — same failure mode as
    app.core.jobs.registry.register(), enforced here too so discovery
    itself fails loudly instead of silently keeping the last writer."""
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
    """Boot-time entry point: discover domains (unless a list is passed
    in for testing) and register every job handler into the real job
    registry. Returns the merged handler map for inspection/tests."""
    from app.core.jobs import registry

    if modules is None:
        modules = discover_domain_modules()
    handlers = collect_job_handlers(modules)
    for job_type, handler in handlers.items():
        registry.register(job_type, handler)
    return handlers
