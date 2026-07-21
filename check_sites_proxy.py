"""Quick site checker with proxy support — tests all Shopify stores.
Uses rotating proxies from Alive-proxy.txt for DNS bypass.
"""

import asyncio
import aiohttp
import csv
import time
import random
import os
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn

console = Console()
SITES_DIR = Path("sites")
PROXY_FILE = Path("Alive-proxy.txt")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SEM_LIMIT = 30
TIMEOUT = 8


def load_proxies(path):
    """Load proxies from file. Returns list of normalized http://user:pass@ip:port."""
    proxies = []
    if not path.exists():
        console.print(f"[red]Proxy file not found: {path}[/]")
        return proxies
    with open(path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split(":")
            if len(parts) >= 4:
                ip, port, user, pw = parts[0], parts[1], parts[2], parts[3]
                proxies.append(f"http://{user}:{pw}@{ip}:{port}")
            elif len(parts) == 2:
                proxies.append(f"http://{parts[0]}:{parts[1]}")
    return proxies


async def check_site(session, url, sem, proxy=None):
    async with sem:
        result = {"url": url, "status": "UNKNOWN", "products": 0, "title": "", "ms": 0, "proxy": "direct"}
        start = time.time()
        kwargs = {"timeout": aiohttp.ClientTimeout(total=TIMEOUT)}
        if proxy:
            kwargs["proxy"] = proxy
            result["proxy"] = proxy.split("@")[-1] if "@" in proxy else proxy
        try:
            async with session.get(f"{url}/products.json?limit=1", **kwargs) as resp:
                result["ms"] = int((time.time() - start) * 1000)
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        products = data.get("products", [])
                        result["products"] = len(products)
                        if products:
                            result["status"] = "LIVE"
                        else:
                            # Check homepage for password
                            async with session.get(url, **kwargs) as r2:
                                html = await r2.text()
                                if "password" in html.lower() and "protect" in html.lower():
                                    result["status"] = "PARKED"
                                else:
                                    result["status"] = "EMPTY"
                                import re
                                m = re.search(r"<title>(.*?)</title>", html, re.I)
                                if m:
                                    result["title"] = m.group(1)[:80]
                    except Exception:
                        result["status"] = "PARSE_ERROR"
                elif resp.status == 404:
                    result["status"] = "DEAD"
                elif resp.status == 403:
                    result["status"] = "BLOCKED"
                elif resp.status == 429:
                    result["status"] = "RATE_LIMITED"
                elif 500 <= resp.status < 600:
                    result["status"] = "SERVER_ERROR"
                else:
                    result["status"] = f"HTTP_{resp.status}"
        except asyncio.TimeoutError:
            result["status"] = "TIMEOUT"
        except aiohttp.ClientConnectorDNSError:
            result["status"] = "DNS_DEAD"
        except aiohttp.ClientConnectorCertificateError:
            result["status"] = "SSL_ERROR"
        except aiohttp.ClientHttpProxyError:
            result["status"] = "PROXY_ERROR"
        except aiohttp.ClientProxyConnectionError:
            result["status"] = "PROXY_DEAD"
        except aiohttp.ClientError as e:
            result["status"] = "CONN_ERROR"
        except Exception:
            result["status"] = "ERROR"
        return result


async def main():
    # Load proxies
    proxies = load_proxies(PROXY_FILE)
    console.print(f"\n[bold cyan]AURORA SITE CHECKER (PROXY)[/]")
    console.print(f"[dim]{'─'*40}[/]")
    console.print(f"Proxies loaded: {len(proxies)}")

    # Test a proxy first
    if proxies:
        console.print(f"[dim]Testing proxy: {proxies[0][:40]}...[/]")
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get("https://httpbin.org/ip", proxy=proxies[0],
                                  timeout=aiohttp.ClientTimeout(total=10)) as r:
                    ip_data = await r.json()
                    console.print(f"[green]✅ Proxy works! IP: {ip_data.get('origin','?')}[/]")
        except Exception as e:
            console.print(f"[yellow]⚠ First proxy failed, trying others...[/]")

    # Load all sites
    files = list(SITES_DIR.glob("*.txt"))
    all_urls = set()
    file_counts = {}
    for f in files:
        with open(f, "r", encoding="utf-8") as fh:
            urls = set()
            for line in fh:
                line = line.strip()
                if line.startswith("http"):
                    urls.add(line.rstrip("/"))
            file_counts[f.name] = len(urls)
            all_urls.update(urls)

    total = len(all_urls)
    console.print(f"\nFiles: {len(files)}")
    for name, count in file_counts.items():
        console.print(f"  {name}: {count}")
    console.print(f"[bold]Total unique: {total}[/]\n")

    sem = asyncio.Semaphore(SEM_LIMIT)
    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=aiohttp.resolver.ThreadedResolver())

    results = []
    proxy_idx = 0

    async with aiohttp.ClientSession(connector=connector) as session:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.completed}/{task.total}"),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Checking sites...", total=total)

            async def check_and_track(url):
                nonlocal proxy_idx
                proxy = None
                if proxies:
                    proxy = proxies[proxy_idx % len(proxies)]
                    proxy_idx += 1
                r = await check_site(session, url, sem, proxy)
                results.append(r)
                progress.update(task, advance=1)

            await asyncio.gather(*[check_and_track(u) for u in all_urls])

    # Sort
    results.sort(key=lambda x: x["url"])

    # Count statuses
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    # Summary
    console.print(f"\n[bold]{'═'*40}[/]")
    console.print(f"[bold cyan]SCAN COMPLETE[/]")
    console.print(f"[bold]{'═'*40}[/]\n")
    console.print(f"[bold]RESULTS:[/]")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        color = "green" if status == "LIVE" else "red" if status in ("DEAD", "DNS_DEAD") else "yellow"
        console.print(f"  [{color}]{status:15s}[/] : {count}")

    console.print(f"\n[bold]Total: {total}[/]")
    live = counts.get("LIVE", 0)
    console.print(f"[green]Live: {live}[/] ({live/total*100:.1f}%)")
    console.print(f"[red]Dead: {counts.get('DEAD',0) + counts.get('DNS_DEAD',0)}[/]")

    # CSV
    csv_path = OUTPUT_DIR / "site_check_proxy.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url", "status", "products", "title", "ms", "proxy"])
        w.writeheader()
        w.writerows(results)

    # Live
    live_path = OUTPUT_DIR / "live_sites.txt"
    with open(live_path, "w") as f:
        for r in results:
            if r["status"] == "LIVE":
                f.write(r["url"] + "\n")

    # Dead
    dead_path = OUTPUT_DIR / "dead_sites.txt"
    with open(dead_path, "w") as f:
        for r in results:
            if r["status"] in ("DEAD", "DNS_DEAD", "TIMEOUT", "SSL_ERROR"):
                f.write(r["url"] + "\n")

    console.print(f"\n[bold]OUTPUT:[/]")
    console.print(f"  📄 {csv_path} ({len(results)} rows)")
    console.print(f"  ✅ {live_path} ({live} sites)")
    console.print(f"  ❌ {dead_path} ({counts.get('DEAD',0)} sites)")
    console.print()


if __name__ == "__main__":
    asyncio.run(main())