import os
import re
import asyncio
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import telebot
from fastapi import FastAPI, Request

# Units & stats
import sympy.physics.units as units_mod
from sympy.physics.units.util import convert_to
from sympy.stats import Normal, Binomial, density, P

app = FastAPI()

# ================= TOKEN =================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ================= STORAGE =================
chat_angle_mode = {}

# ================= HELP MENU =================
def get_help_message(name: str, mode: str) -> str:
    return f"""
👋 Hello {name}!

📘 *Calculator Help Menu*

━━━━━━━━━━━━━━━━━━━━━━
📐 Mode: `{mode.upper()}`
━━━━━━━━━━━━━━━━━━━━━━

🧮 *Basic*
`2+2`, `5^2`, `10/3`

📊 *Advanced*
`sqrt(16)`
`log(10)`
`factorial(5)`

📐 *Trigonometry*
`sin(30)`
`cos(60)`

Use:
`/deg` or `/rad`

━━━━━━━━━━━━━━━━━━━━━━
📈 *Calculus*
`diff(x^2,x)`
`integrate(x^2,x)`

━━━━━━━━━━━━━━━━━━━━━━
📊 *Statistics*
`mean(1,2,3)`
`variance(1,2,3)`

━━━━━━━━━━━━━━━━━━━━━━
🎲 *Probability*
`Normal(0,1)`
`pdf(Normal(0,1),0)`

━━━━━━━━━━━━━━━━━━━━━━
📏 *Unit Conversion*
`10 km to m`

━━━━━━━━━━━━━━━━━━━━━━
📊 *Graph*
`/plot sin(x)`

━━━━━━━━━━━━━━━━━━━━━━
🐍 *Python*
`/py 2**10`

━━━━━━━━━━━━━━━━━━━━━━

✅ Easy to use  
🔥 Try different math expressions!

"""

# ================= SAFE LOCALS =================
def get_safe_locals():
    return {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "sqrt": sp.sqrt,
        "log": sp.log,
        "exp": sp.exp,
        "pi": sp.pi,
        "e": sp.E,
        "factorial": sp.factorial,
        "diff": sp.diff,
        "integrate": sp.integrate,
        "mean": lambda *x: float(np.mean(x)),
        "variance": lambda *x: float(np.var(x)),
        "Normal": Normal,
        "Binomial": Binomial,
        "pdf": lambda d, x: float(density(d)(x).doit()),
        "cdf": lambda d, x: float(P(d <= x)),
        "convert_to": convert_to,
        "m": units_mod.meter,
        "km": units_mod.kilometer,
    }

# ================= EVALUATOR =================
def evaluate(expr):
    expr = expr.replace("^", "**")

    if not re.match(r"^[\d+\-*/().\s^,a-zA-Z0-9_=,%[\]]+$", expr):
        return None

    try:
        res = sp.sympify(expr, locals=get_safe_locals())
        return float(res.evalf())
    except:
        return None

# ================= ROOT =================
@app.get("/")
async def root():
    return {"status": "Bot is live 🚀"}

# ================= WEBHOOK =================
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    text = msg.get("text", "").strip()

    if not text:
        return {"ok": True}

    lower = text.lower()

    # ===== START MESSAGE =====
    if lower == "/start":
        await asyncio.to_thread(
            bot.send_message,
            chat_id,
            "👋 Welcome to Calculator 🤖\n\n"
            "Made by @Sudhakaran12\n\n"
            "👉 Click /help to see all features and how to use."
        )

    # ===== HELP MENU =====
    elif lower == "/help":
        user = msg.get("from", {})
        name = user.get("first_name", "User")
        mode = chat_angle_mode.get(chat_id, "rad")

        await asyncio.to_thread(
            bot.send_message,
            chat_id,
            get_help_message(name, mode)
        )

    # ===== DEG/RAD =====
    elif lower == "/deg":
        chat_angle_mode[chat_id] = "deg"
        await asyncio.to_thread(bot.send_message, chat_id, "📐 Degree mode ON")

    elif lower == "/rad":
        chat_angle_mode[chat_id] = "rad"
        await asyncio.to_thread(bot.send_message, chat_id, "📐 Radian mode ON")

    # ===== PLOT =====
    elif lower.startswith("/plot"):
        expr = text[5:].strip()
        try:
            x = sp.symbols('x')
            f = sp.lambdify(x, sp.sympify(expr), 'numpy')

            xs = np.linspace(-10, 10, 500)
            ys = f(xs)
            ys = np.where(np.isfinite(ys), ys, np.nan)

            plt.plot(xs, ys)
            buf = BytesIO()
            plt.savefig(buf, format='png')
            buf.seek(0)
            plt.close()

            await asyncio.to_thread(bot.send_photo, chat_id, buf)
        except:
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Plot error")

    # ===== PYTHON =====
    elif lower.startswith("/py"):
        code = text[3:].strip()
        if "import" in code or "__" in code:
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Unsafe code")
        else:
            try:
                res = eval(code, {"__builtins__": {}}, {})
                await asyncio.to_thread(bot.send_message, chat_id, str(res))
            except:
                await asyncio.to_thread(bot.send_message, chat_id, "❌ Error")

    # ===== NORMAL CALC =====
    else:
        result = evaluate(text)
        if result is not None:
            await asyncio.to_thread(bot.send_message, chat_id, f"✅ `{result}`")
        else:
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Invalid input")

    return {"ok": True}
