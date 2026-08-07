import re

with open("handlers/admin.py", "r") as f:
    code = f.read()

replacement = """@owner_only
async def broadcast_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    \"\"\"Handle /broadcast <msg> — broadcast to all users (with media support).\"\"\"
    
    use_copy = False
    reply_msg = update.message.reply_to_message
    
    if reply_msg:
        use_copy = True
    elif not ctx.args:
        await update.message.reply_text(f"{e_cross()} Usage: /broadcast &lt;message&gt; OR reply to a message", parse_mode=ParseMode.HTML)
        return

    message_text = " ".join(ctx.args) if ctx.args else ""
    
    conn = ctx.bot_data["db"]
    users = conn.execute(
        "SELECT user_id FROM users WHERE banned = 0"
    ).fetchall()

    status_msg = await update.message.reply_text(f"🚀 <b>Broadcasting to {len(users)} users...</b>", parse_mode=ParseMode.HTML)

    sent = 0
    failed = 0
    
    import asyncio
    sem = asyncio.Semaphore(25) # 25 concurrent sends respects Telegram flood limits
    
    async def _send_one(uid):
        nonlocal sent, failed
        async with sem:
            try:
                if use_copy:
                    await ctx.bot.copy_message(
                        chat_id=uid,
                        from_chat_id=reply_msg.chat_id,
                        message_id=reply_msg.message_id
                    )
                else:
                    await ctx.bot.send_message(
                        chat_id=uid,
                        text=f"📢 <b>Announcement</b>\\n\\n{message_text}",
                        parse_mode=ParseMode.HTML,
                    )
                sent += 1
            except Exception as e:
                failed += 1
                
    tasks = [_send_one(u["user_id"]) for u in users]
    await asyncio.gather(*tasks)

    await status_msg.edit_text(
        f"📢 Broadcast Complete.\\n\\n✅ Sent: {sent}\\n❌ Failed: {failed}",
        parse_mode=ParseMode.HTML,
    )"""

# Regex substitute the old broadcast_cmd
code = re.sub(
    r'@owner_only\nasync def broadcast_cmd\(update: Update, ctx: ContextTypes\.DEFAULT_TYPE\):.*?await asyncio\.sleep\(0\.05\)\s*# ~20 msg/sec, stay under Telegram\'s 30/sec limit\n\n    await update\.message\.reply_text\(\n        f"📢 Broadcast sent to \{sent\} users\.\\nFailed: \{failed\}",\n        parse_mode=ParseMode\.HTML,\n    \)',
    replacement,
    code,
    flags=re.DOTALL
)

with open("handlers/admin.py", "w") as f:
    f.write(code)

print("Broadcast upgraded")
