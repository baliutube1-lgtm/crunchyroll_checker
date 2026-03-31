import os
import re
import asyncio
from fastapi import FastAPI, Request

app = FastAPI()

# ====================== BOT TOKEN ======================
# ✅ MUST be set as Environment Variable in Railway
# NEVER hardcode the token here!
TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN environment variable is not set!\n"
        "Please add it in Railway → Variables → BOT_TOKEN"
    )

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")


# ====================== SAFE CALCULATOR ======================
def safe_evaluate(expression: str):
    """Safely evaluate simple math expressions (prevents code injection)."""
    try:
        expr = expression.strip()
        
        # Only allow: numbers, operators, parentheses, decimal point, spaces
        if not re.match(r"^[\d+\-*/().\s]+$", expr):
            return None
            
        # Super safe eval - no builtins, no variables
        result = eval(
            expr,
            {"__builtins__": None},  # Blocks all dangerous functions
            {}                       # No globals
        )
        
        # Convert to nice display (remove .0 if integer)
        if isinstance(result, float) and result.is_integer():
            return int(result)
        return result
    except:
        return None


# ====================== ROOT (Health Check) ======================
@app.get("/")
async def root():
    return {
        "status": "Bot is running 🚀",
        "webhook": "Ready",
        "message": "Your Telegram bot is live!"
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

        # ================= COMMANDS =================
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

        # ================= CALCULATOR =================
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
                    "Only these characters are allowed:\n"
                    "`0-9 + - * / ( )`"
                )

        # ================= UNKNOWN INPUT =================
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
