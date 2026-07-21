"""Admin handler — /genkey, /genkeys, /keys, /revoke, /stats, /user, /ban, /unban, /broadcast, /reloadsites, /settier, /charged, /backup."""

import logging
import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.tier_manager import is_owner, is_admin, TIER_CONFIG
from core.database import get_or_create_user, is_banned
from templates.messages import format_error, format_banned
from templates.emojis import (
    e_lightning, e_check_done, e_cross, e_gem, e_chart, e_heart,
    e_clipboard, e_mailbox,
)

logger = logging.getLogger(__name__)

DIVIDER = "━━━━━━━━━━━━━━━━━━━━━━"
BOLD = lambda s: f"<b>{s}</b>"
CODE = lambda s: f"<code>{s}</code>"
ITALIC = lambda s: f"<i>{s}</i>"


def admin_only(func):
    """Decorator: restrict command to admins only."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        config = ctx.bot_data["config"]
        if not is_admin(user.id, config):
            await update.message.reply_text(
                "❌ Admin access required.", parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, ctx)
    return wrapper


def owner_only(func):
    """Decorator: restrict command to owner only."""
    async def wrapper(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        config = ctx.bot_data["config"]
        if not is_owner(user.id, config):
            await update.message.reply_text(
                "❌ Owner access required.", parse_mode=ParseMode.HTML,
            )
            return
        return await func(update, ctx)
    return wrapper


@admin_only
async def genkey_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /genkey <tier> <days> — generate a single key."""
    if len(ctx.args) < 2:
        await update.message.reply_text(
            "❌ Usage: /genkey &lt;tier&gt; &lt;days&gt;\n"
            "Example: /genkey PRO 30",
            parse_mode=ParseMode.HTML,
        )
        return

    tier = ctx.args[0].upper()
    try:
        days = int(ctx.args[1])
    except ValueError:
        await update.message.reply_text("❌ Days must be a number.")
        return

    if tier not in KEY_TIER_CONFIG:
        await update.message.reply_text(
            f"❌ Invalid tier. Valid: {', '.join(KEY_TIER_CONFIG.keys())}",
        )
        return

    if days < 1 or days > 365:
        await update.message.reply_text("❌ Days must be 1-365.")
        return

    key = generate_key(tier)
    conn = ctx.bot_data["db"]

    if save_key_to_db(conn, key, tier, days, update.effective_user.id):
        await update.message.reply_text(
            f"{e_lightning()} 𝐀𝐔𝐑𝐎𝐑𝐀 𝐂𝐇𝐄𝐂𝐊𝐄𝐑 {e_lightning()}\n"
            f"{DIVIDER}\n\n"
            f"{e_check_done()} {BOLD('Key Generated')}\n\n"
            f"{CODE(key)}\n\n"
            f"{e_gem()} {BOLD('Tier')}     : {tier}\n"
            f"📅 {BOLD('Duration')} : {days} days\n"
            f"👤 {BOLD('Created by')} : {update.effective_user.username or update.effective_user.id}\n\n"
            f"{DIVIDER}",
            parse_mode=ParseMode.HTML,
        )
        logger.info("Admin %d generated key: %s (%s/%dd)",
                     update.effective_user.id, key, tier, days)
    else:
        await update.message.reply_text("❌ Failed to generate key (duplicate). Try again.")


