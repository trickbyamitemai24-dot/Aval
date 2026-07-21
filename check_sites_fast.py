"""Fast site checker — direct connection, no proxy. Uses ThreadedResolver for proot compatibility."""

import asyncio, aiohttp, csv, time, os, re
from pathlib import Path
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn
from aiohttp.resolver import ThreadedResolver

console = Console()
SITES_DIR = Path("sites")
OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

SEM_LIMIT = 50
TIMEOUT = 8


async def check_site(session, url, sem):
    async with sem:
        result = {"url": url, "status": "UNKNOWN", "products": 0, "title": "", "ms": 0}
        start = time.time()
        try:
            async with session.get(f"{url}/products.json?limit=1") as resp:
                result["ms"] = int((time.time() - start) * 1000)
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        products = data.get("products", [])
                        result["products"] = len(products)
                        if products:
                            result["status"] = "LIVE"
                        else:
                            async with session.get(url) as r2:
                                html = await r2.text()
                                if "password" in html.lower() and "protect" in html.lower():
                                    result["status"] = "PARKED"
                                else:
                                    result["status"] = "EMPTY"
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
        except aiohttp.ClientError:
            result["status"] = "CONN_ERROR"
        except Exception:
            result["status"] = "ERROR"
        return result


async def main():
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
    console.print(f"\n[bold cyan]AURORA SITE CHECKER (DIRECT)[/]")
    console.print(f"[dim]{'─'*40}[/]")
    for name, count in file_counts.items():
        console.print(f"  {name}: {count}")
    console.print(f"[bold]Total unique: {total}[/]\n")

    sem = asyncio.Semaphore(SEM_LIMIT)
    connector = aiohttp.TCPConnector(limit=0, ssl=False, resolver=ThreadedResolver())
    results = []

    async with aiohttp.ClientSession(connector=connector, timeout=aiohttp.ClientTimeout(total=TIMEOUT)) as session:
        with Progress(SpinnerColumn(), TextColumn("{task.description}"), BarColumn(),
                      TextColumn("{task.completed}/{task.total}"), TimeElapsedColumn(), console=console) as progress:
            task = progress.add_task("Checking sites...", total=total)
            async def track(url):
                r = await check_site(session, url, sem)
                results.append(r)
                progress.update(task, advance=1)
            await asyncio.gather(*[track(u) for u in all_urls])

    results.sort(key=lambda x: x["url"])
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    console.print(f"\n[bold]{'═'*40}[/]")
    console.print(f"[bold cyan]SCAN COMPLETE[/]")
    console.print(f"[bold]{'═'*40}[/]\n")
    for status, count in sorted(counts.items(), key=lambda x: -x[1]):
        color = "green" if status == "LIVE" else "red" if status in ("DEAD","DNS_DEAD") else "yellow"
        console.print(f"  [{color}]{status:15s}[/] : {count}")

    live = counts.get("LIVE", 0)
    console.print(f"\n[bold]Total: {total}[/]")
    console.print(f"[green]Live: {live}[/] ({live/total*100:.1f}%)")
    console.print(f"[red]Dead: {counts.get('DEAD',0)}[/]")

    csv_path = OUTPUT_DIR / "site_check.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["url","status","products","title","ms"])
        w.writeheader(); w.writerows(results)

    live_path = OUTPUT_DIR / "live_sites.txt"
    with open(live_path, "w") as f:
        for r in results:
            if r["status"] == "LIVE": f.write(r["url"] + "\n")

    dead_path = OUTPUT_DIR / "dead_sites.txt"
    with open(dead_path, "w") as f:
        for r in results:
            if r["status"] in ("DEAD","DNS_DEAD","TIMEOUT","SSL_ERROR"): f.write(r["url"] + "\n")

    console.print(f"\n[bold]OUTPUT:[/]")
    console.print(f"  📄 {csv_path}")
    console.print(f"  ✅ {live_path} ({live})")
    console.print(f"  ❌ {dead_path} ({counts.get('DEAD',0)})")
    console.print()


if __name__ == "__main__":
    asyncio.run(main())