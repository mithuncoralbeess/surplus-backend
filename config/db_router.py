"""
Database Load Balancer & Automatic Failover Router for Surplus Market.
Supports:
- Primary + Multiple Read-Replica load balancing (Round-Robin across healthy read nodes)
- Per-database Circuit Breaker (auto-isolates unhealthy DB nodes for 20s cooldown)
- Automatic read/write failover to healthy replicas or fallback database when primary experiences transient outage
"""

import time
import threading
import logging
from django.conf import settings
from django.db import connections, OperationalError, InterfaceError

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_rr_counter = 0

# Circuit breaker state per DB alias: { alias: {"failures": int, "open_until": float, "last_error": str, "latency_ms": float} }
_db_health_state = {}

FAILURE_THRESHOLD = 2
COOLDOWN_SECONDS = 20.0


def _ensure_alias_state(alias: str) -> dict:
    if alias not in _db_health_state:
        _db_health_state[alias] = {
            "failures": 0,
            "open_until": 0.0,
            "last_error": None,
            "latency_ms": 0.0,
            "total_routed": 0,
        }
    return _db_health_state[alias]


def mark_db_failure(alias: str, error: Exception | str) -> None:
    with _lock:
        state = _ensure_alias_state(alias)
        state["failures"] += 1
        state["last_error"] = str(error)
        if state["failures"] >= FAILURE_THRESHOLD:
            state["open_until"] = time.time() + COOLDOWN_SECONDS
            logger.warning(
                f"[DB Failover Router] Circuit OPEN for database '{alias}' for {COOLDOWN_SECONDS}s: {error}"
            )


def mark_db_success(alias: str, latency_ms: float = 0.0) -> None:
    with _lock:
        state = _ensure_alias_state(alias)
        state["failures"] = 0
        state["open_until"] = 0.0
        state["last_error"] = None
        if latency_ms > 0:
            state["latency_ms"] = round(latency_ms, 2)


def is_db_circuit_closed(alias: str) -> bool:
    with _lock:
        state = _ensure_alias_state(alias)
        if state["open_until"] <= 0:
            return True
        if time.time() >= state["open_until"]:
            # Cooldown elapsed -> allow HALF_OPEN probe
            return True
        return False


def probe_db_alias(alias: str) -> bool:
    """
    Lightweight connection probe (`SELECT 1`) with circuit breaker state update.
    """
    if alias not in settings.DATABASES:
        return False
    start = time.perf_counter()
    try:
        conn = connections[alias]
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1;")
            cursor.fetchone()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        mark_db_success(alias, elapsed_ms)
        return True
    except (OperationalError, InterfaceError, Exception) as exc:
        try:
            connections[alias].close()
        except Exception:
            pass
        mark_db_failure(alias, exc)
        return False


def get_db_cluster_status() -> dict:
    """
    Returns real-time health, latency, and circuit-breaker status for all configured database nodes.
    """
    configured_aliases = list(settings.DATABASES.keys())
    nodes = {}
    for alias in configured_aliases:
        ok = probe_db_alias(alias)
        state = _ensure_alias_state(alias)
        nodes[alias] = {
            "role": "primary" if alias == "default" else ("fallback" if "fallback" in alias else "read_replica"),
            "status": "healthy" if ok else "unavailable",
            "circuit": "CLOSED" if is_db_circuit_closed(alias) else "OPEN",
            "latency_ms": state.get("latency_ms", 0.0),
            "consecutive_failures": state.get("failures", 0),
            "total_routed": state.get("total_routed", 0),
            "last_error": state.get("last_error"),
            "vendor": connections[alias].vendor if alias in connections else "unknown",
        }
    return {
        "total_nodes": len(configured_aliases),
        "healthy_nodes": sum(1 for n in nodes.values() if n["status"] == "healthy"),
        "nodes": nodes,
    }


class PrimaryReplicaFailoverRouter:
    """
    Django Database Router implementing:
    1. Round-robin read load balancing across healthy read replicas ('replica_*') and 'default'.
    2. Automatic failover if a replica or primary circuit is OPEN.
    """

    def _get_read_candidates(self) -> list[str]:
        all_dbs = list(settings.DATABASES.keys())
        replicas = [k for k in all_dbs if k.startswith("replica")]
        candidates = replicas + ["default"]
        if "fallback" in all_dbs:
            candidates.append("fallback")
        return candidates

    def db_for_read(self, model, **hints) -> str:
        global _rr_counter
        candidates = self._get_read_candidates()
        if len(candidates) <= 1:
            with _lock:
                _ensure_alias_state("default")["total_routed"] += 1
            return "default"

        healthy_replicas = [
            alias for alias in candidates
            if alias != "fallback" and is_db_circuit_closed(alias)
        ]

        if healthy_replicas:
            with _lock:
                idx = _rr_counter % len(healthy_replicas)
                _rr_counter += 1
                chosen = healthy_replicas[idx]
                _ensure_alias_state(chosen)["total_routed"] += 1
            return chosen

        if "fallback" in candidates and is_db_circuit_closed("fallback"):
            with _lock:
                _ensure_alias_state("fallback")["total_routed"] += 1
            return "fallback"

        return "default"

    def db_for_write(self, model, **hints) -> str:
        if is_db_circuit_closed("default"):
            with _lock:
                _ensure_alias_state("default")["total_routed"] += 1
            return "default"

        if "fallback" in settings.DATABASES and is_db_circuit_closed("fallback"):
            with _lock:
                _ensure_alias_state("fallback")["total_routed"] += 1
            return "fallback"

        return "default"

    def allow_relation(self, obj1, obj2, **hints) -> bool:
        return True

    def allow_migrate(self, db, app_label, model_name=None, **hints) -> bool:
        return db in ("default", "fallback")

