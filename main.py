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


# ====================== IN-MEMORY HISTORY (Advanced Feature) ======================
chat_history: dict[int, list[dict]] = {}  # chat_id → list of {"expr": str, "result": any}


def add_to_history(chat_id: int, expression: str, result: any):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expression, "result": result})
    # Keep only last 10 calculations
    if len(chat_history[chat_id]) > 10:
        chat_history[chat_id].pop(0)


# ====================== ADVANCED SAFE CALCULATOR ======================
def safe_evaluate(expression: str):
    """Advanced safe evaluator with math functions, power (^), pi, e, etc."""
    try:
        expr = expression.strip().replace("^", "**")   # Support 5^2 → 5**2

        # Only safe characters + function names
        if not re.match(r"^[\d+\-*/().\s^,a-zA-Z]+$", expr):
            return None

        # Allowed math functions & constants
        safe_dict = {
            "sin": math.sin,
            "cos": math.cos,
            "tan": math.tan,
            "sqrt": math.sqrt,
            "log": math.log,      # natural log
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
            {"__builtins__": None},   # Block dangerous stuff
            safe_dict
        )

        # Clean output
        if isinstance(result, float):
            if result.is_integer():
                return int(result)
            return round(result, 8)   # Max 8 decimal places
        return result

    except:
        return None


# ====================== ROOT (Health Check) ======================
@app.get("/")
async def root():
    return {
        "status": "🚀 Advanced Calculator Bot is LIVE",
        "version": "Advanced v2.0",
        "features": "Math functions + History + Safe eval"
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
                "🚀 **Advanced Calculator Bot** is ready!\n\n"
                "✅ **Supported:**\n"
                "• Basic: `5 + 3`, `100 / 4`\n"
                "• Power: `2^8` or `2**8`\n"
                "• Functions: `sqrt(16)`, `sin(30)`, `log(100)`, `pi`, `e`\n"
                "• `abs(-5)`, `round(3.14159)`, `factorial(5)`\n\n"
                "Commands:\n"
                "`/history` → Last 10 calculations\n"
                "`/clear` → Clear history\n"
                "`/help` → This message"
            )

        # ================= HISTORY =================
        elif lower_text == "/history":
            history = chat_history.get(chat_id, [])
            if not history:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "📜 No calculations yet.\nSend something like `5 + 3`"
                )
            else:
                msg_text = "📜 **Your Last Calculations:**\n\n"
                for i, item in enumerate(reversed(history), 1):
                    msg_text += f"{i}. `{item['expr']}` = **{item['result']}**\n"
                await asyncio.to_thread(bot.send_message, chat_id, msg_text)

        # ================= CLEAR HISTORY =================
        elif lower_text == "/clear":
            chat_history[chat_id] = []
            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                "🗑️ History cleared successfully!"
            )

        # ================= CALCULATOR =================
        elif any(op in text for op in ["+", "-", "*", "/", "^", "(", "sin", "cos", "tan", "sqrt", "log", "pi", "e"]):
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
                    "❌ Invalid expression\n\n"
                    "Allowed: numbers, `+ - * / ^ ( )` and functions like `sqrt`, `sin`, `log`, `pi` etc."
                )

        # ================= UNKNOWN =================
        else:
            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                "🤖 Send a math expression like:\n"
                "`5 + 3`, `sqrt(16)`, `2^8`, `sin(pi/2)`\n\n"
                "Type `/help` for full list."
            )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
