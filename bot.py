"""Aurora Checker — Telegram bot entry point.

Tranger Cloud / Railway / Docker ready.
28 commands, god-level UI, full error handling, rate limiting.
"""

import os
import sys
import logging
import threading

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from core.database import init_db
from core.loader import StoreLoader
from core.bin_lookup import BinLookup
from core.proxy_manager import ProxyManager
from core.error_handler import ErrorHandler, HealthMonitor
from core.rate_limiter import rate_limiter
from core.store_health import init_store_health, StoreHealthCache
from utils.config_loader import load_config
from utils.logger import setup_logging

from handlers.start import start_cmd, status_cmd
from handlers.help import help_cmd
from handlers.single_check import single_check_cmd, stripe_check_cmd
from handlers.bin_handler import bin_cmd
from handlers.mass_check import (
    mass_check_cmd,
    receive_card_file,
    cancel_mass_check,
    mass_check_callback,
    resume_cmd,
    WAITING_FOR_FILE,
    CB_PRICE_5,
    CB_PRICE_10,
    CB_PRICE_ALL,
    CB_PRICE_HQ,
    CB_CANCEL,
)
from handlers.key_handler import redeem_cmd, genkey_cmd, status_cmd as key_status_cmd
from handlers.pricing import plans_cmd
from handlers.admin import (
    keys_cmd,
    revoke_cmd,
    stats_cmd,
    user_cmd,
    ban_cmd,
    unban_cmd,
    broadcast_cmd,
    reloadsites_cmd,
    settier_cmd,
    charged_cmd,
    backup_cmd,
)
from handlers.proxy_handler import (
    addproxy_cmd,
    receive_proxies,
    cancel_proxy_add,
    proxy_cmd,
    clearproxy_cmd,
    WAITING_FOR_PROXY,
)

logger = logging.getLogger(__name__)


def start_health_server():
    """Lightweight health check server for Railway (runs in background thread)."""
    port = int(os.environ.get("PORT", 8080))
    try:
        from http.server import HTTPServer, BaseHTTPRequestHandler

        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/health":
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain")
                    self.end_headers()
                    self.wfile.write(b"OK")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress logs

        server = HTTPServer(("0.0.0.0", port), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        logger.info("Health check server started on port %d (thread)", port)
    except Exception as e:
        logger.warning("Health server failed to start: %s", e)


def main():
    # Load config
    config_path = os.environ.get("CONFIG_PATH", "config.yaml")
    config = load_config(config_path)

    # Setup logging
    log_level = os.environ.get("LOG_LEVEL", config.get("logging", {}).get("level", "INFO"))
    log_file = os.environ.get("LOG_FILE", config.get("logging", {}).get("file", "logs/aurora.log"))
    setup_logging(log_file, log_level)

    logger.info("=" * 50)
    logger.info("  AURORA CHECKER — Starting up...")
    logger.info("=" * 50)

    # Get bot token (env var takes priority)
    token = os.environ.get("BOT_TOKEN") or config.get("bot", {}).get("token", "")
    if not token or token.startswith("${"):
        logger.error("BOT_TOKEN not set. Set BOT_TOKEN env var.")
        sys.exit(1)

    # Init database
    db_path = os.environ.get("DATABASE_PATH", config.get("database", {}).get("path", "data/aurora.db"))
    conn = init_db(db_path)

    # Load stores
    sites_dir = config.get("sites_dir", "sites")
    loader = StoreLoader(sites_dir)
    stores_all = loader.get_stores("all")
    stores_5 = loader.get_stores("5")
    stores_10 = loader.get_stores("10")

    logger.info("Loaded stores: all=%d, $5=%d, $10=%d", len(stores_all), len(stores_5), len(stores_10))

    # Init BIN lookup
    bin_api_url = config.get("bin_lookup", {}).get("api_url", "")
    bin_lookup = BinLookup(conn, bin_api_url)

    # Init proxy manager
    proxy_manager = ProxyManager(conn)

    # Init store health
    init_store_health(conn)
    health_cache = StoreHealthCache(conn)

    # Init error handler + health monitor
    error_handler = ErrorHandler(config)
    health_monitor = HealthMonitor()

    # Build Telegram app
    app = Application.builder().token(token).build()

    # Store shared state
    app.bot_data["db"] = conn
    app.bot_data["config"] = config
    app.bot_data["loader"] = loader
    app.bot_data["stores_all"] = stores_all
    app.bot_data["stores_5"] = stores_5
    app.bot_data["stores_10"] = stores_10
    app.bot_data["bin_lookup"] = bin_lookup
    app.bot_data["proxy_manager"] = proxy_manager
    app.bot_data["error_handler"] = error_handler
    app.bot_data["health_monitor"] = health_monitor
    app.bot_data["health_cache"] = health_cache

    # ── Register handlers ──

    # Core commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("status", key_status_cmd))
    app.add_handler(CommandHandler("sh", single_check_cmd))
    app.add_handler(CommandHandler("st", stripe_check_cmd))
    app.add_handler(CommandHandler("bin", bin_cmd))

    # Mass check conversation: /chk → wait for file → process
    mass_conv = ConversationHandler(
        entry_points=[CommandHandler("chk", mass_check_cmd)],
        states={
            WAITING_FOR_FILE: [
                MessageHandler(filters.Document.TXT, receive_card_file),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_mass_check)],
    )
    app.add_handler(mass_conv)

    # Inline button callback for price range selection
    app.add_handler(CallbackQueryHandler(
        mass_check_callback,
        pattern=r"^mc_(price_5|price_10|price_all|price_hq|price_v40|cancel)$",
    ))

    # Resume interrupted mass check
    app.add_handler(CommandHandler("resume", resume_cmd))

    # Key + pricing + status
    app.add_handler(CommandHandler("redeem", redeem_cmd))
    app.add_handler(CommandHandler("plans", plans_cmd))
    app.add_handler(CommandHandler("genkey", genkey_cmd))

    # Admin commands
    app.add_handler(CommandHandler("keys", keys_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("user", user_cmd))
    app.add_handler(CommandHandler("ban", ban_cmd))
    app.add_handler(CommandHandler("unban", unban_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(CommandHandler("reloadsites", reloadsites_cmd))
    app.add_handler(CommandHandler("settier", settier_cmd))
    app.add_handler(CommandHandler("charged", charged_cmd))
    app.add_handler(CommandHandler("backup", backup_cmd))

    # Proxy commands
    app.add_handler(CommandHandler("proxy", proxy_cmd))
    app.add_handler(CommandHandler("clearproxy", clearproxy_cmd))

    # Add proxy conversation: /addproxy → wait for text/file → validate
    proxy_conv = ConversationHandler(
        entry_points=[CommandHandler("addproxy", addproxy_cmd)],
        states={
            WAITING_FOR_PROXY: [
                MessageHandler(filters.Document.TXT, receive_proxies),
                MessageHandler(filters.TEXT & ~filters.COMMAND, receive_proxies),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel_proxy_add)],
    )
    app.add_handler(proxy_conv)

    # Global error handler (catches ALL unhandled exceptions)
    app.add_error_handler(error_handler.handle_error)

    logger.info("Bot handlers registered (28 commands). Starting polling...")

    # Start health check server in background thread (Railway healthcheck)
    start_health_server()

    # Run bot — blocks until stopped
    # PTB handles SIGINT/SIGTERM internally
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()