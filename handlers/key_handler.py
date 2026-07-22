"""Key handlers — /genkey (admin), /redeem (users), /status.

/genkey <plan> <quantity> <duration_days> — admin generates batch
/redeem <KEY> — direct redeem
/redeem (reply to key message) — auto-picks next unused key
/status — shows user's active tier + expiry
"""

import logging
import asyncio
from datetime import datetime
from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from core.key_system import (
    generate_keys, validate_key_format, save_batch, get_next_unused_key,
    get_batch_by_message, redeem_batch_key, redeem_direct_key,
    check_cooldown, get_batch_status, get_user_tier_info,
    create_batch_table, TIER_CONFIG, RedemptionResult,
)
from core.database import is_banned, get_or_create_user
from core.tier_manager import is_admin, is_owner
from core.error_handler import safe_send
from templates.messages import (
    format_batch_keys_generated, format_batch_redeem_success,
    format_batch_all_redeemed, format_redeem_cooldown,
    format_key_not_found, format_key_already_redeemed,
    format_genkey_usage, format_status_user, format_key_error,
    format_banned, format_error,
)

logger = logging.getLogger(__name__)


async def genkey_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /genkey <plan> <quantity> <duration_days> — admin only."""
    user = update.effective_user
    conn = ctx.bot_data["db"]
    config = ctx.bot_data["config"]

    if not is_admin(user.id, config):
        await update.message.reply_text(
            "❌ Admin access required.", parse_mode=ParseMode.HTML,
        )
        return

    if len(ctx.args) < 3:
        await update.message.reply_text(format_genkey_usage(), parse_mode=ParseMode.HTML)
        return

    plan = ctx.args[0].upper()
    try:
        quantity = int(ctx.args[1])
        duration_days = int(ctx.args[2])
    except ValueError:
        await update.message.reply_text(format_genkey_usage(), parse_mode=ParseMode.HTML)
        return

    if plan not in TIER_CONFIG:
        await update.message.reply_text(
            f"❌ Invalid plan. Valid: {', '.join(TIER_CONFIG.keys())}",
        )
        return

    if quantity < 1 or quantity > 500:
        await update.message.reply_text("❌ Quantity must be 1-500.")
        return

    if duration_days < 1 or duration_days > 365:
        await update.message.reply_text("❌ Duration must be 1-365 days.")
        return

    # Ensure batch table exists
    create_batch_table(conn)

    # Generate keys
    keys = generate_keys(quantity)
    if len(keys) < quantity:
        await update.message.reply_text("❌ Failed to generate enough unique keys. Try again.")
        return

    # Save batch (message_id will be updated after sending)
    batch_id = save_batch(conn, keys, plan, duration_days, user.id)

    # Get card limit for this tier
    card_limit = TIER_CONFIG[plan]["card_limit"]

    # Format message with code block
    text = format_batch_keys_generated(plan, quantity, duration_days, keys, card_limit)

    # Send message
    sent_msg = await update.message.reply_text(text, parse_mode=ParseMode.HTML)

    # Update batch with message_id + chat_id for reply-to-redeem
    conn.execute(
        "UPDATE key_batches SET message_id = ?, chat_id = ? WHERE batch_id = ?",
        (sent_msg.message_id, sent_msg.chat_id, batch_id),
    )
    conn.commit()

    logger.info("Admin %d generated %d %s keys (%dd), batch %s",
                user.id, quantity, plan, duration_days, batch_id)


async def redeem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /redeem — direct key OR reply to key message."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    # Ensure batch table exists
    create_batch_table(conn)

    # Ensure user exists
    get_or_create_user(conn, user.id, user.username, user.first_name)

    # Check cooldown
    can_redeem, cooldown_str = check_cooldown(conn, user.id)
    if not can_redeem:
        await update.message.reply_text(
            format_redeem_cooldown(cooldown_str), parse_mode=ParseMode.HTML,
        )
        return

    # Case 1: Direct key /redeem AURORA-XXXX-XXXX-XXXX-XXXX
    if ctx.args:
        key = ctx.args[0].strip()
        result = redeem_direct_key(conn, key, user.id)
        await _send_redeem_result(update, ctx, result, conn)
        return

    # Case 2: Reply to key message with /redeem → auto-pick next unused
    if update.message.reply_to_message:
        replied = update.message.reply_to_message
        batch = get_batch_by_message(conn, replied.chat_id, replied.message_id)

        if batch:
            # Check if all redeemed
            status = get_batch_status(conn, batch["batch_id"])
            if status["remaining"] == 0:
                await update.message.reply_text(
                    format_batch_all_redeemed(), parse_mode=ParseMode.HTML,
                )
                return

            # Get next unused key
            key_row = get_next_unused_key(conn, batch["batch_id"])
            if not key_row:
                await update.message.reply_text(
                    format_batch_all_redeemed(), parse_mode=ParseMode.HTML,
                )
                return

            result = redeem_batch_key(conn, key_row, user.id)
            await _send_redeem_result(update, ctx, result, conn)
            return
        else:
            # Maybe the replied message contains a key in text
            replied_text = replied.text or ""
            # Try to find AURORA-XXXX pattern in replied message
            import re
            match = re.search(r"AURORA-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}", replied_text.upper())
            if match:
                key = match.group(0)
                result = redeem_direct_key(conn, key, user.id)
                await _send_redeem_result(update, ctx, result, conn)
                return

    # No args and no reply
    await update.message.reply_text(format_key_error(), parse_mode=ParseMode.HTML)


def _send_redeem_result(update, ctx, result: RedemptionResult, conn):
    """Send the appropriate redemption result message."""
    # Note: This is called from an async context but is itself sync.
    # We return the coroutine for the caller to await.
    if result.success:
        text = format_batch_redeem_success(
            tier=result.tier,
            duration=conn.execute(
                "SELECT duration_days FROM batch_keys WHERE key = ?",
                (result.key,),
            ).fetchone()["duration_days"],
            expires_str=result.expires_at,
            key=result.key,
            position=result.position,
            card_limit=result.card_limit,
        )
        logger.info("User %d redeemed key %s (%s)", update.effective_user.id, result.key, result.position)
        return update.message.reply_text(text, parse_mode=ParseMode.HTML)
    else:
        if "not found" in result.message.lower():
            return update.message.reply_text(
                format_key_not_found(), parse_mode=ParseMode.HTML,
            )
        elif "already" in result.message.lower():
            return update.message.reply_text(
                format_key_already_redeemed(), parse_mode=ParseMode.HTML,
            )
        else:
            return update.message.reply_text(
                format_error(result.message), parse_mode=ParseMode.HTML,
            )


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /status — show user's active tier + expiry."""
    user = update.effective_user
    conn = ctx.bot_data["db"]

    if is_banned(conn, user.id):
        await update.message.reply_text(format_banned(), parse_mode=ParseMode.HTML)
        return

    get_or_create_user(conn, user.id, user.username, user.first_name)

    info = get_user_tier_info(conn, user.id)
    cfg = TIER_CONFIG.get(info["tier"], TIER_CONFIG["FREE"])

    text = format_status_user(
        tier=info["tier"],
        expires=info["expires"],
        expired=info["expired"],
        card_limit=cfg["card_limit"],
        workers=cfg["workers"],
    )

    await update.message.reply_text(text, parse_mode=ParseMode.HTML)