@admin_only
async def genkeys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /genkeys <tier> <days> <count> — generate multiple keys."""
    if len(ctx.args) < 3:
        await update.message.reply_text(
            "❌ Usage: /genkeys &lt;tier&gt; &lt;days&gt; &lt;count&gt;\n"
            "Example: /genkeys MAX 30 5",
            parse_mode=ParseMode.HTML,
        )
        return

    tier = ctx.args[0].upper()
    try:
        days = int(ctx.args[1])
        count = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("❌ Days and count must be numbers.")
        return

    if tier not in KEY_TIER_CONFIG:
        await update.message.reply_text(
            f"❌ Invalid tier. Valid: {', '.join(KEY_TIER_CONFIG.keys())}",
        )
        return

    if count < 1 or count > 50:
        await update.message.reply_text("❌ Count must be 1-50.")
        return

    conn = ctx.bot_data["db"]
    keys = generate_keys(tier, count)
    saved = []
    for k in keys:
        if save_key_to_db(conn, k, tier, days, update.effective_user.id):
            saved.append(k)

    if not saved:
        await update.message.reply_text("❌ Failed to generate keys.")
        return

    keys_text = "\n".join(f"<code>{k}</code>" for k in saved)
    await update.message.reply_text(
        f"✅ Generated {len(saved)} keys:\n\n"
        f"{keys_text}\n\n"
        f"💎 Tier: {tier} | 📅 {days} days",
        parse_mode=ParseMode.HTML,
    )
    logger.info("Admin %d generated %d keys (%s/%dd)",
                 update.effective_user.id, len(saved), tier, days)


@admin_only
async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /keys [active] — list all keys."""
    conn = ctx.bot_data["db"]
    active_only = len(ctx.args) > 0 and ctx.args[0].lower() == "active"

    rows = get_all_keys(conn, active_only=active_only)

    if not rows:
        await update.message.reply_text("No keys found.")
        return

    lines = [f"📋 Keys ({'active' if active_only else 'all'}): {len(rows)}\n"]
    for row in rows[:30]:  # Limit to 30 to avoid message too long
        status = "✅" if row["active"] else "❌"
        redeemed = f"→ {row['redeemed_by']}" if row["redeemed_by"] else "unused"
        lines.append(
            f"{status} <code>{row['key']}</code> | {row['tier']} | "
            f"{row['days']}d | {redeemed}"
        )

    if len(rows) > 30:
        lines.append(f"\n... and {len(rows) - 30} more")

    await update.message.reply_text(
        "\n".join(lines), parse_mode=ParseMode.HTML,
    )


