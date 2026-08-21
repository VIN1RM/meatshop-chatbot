"""Rate limit por chave com janela deslizante em memória.

Limitações conhecidas, assumidas de propósito para manter o serviço sem dependências
externas:

- o contador vive no processo. Com mais de uma instância no Render, cada uma conta
  separado e o limite efetivo é multiplicado pelo número de instâncias;
- a chave vem do IP informado pelo proxy, que o cliente pode forjar rotacionando
  `X-Forwarded-For`. Isso barra o abuso ingênuo (laço de `curl`), não um atacante
  dedicado — para esse caso o lugar do limite é na borda (WAF/CDN).

Migrar o contador para Redis resolve o primeiro item quando houver escala horizontal.
"""

import time
from collections import deque
from collections.abc import Callable

# Varre chaves ociosas a cada N verificações, para a memória não crescer com IPs distintos.
_PURGE_EVERY = 1000


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._checks = 0

    def check(self, key: str) -> float | None:
        """Registra um acesso.

        Devolve `None` se permitido, ou os segundos restantes até liberar.
        """
        now = self._clock()
        self._checks += 1
        if self._checks % _PURGE_EVERY == 0:
            self._purge(now)

        hits = self._hits.setdefault(key, deque())
        self._prune(hits, now)

        if len(hits) >= self.max_requests:
            return self.window_seconds - (now - hits[0])

        hits.append(now)
        return None

    def _prune(self, hits: deque[float], now: float) -> None:
        limite = now - self.window_seconds
        while hits and hits[0] <= limite:
            hits.popleft()

    def _purge(self, now: float) -> None:
        for key in list(self._hits):
            self._prune(self._hits[key], now)
            if not self._hits[key]:
                del self._hits[key]

    def reset(self) -> None:
        self._hits.clear()
        self._checks = 0
