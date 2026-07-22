"""Admin handler — /genkey, /genkeys, /keys, /revoke, /stats, /user, /ban, /unban, /broadcast, /reloadsites, /settier, /charged, /backup, /chk_all_site."""

import logging
import asyncio
import datetime
import functools
import time as _time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes, CallbackQueryHandler

from core.tier_manager import is_owner, is_admin, TIER_CONFIG, get_user_tier, get_tier_config
from core.database import get_or_create_user, is_banned
from core.card_parser import parse_card, luhn_valid
from core.checker import shopify_check
from core.rate_limiter import rate_limiter
from templates.messages import format_error, format_banned
from templates.emojis import (
    e_lightning, e_check_done, e_cross, e_gem, e_chart, e_heart,
    e_clipboard, e_mailbox, e_warning, e_smile, e_calendar, e_card,
)

logger = logging.getLogger(__name__)

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"
BOLD = lambda s: f"<b>{s}</b>"
CODE = lambda s: f"<code>{s}</code>"
ITALIC = lambda s: f"<i>{s}</i>"


def admin_only(func):
    """Decorator: restrict command to admins only."""
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        config = ctx.bot_data["config"]
        if not is_admin(user.id, config):
            await update.message.reply_text(
                "{e_cross()} Admin access required.", parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, ctx)
    return wrapper


def owner_only(func):
    """Decorator: restrict command to owner only."""
    @functools.wraps(func)
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        config = ctx.bot_data["config"]
        if not is_owner(user.id, config):
            await update.message.reply_text(
                "{e_cross()} Owner access required.", parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, ctx)
    return wrapper


@admin_only
async def genkey_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Placeholder — /genkey is handled by key_handler.py."""
    await update.message.reply_text("Use /genkey (key system v2).")


@admin_only
async def genkeys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Placeholder — not registered in bot.py."""
    await update.message.reply_text("Use /genkey (key system v2).")


@admin_only
async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /keys [active] — list batch keys from key system v2."""
    conn = ctx.bot_data["db"]
    active_only = len(ctx.args) > 0 and ctx.args[0].lower() == "active"

    if active_only:
        rows = conn.execute(
            "SELECT * FROM batch_keys WHERE status = 'unused' ORDER BY id DESC LIMIT 50"
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM batch_keys ORDER BY id DESC LIMIT 50"
        ).fetchall()

    if not rows:
        await update.message.reply_text("No keys found.")
        return

    lines = [f"📋 Batch Keys ({'active' if active_only else 'all'}): {len(rows)}\n"]
    for row in rows[:30]:
        status = "✅" if row["status"] == "unused" else "❌"
        redeemed = f"→ {row['redeemed_by']}" if row["redeemed_by"] else "unused"
        lines.append(
            f"{status} <code>{row['key']}</code> | {row['tier']} | "
            f"{row['duration_days']}d | {redeemed}"
        )

    if len(rows) > 30:
        lines.append(f"\n... and {len(rows) - 30} more")

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
    )


@admin_only
async def revoke_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /revoke <key> — mark a batch key as revoked."""
    if not ctx.args:
        await update.message.reply_text("{e_cross()} Usage: /revoke &lt;key&gt;", parse_mode=ParseMode.HTML)
        return

    key = ctx.args[0].upper().strip()
    conn = ctx.bot_data["db"]

    result = conn.execute(
        "UPDATE batch_keys SET status = 'revoked' WHERE key = ? AND status = 'unused'",
        (key,),
    )
    conn.commit()

    if result.rowcount > 0:
        await update.message.reply_text(f"{e_check_done()} Key revoked: <code>{key}</code>", parse_mode=ParseMode.HTML)
        logger.info("Admin %d revoked key: %s", update.effective_user.id, key)
    else:
        await update.message.reply_text("{e_cross()} Key not found or already redeemed/revoked.")


