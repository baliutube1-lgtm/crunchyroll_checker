import os
import re
import asyncio
import telebot                          # ←←← THIS WAS MISSING!
from fastapi import FastAPI, Request

app = FastAPI()

# ====================== BOT TOKEN ======================
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN environment variable is not set!\n"
        "Please add it in Railway → Variables → BOT_TOKEN"
    )

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")


# ====================== SAFE CALCULATOR ======================
def safe_evaluate(expression: str):
    """Safely evaluate simple math expressions."""
    try:
        expr = expression.strip()
        
        if not re.match(r"^[\d+\-*/().\s]+$", expr):
            return None
            
        result = eval(
            expr,
            {"__builtins__": None},
            {}
        )
        
        if isinstance(result, float) and result.is_integer():
            return int(result)
        return result
    except:
        return None


# ====================== ROOT ======================
@app.get("/")
async def root():
    return {
        "status": "Bot is running 🚀",
        "webhook": "Ready"
    }


# ====================== WEBHOOK ======================
@app.post("/webhook")
async def webhook(request: Request):
    try:
        data = await request.json()

        if "message" not in data:
            return {"ok": True}

        msg = data["message"]
        chat_id = msg["chat"]["id"]
        text = msg.get("text", "").strip()

        if not text:
            return {"ok": True}

        lower_text = text.lower()

        # Commands
        if lower_text in ["/start", "/help"]:
            user = msg.get("from", {})
            username = user.get("username")
            name = f"@{username}" if username else user.get("first_name", "there")

            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                f"Hello {name} 👋\n\n"
                "I'm a **simple calculator bot**!\n\n"
                "Just send any math like:\n"
                "• `5 + 3`\n"
                "• `12 * 8`\n"
                "• `100 / 4`\n"
                "• `(15 + 3) * 2`\n\n"
                "Type `/help` anytime."
            )

        # Calculator
        elif any(op in text for op in ["+", "-", "*", "/"]):
            result = safe_evaluate(text)
            
            if result is not None:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    f"✅ **Result:** `{result}`"
                )
            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "❌ Invalid expression\n\n"
                    "Only these characters allowed:\n"
                    "`0-9 + - * / ( )`"
                )

        # Unknown
        else:
            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                "🤖 Send me a calculation like:\n"
                "`5 + 3` or `100 / 4`\n\n"
                "Type `/help` for instructions."
            )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
