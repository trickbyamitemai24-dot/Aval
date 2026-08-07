import re

with open("handlers/single_check.py", "r") as f:
    code = f.read()

# We'll create an async wrapper for the check loop
wrapper_code = """
    async def _run_store_check():
        used = set()
        pm = ctx.bot_data.get("proxy_manager")
        max_store_retries = 5
        res = None
        s = None
        for attempt in range(max_store_retries):
            s = pick_store(stores, used)
            if not s:
                break
            used.add(s)
            
            p = pm.get_proxy(user.id) if pm else None
            res = await shopify_check(card, s, proxy=p, timeout=120)
            
            if res.status != "SITE_ERROR":
                break
                
            await asyncio.sleep(1)
            
        if res is None or res.status == "SITE_ERROR":
            from core.checker import CheckResult
            res = CheckResult("DEAD", "All stores returned errors — try again later", "Shopify Payments", 0.0, s or "unknown", card)
            
        return res

    # Run check + BIN lookup in parallel (saves 2-10s latency)
    import asyncio
    bin_lookup: BinLookup = ctx.bot_data["bin_lookup"]
    
    check_task = asyncio.create_task(_run_store_check())
    bin_task = asyncio.create_task(bin_lookup.lookup(card.bin))
    
    result, bin_info = await asyncio.gather(check_task, bin_task)

    if not result:
        await checking_msg.edit_text(format_error("No working stores available right now."))
        rate_limiter.refund_hourly(user.id)
        return
"""

# Replace from `used = set()` to `if not result:` with our wrapper
start_idx = code.find('    used = set()')
end_idx = code.find('    if not isinstance(bin_info, dict):')

if start_idx != -1 and end_idx != -1:
    code = code[:start_idx] + wrapper_code + "\n" + code[end_idx:]
    with open("handlers/single_check.py", "w") as f:
        f.write(code)
    print("Parallel check applied")
else:
    print("Failed to apply parallel check")