@admin_only
async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /stats — bot statistics."""
    conn = ctx.bot_data["db"]

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    banned_users = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
    active_keys = conn.execute("SELECT COUNT(*) FROM batch_keys WHERE status = 'unused'").fetchone()[0]
    redeemed_keys = conn.execute("SELECT COUNT(*) FROM batch_keys WHERE status = 'redeemed'").fetchone()[0]
    total_checks = conn.execute("SELECT COALESCE(SUM(total_checks), 0) FROM users").fetchone()[0]
    total_charged = conn.execute("SELECT COALESCE(SUM(total_charged), 0) FROM users").fetchone()[0]
    total_live = conn.execute("SELECT COALESCE(SUM(total_live), 0) FROM users").fetchone()[0]
    total_dead = conn.execute("SELECT COALESCE(SUM(total_dead), 0) FROM users").fetchone()[0]
    total_proxies = conn.execute("SELECT COUNT(*) FROM user_proxies WHERE status = 'live'").fetchone()[0]
    recent_charged = conn.execute("SELECT COUNT(*) FROM charged_cards WHERE checked_at > datetime('now', '-24 hours')").fetchone()[0]

    # Tier distribution
    tier_dist = conn.execute(
        "SELECT tier, COUNT(*) as count FROM users GROUP BY tier"
    ).fetchall()
    tier_lines = "\n".join(f"  {r['tier']}: {r['count']}" for r in tier_dist) or "  No data"

    # Top 5 users
    top_users = conn.execute(
        "SELECT user_id, username, total_checks FROM users "
        "ORDER BY total_checks DESC LIMIT 5"
    ).fetchall()
    top_lines = []
    for i, u in enumerate(top_users, 1):
        name = u["username"] or str(u["user_id"])
        top_lines.append(f"  {i}. {name}: {u['total_checks']} checks")
    top_text = "\n".join(top_lines) or "  No data"

    await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"{e_chart()} {BOLD('𝑩𝑶𝑻 𝑺𝑻𝑨𝑻𝑰𝑺𝑻𝑰𝑪𝑺')}\n\n"
        f"{e_clipboard()} {BOLD('Users')}          : {total_users}\n"
        f"{e_cross()} {BOLD('Banned')}         : {banned_users}\n"
        f"{e_gem()} {BOLD('Active Keys')}    : {active_keys}\n"
        f"{e_check_done()} {BOLD('Redeemed Keys')}   : {redeemed_keys}\n"
        f"{e_gem()} {BOLD('Total Checks')}   : {total_checks}\n"
        f"{e_heart()} {BOLD('Total Charged')}   : {total_charged}\n"
        f"{e_smile()} {BOLD('Total Live')}     : {total_live}\n"
        f"{e_warning()} {BOLD('Total Dead')}      : {total_dead}\n"
        f"{e_clipboard()} {BOLD('Live Proxies')}    : {total_proxies}\n"
        f"{e_heart()} {BOLD('Charged (24h)')}   : {recent_charged}\n\n"
        f"{DIVIDER}\n"
        f"{e_chart()} {BOLD('Tier Distribution')}\n{tier_lines}\n\n"
        f"{e_gem()} {BOLD('Top 5 Users')}\n{top_text}\n\n"
        f"{DIVIDER}\n"
        f"{e_mailbox()} {ITALIC('Owner: @rayzenqx')}",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def user_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /user <id> — view user info."""
    if not ctx.args:
        await update.message.reply_text("{e_cross()} Usage: /user &lt;id&gt;", parse_mode=ParseMode.HTML)
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("{e_cross()} Invalid user ID.")
        return

    conn = ctx.bot_data["db"]
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()

    if not user:
        await update.message.reply_text("{e_cross()} User not found.")
        return

    banned = "Yes" if user["banned"] else "No"
    expires = user["key_expires_at"] or "—"

    await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"👤 {BOLD('User Info')}\n\n"
        f"🆔 {BOLD('ID')}          : {user['user_id']}\n"
        f"👤 {BOLD('Username')}    : {user['username'] or '—'}\n"
        f"{e_gem()} {BOLD('Tier')}        : {user['tier']}\n"
        f"{e_chart()} {BOLD('Card Limit')}  : {user['card_limit']}\n"
        f"{e_lightning()} {BOLD('Workers')}     : {user['workers']}\n"
        f"{e_calendar()} {BOLD('Key Expires')} : {expires}\n"
        f"{e_gem()} {BOLD('Total Checks')}: {user['total_checks']}\n"
        f"{e_heart()} {BOLD('Charged')}     : {user['total_charged']}\n"
        f"{e_smile()} {BOLD('Live')}        : {user['total_live']}\n"
        f"{e_warning()} {BOLD('Dead')}         : {user['total_dead']}\n"
        f"{e_cross()} {BOLD('Banned')}      : {banned}\n"
        f"{e_calendar()} {BOLD('Joined')}      : {user['joined_at']}\n\n"
        f"{DIVIDER}",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /ban <id> [reason] — ban a user."""
    if not ctx.args:
        await update.message.reply_text(
            "{e_cross()} Usage: /ban &lt;id&gt; [reason]", parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("{e_cross()} Invalid user ID.")
        return

    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "No reason provided"
    conn = ctx.bot_data["db"]

    # Don't ban owner
    config = ctx.bot_data["config"]
    if target_id == config["bot"]["owner_id"]:
        await update.message.reply_text("{e_cross()} Cannot ban the owner.")
        return

    conn.execute(
        "UPDATE users SET banned = 1, banned_reason = ? WHERE user_id = ?",
        (reason, target_id),
    )
    conn.commit()

    await update.message.reply_text(
        f"{e_cross()} User {target_id} banned.\nReason: {reason}",
        parse_mode=ParseMode.HTML,
    )
    logger.info("Admin %d banned user %d: %s", update.effective_user.id, target_id, reason)


@admin_only
async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /unban <id> — unban a user."""
    if not ctx.args:
        await update.message.reply_text("{e_cross()} Usage: /unban &lt;id&gt;", parse_mode=ParseMode.HTML)
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("{e_cross()} Invalid user ID.")
        return

    conn = ctx.bot_data["db"]
    conn.execute(
        "UPDATE users SET banned = 0, banned_reason = NULL WHERE user_id = ?",
        (target_id,),
    )
    conn.commit()

    await update.message.reply_text(f"{e_check_done()} User {target_id} unbanned.")


