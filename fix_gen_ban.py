import re

with open("handlers/mass_check.py", "r") as f:
    code = f.read()

gen_logic = """    # Parse cards
    cards = parse_card_list(text)
    if not cards:
        await update.message.reply_text(
            format_error("No valid cards found in file."),
            parse_mode=ParseMode.HTML,
        )
        return ConversationHandler.END

    # Anti-Spam Generator Ban
    from collections import Counter
    sample = cards[:20]
    if len(sample) >= 5:
        num_cnt = Counter(c.number for c in sample)
        cvv_cnt = Counter(c.cvv for c in sample)
        top_num = num_cnt.most_common(1)[0][1]
        top_cvv = cvv_cnt.most_common(1)[0][1]
        
        reason = None
        if top_num >= 15:
            reason = f"Card number repeated {top_num}x in first 20 cards"
        elif top_cvv >= 15:
            reason = f"CVV repeated {top_cvv}x in first 20 cards"
            
        if reason:
            conn.execute("UPDATE users SET banned = 1, banned_reason = ? WHERE user_id = ?", (reason, user.id))
            conn.commit()
            await update.message.reply_text(
                format_error(f"You have been auto-banned for API abuse.\\nReason: {reason}"),
                parse_mode=ParseMode.HTML
            )
            try:
                owner_id = ctx.bot_data["config"]["bot"]["owner_id"]
                await ctx.bot.send_message(
                    chat_id=owner_id,
                    text=f"🚫 <b>AUTO-BANNED</b>\\nUser: {user.id} (@{user.username})\\nReason: {reason}",
                    parse_mode=ParseMode.HTML
                )
            except: pass
            return ConversationHandler.END"""

code = re.sub(r'    # Parse cards\n    cards = parse_card_list\(text\)\n    if not cards:\n        await update\.message\.reply_text\(\n            format_error\("No valid cards found in file\."\),\n            parse_mode=ParseMode\.HTML,\n        \)\n        return ConversationHandler\.END', gen_logic, code)

with open("handlers/mass_check.py", "w") as f:
    f.write(code)

print("Auto-ban added")
