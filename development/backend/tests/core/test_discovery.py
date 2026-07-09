from types import SimpleNamespace

import pytest

from app.core import discovery
from app.core.jobs import registry
from app.core.jobs.registry import DuplicateJobTypeError


@pytest.fixture(autouse=True)
def _clear_registry():
    registry.clear()
    yield
    registry.clear()


def test_discover_domain_modules_finds_all_domains() -> None:
    modules = discovery.discover_domain_modules()
    names = {discovery.domain_name(m) for m in modules}

    assert {"identity", "mail_sources", "mail_intake", "labels", "gmail_actions"} <= names


def test_collect_routers_returns_every_domain_router() -> None:
    modules = discovery.discover_domain_modules()
    routers = discovery.collect_routers(modules)

    assert {"identity", "mail_sources", "mail_intake", "labels", "gmail_actions"} <= set(
        routers.keys()
    )
    for router in routers.values():
        assert router is not None


def test_collect_job_handlers_merges_across_domains() -> None:
    modules = discovery.discover_domain_modules()
    handlers = discovery.collect_job_handlers(modules)

    expected_job_types = {
        "register_watch",
        "renew_watch",
        "process_notification",
        "poll_history",
        "sync_delta",
        "sync_full",
        "execute_action",
    }
    assert expected_job_types <= set(handlers.keys())


def test_collect_job_handlers_raises_on_duplicate_job_type() -> None:
    async def handler_a(payload: dict) -> None:
        return None

    async def handler_b(payload: dict) -> None:
        return None

    fake_module_a = SimpleNamespace(
        __name__="app.domains.fake_a", JOB_HANDLERS={"shared_job": handler_a}
    )
    fake_module_b = SimpleNamespace(
        __name__="app.domains.fake_b", JOB_HANDLERS={"shared_job": handler_b}
    )

    with pytest.raises(DuplicateJobTypeError):
        discovery.collect_job_handlers([fake_module_a, fake_module_b])


def test_collect_event_consumers_merges_lists_for_shared_event_type() -> None:
    fake_module_a = SimpleNamespace(
        __name__="app.domains.fake_a", EVENT_CONSUMERS={"shared_event": ["job_a"]}
    )
    fake_module_b = SimpleNamespace(
        __name__="app.domains.fake_b", EVENT_CONSUMERS={"shared_event": ["job_b"]}
    )

    consumers = discovery.collect_event_consumers([fake_module_a, fake_module_b])

    assert consumers["shared_event"] == ["job_a", "job_b"]


def test_collect_purge_handlers_skips_domains_without_one() -> None:
    def a_purge(source_id) -> None:
        return None

    fake_with_purge = SimpleNamespace(__name__="app.domains.fake_a", PURGE_HANDLER=a_purge)
    fake_without_purge = SimpleNamespace(__name__="app.domains.fake_b", PURGE_HANDLER=None)

    handlers = discovery.collect_purge_handlers([fake_with_purge, fake_without_purge])

    assert handlers == {"fake_a": a_purge}


def test_register_discovered_jobs_populates_the_real_registry() -> None:
    discovery.register_discovered_jobs()

    assert registry.get_handler("sync_full") is not None
    assert registry.get_handler("execute_action") is not None
    assert registry.get_handler("no_such_job_type") is None


def test_register_discovered_jobs_raises_on_duplicate_job_type() -> None:
    async def handler(payload: dict) -> None:
        return None

    fake_module_a = SimpleNamespace(
        __name__="app.domains.fake_a", JOB_HANDLERS={"dup_job": handler}
    )
    fake_module_b = SimpleNamespace(
        __name__="app.domains.fake_b", JOB_HANDLERS={"dup_job": handler}
    )

    with pytest.raises(DuplicateJobTypeError):
        discovery.register_discovered_jobs([fake_module_a, fake_module_b])