@owner_only
async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast <msg> — broadcast to all users."""
    if not ctx.args:
        await update.message.reply_text("{e_cross()} Usage: /broadcast &lt;message&gt;", parse_mode=ParseMode.HTML)
        return

    message = " ".join(ctx.args)
    conn = ctx.bot_data["db"]
    users = conn.execute(
        "SELECT user_id FROM users WHERE banned = 0"
    ).fetchall()

    sent = 0
    failed = 0
    for u in users:
        try:
            await ctx.bot.send_message(
                chat_id=u["user_id"],
                text=f"📢 <b>Broadcast</b>\n\n{message}",
                parse_mode=ParseMode.HTML,
            )
            sent += 1
        except Exception as e:
            logger.debug("Broadcast failed for %d: %s", u["user_id"], e)
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast sent to {sent} users.\nFailed: {failed}",
        parse_mode=ParseMode.HTML,
    )


@owner_only
async def reloadsites_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /reloadsites — reload store lists."""
    loader = ctx.bot_data["loader"]
    loader.reload()

    stores_all = loader.get_stores("all")
    stores_5 = loader.get_stores("5")
    stores_10 = loader.get_stores("10")

    ctx.bot_data["stores_all"] = stores_all
    ctx.bot_data["stores_5"] = stores_5
    ctx.bot_data["stores_10"] = stores_10

    await update.message.reply_text(
        f"{e_check_done()} Sites reloaded.\n"
        f"{e_chart()} All: {len(stores_all)} | $5: {len(stores_5)} | $10: {len(stores_10)}",
    )


