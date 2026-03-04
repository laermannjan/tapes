import logging
from collections import defaultdict
from typing import Callable

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._listeners: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event: str, handler: Callable) -> None:
        self._listeners[event].append(handler)

    def emit(self, event: str, **kwargs) -> None:
        for handler in self._listeners[event]:
            try:
                handler(**kwargs)
            except Exception as e:
                logger.error(
                    "EventBus: handler %s raised %s on event '%s': %s",
                    getattr(handler, "__name__", repr(handler)),
                    type(e).__name__,
                    event,
                    e,
                )