@admin_only
async def revoke_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /revoke <key> — revoke a key."""
    if not ctx.args:
        await update.message.reply_text("❌ Usage: /revoke &lt;key&gt;", parse_mode=ParseMode.HTML)
        return

    key = ctx.args[0].upper()
    conn = ctx.bot_data["db"]

    if revoke_key(conn, key):
        await update.message.reply_text(f"✅ Key revoked: <code>{key}</code>", parse_mode=ParseMode.HTML)
        logger.info("Admin %d revoked key: %s", update.effective_user.id, key)
    else:
        await update.message.reply_text("❌ Key not found or already inactive.")


@admin_only
async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /stats — bot statistics."""
    conn = ctx.bot_data["db"]

    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    banned_users = conn.execute("SELECT COUNT(*) FROM users WHERE banned = 1").fetchone()[0]
    active_keys = conn.execute("SELECT COUNT(*) FROM keys WHERE active = 1 AND redeemed_by IS NULL").fetchone()[0]
    redeemed_keys = conn.execute("SELECT COUNT(*) FROM keys WHERE redeemed_by IS NOT NULL").fetchone()[0]
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
        f"👥 {BOLD('Users')}          : {total_users}\n"
        f"🚫 {BOLD('Banned')}         : {banned_users}\n"
        f"{e_gem()} {BOLD('Active Keys')}    : {active_keys}\n"
        f"{e_check_done()} {BOLD('Redeemed Keys')}   : {redeemed_keys}\n"
        f"🔑 {BOLD('Total Checks')}   : {total_checks}\n"
        f"{e_heart()} {BOLD('Total Charged')}   : {total_charged}\n"
        f"😀 {BOLD('Total Live')}     : {total_live}\n"
        f"⚠️ {BOLD('Total Dead')}      : {total_dead}\n"
        f"{e_clipboard()} {BOLD('Live Proxies')}    : {total_proxies}\n"
        f"{e_heart()} {BOLD('Charged (24h)')}   : {recent_charged}\n\n"
        f"{DIVIDER}\n"
        f"📈 {BOLD('Tier Distribution')}\n{tier_lines}\n\n"
        f"🏆 {BOLD('Top 5 Users')}\n{top_text}\n\n"
        f"{DIVIDER}\n"
        f"{e_mailbox()} {ITALIC('Owner: @rayzenqx')}",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def user_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /user <id> — view user info."""
    if not ctx.args:
        await update.message.reply_text("❌ Usage: /user &lt;id&gt;", parse_mode=ParseMode.HTML)
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    conn = ctx.bot_data["db"]
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (target_id,)).fetchone()

    if not user:
        await update.message.reply_text("❌ User not found.")
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
        f"⚡ {BOLD('Workers')}     : {user['workers']}\n"
        f"📅 {BOLD('Key Expires')} : {expires}\n"
        f"🔑 {BOLD('Total Checks')}: {user['total_checks']}\n"
        f"{e_heart()} {BOLD('Charged')}     : {user['total_charged']}\n"
        f"😀 {BOLD('Live')}        : {user['total_live']}\n"
        f"⚠️ {BOLD('Dead')}         : {user['total_dead']}\n"
        f"🚫 {BOLD('Banned')}      : {banned}\n"
        f"📅 {BOLD('Joined')}      : {user['joined_at']}\n\n"
        f"{DIVIDER}",
        parse_mode=ParseMode.HTML,
    )


@admin_only
async def ban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /ban <id> [reason] — ban a user."""
    if not ctx.args:
        await update.message.reply_text(
            "❌ Usage: /ban &lt;id&gt; [reason]", parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    reason = " ".join(ctx.args[1:]) if len(ctx.args) > 1 else "No reason provided"
    conn = ctx.bot_data["db"]

    # Don't ban owner
    config = ctx.bot_data["config"]
    if target_id == config["bot"]["owner_id"]:
        await update.message.reply_text("❌ Cannot ban the owner.")
        return

    conn.execute(
        "UPDATE users SET banned = 1, banned_reason = ? WHERE user_id = ?",
        (reason, target_id),
    )
    conn.commit()

    await update.message.reply_text(
        f"🚫 User {target_id} banned.\nReason: {reason}",
        parse_mode=ParseMode.HTML,
    )
    logger.info("Admin %d banned user %d: %s", update.effective_user.id, target_id, reason)


@admin_only
async def unban_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /unban <id> — unban a user."""
    if not ctx.args:
        await update.message.reply_text("❌ Usage: /unban &lt;id&gt;", parse_mode=ParseMode.HTML)
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    conn = ctx.bot_data["db"]
    conn.execute(
        "UPDATE users SET banned = 0, banned_reason = NULL WHERE user_id = ?",
        (target_id,),
    )
    conn.commit()

    await update.message.reply_text(f"✅ User {target_id} unbanned.")


@owner_only
async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /broadcast <msg> — broadcast to all users."""
    if not ctx.args:
        await update.message.reply_text("❌ Usage: /broadcast &lt;message&gt;", parse_mode=ParseMode.HTML)
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
        f"✅ Sites reloaded.\n"
        f"📊 All: {len(stores_all)} | $5: {len(stores_5)} | $10: {len(stores_10)}",
    )


@owner_only
async def settier_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /settier <id> <tier> <days> — manually set user tier."""
    if len(ctx.args) < 3:
        await update.message.reply_text(
            "❌ Usage: /settier &lt;id&gt; &lt;tier&gt; &lt;days&gt;\n"
            "Example: /settier 123456789 ULTRA 30",
            parse_mode=ParseMode.HTML,
        )
        return

    try:
        target_id = int(ctx.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid user ID.")
        return

    tier = ctx.args[1].upper()
    if tier not in TIER_CONFIG:
        await update.message.reply_text(
            f"❌ Invalid tier. Valid: {', '.join(TIER_CONFIG.keys())}",
        )
        return

    try:
        days = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text("❌ Days must be a number.")
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
        f"✅ User {target_id} set to {tier} for {days} days.\n"
        f"📅 Expires: {expires.strftime('%Y-%m-%d %H:%M UTC')}",
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

    lines = [f"🤍 <b>Recent Charged Cards ({len(rows)})</b>\n"]
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
    db_path = conn.execute("PRAGMA database_list").fetchone()["file"]

    backup_dir = Path("data/backup")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"aurora_backup_{timestamp}.db"

    try:
        shutil.copy2(db_path, str(backup_path))
        await update.message.reply_text(
            f"✅ Database backed up.\n📁 {backup_path}",
        )
        logger.info("DB backed up to %s", backup_path)
    except Exception as e:
        await update.message.reply_text(f"❌ Backup failed: {e}")