@owner_only
async def settier_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /settier <id> <tier> <days> — manually set user tier."""
    if len(ctx.args) < 3:
        await update.message.reply_text(
            "{e_cross()} Usage: /settier &lt;id&gt; &lt;tier&gt; &lt;days&gt;\n"
            "Example: /settier 123456789 ULTRA 30",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("{e_cross()} Invalid user ID.")
        return

    tier = ctx.args[1].upper()
    if tier not in TIER_CONFIG:
        await update.message.reply_text(
            f"{e_cross()} Invalid tier. Valid: {', '.join(TIER_CONFIG.keys())}",
        )
        return

    try:
        days = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("{e_cross()} Days must be a number.")
        return

    conn = ctx.bot_data["db"]
    cfg = TIER_CONFIG[tier]
    expires = datetime.datetime.utcnow() + datetime.timedelta(days=days)

    # Ensure user exists
    get_or_create_user(conn, target_id)

    conn.execute(
        """UPDATE users
           SET tier = ?, card_limit = ?, workers = ?, key_expires_at = ?
           WHERE user_id = ?""",
        (tier, cfg["card_limit"], cfg["workers"],
         expires.isoformat(), target_id),
    )
    conn.commit()

    await update.message.reply_text(
        f"{e_check_done()} User {target_id} set to {tier} for {days} days.\n"
        f"{e_calendar()} Expires: {expires.strftime('%Y-%m-%d %H:%M UTC')}",
    )
    logger.info("Owner %d set tier for %d: %s/%dd",
                 update.effective_user.id, target_id, tier, days)


@admin_only
async def charged_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /charged — show recent charged cards."""
    conn = ctx.bot_data["db"]
    rows = conn.execute(
        "SELECT * FROM charged_cards ORDER BY checked_at DESC LIMIT 20"
    ).fetchall()

    if not rows:
        await update.message.reply_text("No charged cards recorded.")
        return

    lines = [f"{e_heart()} <b>Recent Charged Cards ({len(rows)})</b>\n"]
    for r in rows:
        lines.append(
            f"<code>{r['card_masked']}</code> | {r['gateway']} | "
            f"${r['price']} | {r['checked_at']}"
        )

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
    )


