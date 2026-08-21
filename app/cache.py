"""Cache de respostas em memória com TTL e descarte do menos usado.

Perguntas repetidas ("como fazer picanha") são a maior parte do tráfego de um chatbot
de domínio fechado, e cada repetição custa uma chamada de IA. O cache vale só para
perguntas sem histórico — com histórico a chance de repetição exata é praticamente nula.

Assim como o rate limit, o estado é por processo: com várias instâncias cada uma mantém
o seu cache. Isso reduz a taxa de acerto, não a correção.
"""

import time
from collections import OrderedDict
from collections.abc import Callable


class TTLCache:
    def __init__(
        self,
        ttl_seconds: float,
        max_entries: int,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._clock = clock
        self._entries: OrderedDict[str, tuple[float, str]] = OrderedDict()

    @property
    def enabled(self) -> bool:
        return self.ttl_seconds > 0 and self.max_entries > 0

    def get(self, key: str) -> str | None:
        if not self.enabled:
            return None

        entry = self._entries.get(key)
        if entry is None:
            return None

        expira_em, value = entry
        if self._clock() >= expira_em:
            del self._entries[key]
            return None

        self._entries.move_to_end(key)
        return value

    def set(self, key: str, value: str) -> None:
        if not self.enabled:
            return

        self._entries[key] = (self._clock() + self.ttl_seconds, value)
        self._entries.move_to_end(key)
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)

    def clear(self) -> None:
        self._entries.clear()
