import re

with open("handlers/admin.py", "r") as f:
    code = f.read()

# Replace keys_cmd
keys_cmd_old = """@admin_only
async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle /keys [active] — list batch keys from key system v2.\"\"\"
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

    lines = [f"{hdr()}\\n\\n{frame('BATCH KEYS')}\\n"]
    for row in rows[:30]:
        status = "✅" if row["status"] == "unused" else "❌"
        redeemed = f"→ {row['redeemed_by']}" if row["redeemed_by"] else "unused"
        lines.append(
            f"{status} <code>{row['key']}</code> | {row['tier']} | "
            f"{row['duration_days']}d | {redeemed}"
        )

    if len(rows) > 30:
        lines.append(f"\\n... and {len(rows) - 30} more")
    lines.append(f"\\n{ftr()}")

    await update.message.reply_text(
        "\\n".join(lines), parse_mode=ParseMode.HTML,
    )"""

keys_cmd_new = """@admin_only
async def keys_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle /keys [active] — list batch keys from key system v2 with pagination.\"\"\"
    active_only = len(ctx.args) > 0 and ctx.args[0].lower() == "active"
    await _send_keys_page(update.message.reply_text, ctx, page=1, active_only=active_only)

async def _send_keys_page(send_func, ctx, page: int, active_only: bool):
    conn = ctx.bot_data["db"]
    limit = 15
    offset = (page - 1) * limit

    if active_only:
        total = conn.execute("SELECT COUNT(*) FROM batch_keys WHERE status = 'unused'").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM batch_keys WHERE status = 'unused' ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()
    else:
        total = conn.execute("SELECT COUNT(*) FROM batch_keys").fetchone()[0]
        rows = conn.execute(
            "SELECT * FROM batch_keys ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)
        ).fetchall()

    from templates.messages import format_error
    if not rows and page == 1:
        await send_func(format_error("No keys found."), parse_mode=ParseMode.HTML)
        return

    total_pages = max(1, (total + limit - 1) // limit)
    
    lines = [f"{hdr()}\\n\\n{frame('BATCH KEYS')}\\n"]
    for row in rows:
        status = "✅" if row["status"] == "unused" else "❌"
        redeemed = f"→ {row['redeemed_by']}" if row["redeemed_by"] else "unused"
        lines.append(
            f"{status} <code>{row['key']}</code> | {row['tier']} | "
            f"{row['duration_days']}d | {redeemed}"
        )
    lines.append(f"\\n{ftr()}")

    # Pagination Keyboard
    buttons = []
    cb_prefix = "keys_page_active_" if active_only else "keys_page_all_"
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"{cb_prefix}{page-1}"))
    buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"{cb_prefix}{page+1}"))
    
    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    await send_func("\\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)"""

# Replace charged_cmd
charged_cmd_old = """@admin_only
async def charged_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle /charged — show recent charged cards.\"\"\"
    conn = ctx.bot_data["db"]
    rows = conn.execute(
        "SELECT * FROM charged_cards ORDER BY checked_at DESC LIMIT 20"
    ).fetchall()

    if not rows:
        await update.message.reply_text("No charged cards recorded.")
        return

    lines = [f"{hdr()}\\n\\n{frame('RECENT CHARGED')}\\n"]
    for r in rows:
        lines.append(
            f"<code>{r['card_masked']}</code> | {r['gateway']} | "
            f"${r['price']} | {r['checked_at']}"
        )
    lines.append(f"\\n{ftr()}")

    await update.message.reply_text(
        "\\n".join(lines), parse_mode=ParseMode.HTML,
    )"""

charged_cmd_new = """@admin_only
async def charged_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle /charged — show recent charged cards with pagination.\"\"\"
    await _send_charged_page(update.message.reply_text, ctx, page=1)

async def _send_charged_page(send_func, ctx, page: int):
    conn = ctx.bot_data["db"]
    limit = 10
    offset = (page - 1) * limit
    
    total = conn.execute("SELECT COUNT(*) FROM charged_cards").fetchone()[0]
    rows = conn.execute(
        "SELECT * FROM charged_cards ORDER BY checked_at DESC LIMIT ? OFFSET ?", (limit, offset)
    ).fetchall()

    from templates.messages import format_error
    if not rows and page == 1:
        await send_func(format_error("No charged cards recorded."), parse_mode=ParseMode.HTML)
        return

    total_pages = max(1, (total + limit - 1) // limit)

    lines = [f"{hdr()}\\n\\n{frame('RECENT CHARGED')}\\n"]
    for r in rows:
        lines.append(
            f"<code>{r['card_masked']}</code> | {r['gateway']} | "
            f"${r['price']} | {r['checked_at']}"
        )
    lines.append(f"\\n{ftr()}")

    # Pagination Keyboard
    buttons = []
    if page > 1:
        buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"charged_page_{page-1}"))
    buttons.append(InlineKeyboardButton(f"{page}/{total_pages}", callback_data="ignore"))
    if page < total_pages:
        buttons.append(InlineKeyboardButton("Next ➡️", callback_data=f"charged_page_{page+1}"))
    
    markup = InlineKeyboardMarkup([buttons]) if buttons else None
    await send_func("\\n".join(lines), parse_mode=ParseMode.HTML, reply_markup=markup)

async def admin_pagination_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle inline button callback for admin pagination.\"\"\"
    query = update.callback_query
    
    # Check if ignore button
    if query.data == "ignore":
        await query.answer()
        return

    user = query.from_user
    config = ctx.bot_data["config"]
    from core.tier_manager import is_admin
    if not is_admin(user.id, config):
        await query.answer("Admin access required.", show_alert=True)
        return

    await query.answer()
    data = query.data

    try:
        if data.startswith("keys_page_active_"):
            page = int(data.replace("keys_page_active_", ""))
            await _send_keys_page(query.edit_message_text, ctx, page, active_only=True)
        elif data.startswith("keys_page_all_"):
            page = int(data.replace("keys_page_all_", ""))
            await _send_keys_page(query.edit_message_text, ctx, page, active_only=False)
        elif data.startswith("charged_page_"):
            page = int(data.replace("charged_page_", ""))
            await _send_charged_page(query.edit_message_text, ctx, page)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("Pagination error: %s", e)"""

if keys_cmd_old in code:
    code = code.replace(keys_cmd_old, keys_cmd_new)
if charged_cmd_old in code:
    code = code.replace(charged_cmd_old, charged_cmd_new)

with open("handlers/admin.py", "w") as f:
    f.write(code)

print("Pagination added to admin.py")
