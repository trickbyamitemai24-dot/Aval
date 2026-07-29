import urllib.parse
from aiohttp import web
from core.card_parser import parse_card
from core.checker import shopify_check

async def shopify_handler(request):
    site = request.query.get("site")
    cc = request.query.get("cc")
    proxy = request.query.get("proxy")

    if not site or not cc:
        return web.json_response({"error": "Missing 'site' or 'cc' parameter"}, status=400)

    # Decode site URL if necessary (aiohttp does some unquoting automatically, but just in case)
    site = urllib.parse.unquote(site)

    card = parse_card(cc)
    if not card:
        return web.json_response({"error": "Invalid card format"}, status=400)

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
            "card": card.masked
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
    return app