@owner_only
async def backup_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /backup — backup SQLite database."""
    import shutil
    import os
    from pathlib import Path

    conn = ctx.bot_data["db"]
    db_path = conn.execute("PRAGMA database_list WHERE name = 'main'").fetchone()["file"]

    backup_dir = Path("data/backup")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"aurora_backup_{timestamp}.db"

    try:
        shutil.copy2(db_path, str(backup_path))
        await update.message.reply_text(
            f"{e_check_done()} Database backed up.\n{e_clipboard()} {backup_path}",
        )
        logger.info("DB backed up to %s", backup_path)
    except Exception as e:
        await update.message.reply_text(f"{e_cross()} Backup failed: {e}")


# ═════════════════════════════════════════════════════════════════════════
# /chk_all_site — Owner only: check one card against ALL stores
# ═════════════════════════════════════════════════════════════════════════

# Pending deletion sessions: {user_id: {bad_stores: [(url, reason)], card: str}}
_pending_deletions: dict[int, dict] = {}


@owner_only
async def chk_all_site_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /chk_all_site <card> — check one card against all stores.

    Owner only. Checks the card against every store in all site files.
    Stores that return errors (no_products, session_init_failed, timeout, dns_error)
    are flagged for deletion. After completion, shows a button to approve deletion.
    """
    user = update.effective_user
    config = ctx.bot_data["config"]

    if not is_owner(user.id, config):
        await update.message.reply_text("{e_cross()} Owner access required.")
        return

    # Parse card from args or reply
    raw_card = None
    if ctx.args:
        raw_card = " ".join(ctx.args)
    elif update.message.reply_to_message:
        raw_card = update.message.reply_to_message.text

    if not raw_card:
        await update.message.reply_text(
            f"{e_cross()} {BOLD('Usage:')}\n"
            f"{CODE('/chk_all_site 4798510629051356|12|2028|893')}\n\n"
            f"Checks one card against ALL stores.\n"
            f"Bad/error stores are flagged for deletion.",
            parse_mode=ParseMode.HTML,
        )
        return

    card = parse_card(raw_card)
    if not card:
        await update.message.reply_text(
            f"{e_cross()} Invalid card format.",
            parse_mode=ParseMode.HTML,
        )
        return

    if not luhn_valid(card.number):
        await update.message.reply_text(
            f"{e_cross()} Card failed Luhn check.",
            parse_mode=ParseMode.HTML,
        )
        return

    # Get all stores with source files
    loader = ctx.bot_data["loader"]
    all_stores = loader.get_all_stores_with_source()

    if not all_stores:
        await update.message.reply_text(
            f"{e_cross()} No stores found.",
            parse_mode=ParseMode.HTML,
        )
        return

    total = len(all_stores)
    await update.message.reply_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"{e_chart()} {BOLD('Check All Sites')}\n\n"
        f"{e_card()} Card: {CODE(card.masked)}\n"
        f"{e_chart()} Total stores: {total}\n"
        f"{e_lightning()} Workers: 50 (parallel)\n"
        f"{e_cross()} Bad stores will be flagged for deletion\n\n"
        f"{e_heart()} Starting check...",
        parse_mode=ParseMode.HTML,
    )

    # Run the check
    pm = ctx.bot_data.get("proxy_manager")
    good_stores = []     # stores where card got a real response (CHARGED/LIVE/DEAD)
    bad_stores = []      # stores with errors (no_products, timeout, dns, session_init, etc.)
    charged_stores = []
    live_stores = []

    # Get owner's tier workers
    conn = ctx.bot_data["db"]
    owner_tier = get_user_tier(conn, user.id)
    owner_cfg = get_tier_config(owner_tier)
    worker_count = owner_cfg["workers"]

    semaphore = asyncio.Semaphore(worker_count)
    progress = {"checked": 0}
    start_time = _time.time()
    progress_msg = None

    async def check_one(store_url: str, source_file: str):
        nonlocal progress_msg
        async with semaphore:
            proxy = None
            if pm:
                proxy = pm.get_proxy(user.id)

            result = await shopify_check(card, store_url, proxy=proxy, timeout=20)

            progress["checked"] += 1
            checked = progress["checked"]

            # Classify store health
            error_keywords = (
                "no_products_found", "session_init_failed", "timeout",
                "dns_error", "ssl_error", "connection_error",
                "checkout_start_failed", "token_extraction_failed",
                "cart_failed", "unknown_error", "proxy_error",
                "card_vault_failed", "submission_rejected",
            )

            if any(kw in result.message for kw in error_keywords):
                bad_stores.append((store_url, source_file, result.message))
            else:
                good_stores.append(store_url)
                if result.status == "CHARGED":
                    charged_stores.append((store_url, result.price))
                elif result.status in ("LIVE", "LIVE_3DS"):
                    live_stores.append((store_url, result.message))

            # Progress update every 50 stores
            if checked % 50 == 0 or checked == total:
                elapsed = _time.time() - start_time
                m = int(elapsed // 60)
                s = int(elapsed % 60)
                pct = int(checked / total * 100) if total > 0 else 0
                try:
                    text = (
                        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
                        f"{DIVIDER}\n\n"
                        f"{e_chart()} {BOLD('Check All Sites — Progress')}\n\n"
                        f"{e_card()} Card: {CODE(card.masked)}\n"
                        f"{e_chart()} Checked: {checked}/{total} ({pct}%)\n"
                        f"⏰ Duration: {m}m {s}s\n\n"
                        f"{e_heart()} Charged: {len(charged_stores)}\n"
                        f"{e_check_done()} Live: {len(live_stores)}\n"
                        f"{e_check_done()} Good stores: {len(good_stores)}\n"
                        f"{e_cross()} Bad stores: {len(bad_stores)}\n\n"
                        f"{DIVIDER}"
                    )
                    if progress_msg:
                        await progress_msg.edit_text(text, parse_mode=ParseMode.HTML)
                    else:
                        progress_msg = await update.message.reply_text(
                            text, parse_mode=ParseMode.HTML,
                        )
                except Exception:
                    pass

    tasks = [check_one(url, src) for url, src in all_stores]
    await asyncio.gather(*tasks, return_exceptions=True)

    elapsed = _time.time() - start_time
    m = int(elapsed // 60)
    s = int(elapsed % 60)

    # Store bad stores for deletion approval
    _pending_deletions[user.id] = {
        "bad_stores": bad_stores,
        "card": card.masked,
        "total": total,
        "good": len(good_stores),
    }

    # Build result message
    result_text = (
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"{e_check_done()} {BOLD('Check All Sites — Complete')}\n\n"
        f"{e_card()} Card: {CODE(card.masked)}\n"
        f"{e_chart()} Total stores checked: {total}\n"
        f"⏰ Duration: {m}m {s}s\n\n"
        f"{DIVIDER}\n"
        f"{e_heart()} {BOLD('Charged')}: {len(charged_stores)}\n"
    )
    for url, price in charged_stores[:10]:
        result_text += f"  {e_heart()} {url} — ${price}\n"
    if len(charged_stores) > 10:
        result_text += f"  ... and {len(charged_stores) - 10} more\n"

    result_text += f"\n{e_check_done()} {BOLD('Live')}: {len(live_stores)}\n"
    for url, msg in live_stores[:10]:
        result_text += f"  {e_check_done()} {url} — {msg}\n"
    if len(live_stores) > 10:
        result_text += f"  ... and {len(live_stores) - 10} more\n"

    result_text += (
        f"\n{e_check_done()} {BOLD('Good stores')}: {len(good_stores)}\n"
        f"{e_cross()} {BOLD('Bad/Error stores')}: {len(bad_stores)}\n\n"
        f"{DIVIDER}\n"
    )

    if bad_stores:
        result_text += (
            f"\n{e_cross()} {BOLD('Bad stores flagged for deletion:')}\n"
            f"Stores with errors (no products, timeout, DNS fail, etc.)\n\n"
        )
        # Show breakdown by error type
        error_counts = {}
        for _, _, reason in bad_stores:
            error_counts[reason] = error_counts.get(reason, 0) + 1
        for reason, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            result_text += f"  • {reason}: {count} stores\n"

        result_text += (
            f"\n{BOLD('Total to delete')}: {len(bad_stores)} stores\n\n"
            f"Press button below to approve deletion."
        )

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                f"{e_check_done()} Delete {len(bad_stores)} bad stores",
                callback_data="delete_bad_stores",
            ),
            InlineKeyboardButton("{e_cross()} Cancel", callback_data="cancel_deletion"),
        ]])
        await update.message.reply_text(
            result_text, parse_mode=ParseMode.HTML, reply_markup=keyboard,
        )
    else:
        result_text += f"\n{e_check_done()} All stores are healthy!"
        await update.message.reply_text(result_text, parse_mode=ParseMode.HTML)

    logger.info(
        "chk_all_site: user=%d total=%d good=%d bad=%d charged=%d live=%d",
        user.id, total, len(good_stores), len(bad_stores),
        len(charged_stores), len(live_stores),
    )
    rate_limiter.end_mass(user.id)


