from collections.abc import Awaitable, Callable

JobHandler = Callable[[dict], Awaitable[None]]

_handlers: dict[str, JobHandler] = {}


class DuplicateJobTypeError(Exception):
    pass


def register(job_type: str, handler: JobHandler) -> None:
    if job_type in _handlers:
        raise DuplicateJobTypeError(job_type)
    _handlers[job_type] = handler


def get_handler(job_type: str) -> JobHandler | None:
    return _handlers.get(job_type)


def clear() -> None:
    _handlers.clear()
