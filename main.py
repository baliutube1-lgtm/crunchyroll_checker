import os
import re
import asyncio
import math
import telebot
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

# ====================== IN-MEMORY HISTORY ======================
chat_history: dict[int, list[dict]] = {}

def add_to_history(chat_id: int, expression: str, result: any):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expression, "result": result})
    if len(chat_history[chat_id]) > 10:
        chat_history[chat_id].pop(0)


# ====================== ADVANCED SAFE CALCULATOR ======================
def safe_evaluate(expression: str):
    """Advanced safe evaluator with math functions, power, pi, e, etc."""
    try:
        expr = expression.strip().replace("^", "**")

        # Only safe characters allowed
        if not re.match(r"^[\d+\-*/().\s^,a-zA-Z]+$", expr):
            return None

        # Allowed functions & constants
        safe_dict = {
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "sqrt": math.sqrt,
            "log": math.log,
            "log10": math.log10,
            "exp": math.exp,
            "pi": math.pi,
            "e": math.e,
            "abs": abs,
            "round": round,
            "factorial": math.factorial,
            "pow": pow,
        }

        result = eval(
            expr,
            {"__builtins__": None},
            safe_dict
        )

        # Clean output
        if isinstance(result, float):
            if result.is_integer():
                return int(result)
            return round(result, 8)
        return result

    except Exception:  # Catch everything safely
        return None


# ====================== ROOT ======================
@app.get("/")
async def root():
    return {
        "status": "🚀 Advanced Calculator Bot is LIVE",
        "version": "Advanced v2.1 (fixed detection)"
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

        # ==================== COMMANDS ====================
        if lower_text in ["/start", "/help"]:
            user = msg.get("from", {})
            username = user.get("username")
            name = f"@{username}" if username else user.get("first_name", "there")

            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                f"Hello {name} 👋\n\n"
                "🚀 **Advanced Calculator Bot** ready!\n\n"
                "✅ Supported:\n"
                "• `5 + 3`, `100 / 4`\n"
                "• `2^8`, `sqrt(16)`\n"
                "• `sin(pi/2)`, `log(100)`, `factorial(5)`\n"
                "• `pi`, `e`\n\n"
                "Commands:\n"
                "`/history` → Last 10 results\n"
                "`/clear` → Clear history\n"
                "`/help` → This message"
            )

        elif lower_text == "/history":
            history = chat_history.get(chat_id, [])
            if not history:
                await asyncio.to_thread(bot.send_message, chat_id, "📜 No history yet.")
            else:
                txt = "📜 **Your History:**\n\n"
                for i, item in enumerate(reversed(history), 1):
                    txt += f"{i}. `{item['expr']}` = **{item['result']}**\n"
                await asyncio.to_thread(bot.send_message, chat_id, txt)

        elif lower_text == "/clear":
            chat_history[chat_id] = []
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ History cleared!")

        # ==================== CALCULATOR (FIXED) ====================
        else:
            # Try to evaluate everything that is not a command
            result = safe_evaluate(text)

            if result is not None:
                add_to_history(chat_id, text, result)
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    f"✅ **Result:** `{result}`"
                )
            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "🤖 Send a math expression like:\n"
                    "`5 + 3`, `sqrt(16)`, `2^8`, `sin(pi/2)`, `log(100)`\n\n"
                    "Type `/help` for more info"
                )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