async def handle_deletion_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle inline button callback for bad store deletion."""
    query = update.callback_query
    await query.answer()

    user = query.from_user
    data = query.data

    if data == "cancel_deletion":
        _pending_deletions.pop(user.id, None)
        await query.edit_message_text(
            f"{e_cross()} Deletion cancelled. Bad stores kept.",
            parse_mode=ParseMode.HTML,
        )
        return

    if data != "delete_bad_stores":
        return

    pending = _pending_deletions.get(user.id)
    if not pending:
        await query.edit_message_text("{e_cross()} Session expired. Run /chk_all_site again.")
        return

    bad_stores = pending["bad_stores"]
    loader = ctx.bot_data["loader"]

    # Delete bad stores from their source files
    deleted = 0
    failed = 0
    files_modified = set()

    for store_url, source_file, _ in bad_stores:
        if loader.remove_store(store_url, source_file):
            deleted += 1
            files_modified.add(source_file)
        else:
            failed += 1

    # Clear loader cache so changes take effect
    loader.reload()

    # Update ALL bot_data store lists
    ctx.bot_data["stores_all"] = loader.get_stores("all")
    ctx.bot_data["stores_5"] = loader.get_stores("5")
    ctx.bot_data["stores_10"] = loader.get_stores("10")

    _pending_deletions.pop(user.id, None)

    await query.edit_message_text(
        f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
        f"{DIVIDER}\n\n"
        f"{e_check_done()} {BOLD('Deletion Complete')}\n\n"
        f"{e_cross()} Deleted: {deleted} bad stores\n"
        f"{e_cross()} Failed: {failed}\n"
        f"{e_clipboard()} Files modified: {len(files_modified)}\n\n"
        f"{DIVIDER}\n"
        f"{e_clipboard()} Stores remaining: {len(loader.get_stores('all'))}",
        parse_mode=ParseMode.HTML,
    )
    logger.info(
        "chk_all_site deletion: user=%d deleted=%d failed=%d files=%s",
        user.id, deleted, failed, files_modified,
    )