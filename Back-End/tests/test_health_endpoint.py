import asyncio
import inspect

from app.main import health


def test_health_endpoint_is_non_blocking() -> None:
    assert inspect.iscoroutinefunction(health)
    assert asyncio.run(health()) == {"status": "ok"}
