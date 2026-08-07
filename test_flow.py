import asyncio
from unittest.mock import MagicMock, AsyncMock
from handlers.single_check import single_check_cmd
from telegram import Update
import logging
logging.basicConfig(level=logging.DEBUG)

async def main():
    ctx = MagicMock()
    ctx.args = ["5455122802569146|12|26|543"]
    
    update = MagicMock()
    update.message.reply_to_message = None
    update.effective_user.id = 12345
    update.effective_user.username = "test"
    update.effective_user.first_name = "test"
    
    update.message.reply_text = AsyncMock()
    update.message.reply_text.return_value = AsyncMock()
    
    from core.database import init_db
    conn = init_db(":memory:")
    
    from core.bin_lookup import BinLookup
    bin_lookup = BinLookup(conn)
    
    loader = MagicMock()
    loader.get_stores.return_value = ["https://dandyworldwide.com"]
    
    ctx.bot_data = {
        "db": conn,
        "loader": loader,
        "stores_all": ["https://dandyworldwide.com"],
        "proxy_manager": None,
        "bin_lookup": bin_lookup
    }
    
    await single_check_cmd(update, ctx)
    print("Done")

asyncio.run(main())
