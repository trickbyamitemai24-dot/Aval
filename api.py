import urllib.parse
from aiohttp import web
from core.card_parser import parse_card
from core.checker import shopify_check
from core.proxy_manager import normalize_proxy

async def shopify_handler(request):
    site = request.query.get("site")
    cc = request.query.get("cc")
    raw_proxy = request.query.get("proxy")

    if not site or not cc:
        return web.json_response({"error": "Missing 'site' or 'cc' parameter"}, status=400)

    # Decode site URL if necessary (aiohttp does some unquoting automatically, but just in case)
    site = urllib.parse.unquote(site)

    card = parse_card(cc)
    if not card:
        return web.json_response({"error": "Invalid card format"}, status=400)

    proxy = normalize_proxy(raw_proxy) if raw_proxy else None
    if raw_proxy and not proxy:
        return web.json_response({"error": "Invalid proxy format"}, status=400)

    try:
        # Run the shopify check
        result = await shopify_check(
            store_url=site,
            card=card,
            proxy=proxy,
            timeout=25  # Give it a bit more time for API
        )
        
        return web.json_response({
            "status": result.status,
            "message": result.message,
            "gateway": result.gateway,
            "price": result.price,
            "store": result.store,
            "card": card.masked,
            "debug_proxy": proxy
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

def create_api_app():
    app = web.Application()
    app.router.add_get('/shopify', shopify_handler)
    
    # Root and health handlers
    async def root_handler(request):
        return web.Response(text="Aurora Checker API is running")
    
    async def health_handler(request):
        return web.Response(text="OK")
        
    app.router.add_get('/', root_handler)
    app.router.add_get('/health', health_handler)
    app.router.add_get('/debug', debug_handler)
    return app

async def debug_handler(request):
    import aiohttp
    proxy = "http://purevpn0s11127688:4mwmyaoa@px014236.pointtoserver.com:10780"
    url = "https://artpop.com/products.json?limit=1"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    
    res = {}
    
    # 1. Direct
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, headers=headers) as r:
                res["direct"] = r.status
    except Exception as e:
        res["direct"] = str(e)
        
    # 2. Proxy
    try:
        async with aiohttp.ClientSession() as s:
            async with s.get(url, proxy=proxy, headers=headers) as r:
                res["proxy"] = r.status
    except Exception as e:
        res["proxy"] = str(e)
        
    return web.json_response(res)
