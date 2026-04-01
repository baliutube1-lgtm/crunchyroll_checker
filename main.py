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
from sympy.stats import Normal, Binomial, density, P, E as stats_E, variance as stats_var

app = FastAPI()

# ================= TOKEN =================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("❌ BOT_TOKEN not set")

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ================= STORAGE =================
chat_history = {}
chat_variables = {}
chat_angle_mode = {}
chat_custom_funcs = {}

# ================= HELP MENU =================
def get_help_message(name: str, mode: str) -> str:
    return f"""
👋 Hello {name}!

🚀 *ULTIMATE SCIENTIFIC CALCULATOR*

━━━━━━━━━━━━━━━━━━━━━━
📐 *Angle Mode:* `{mode.upper()}`
━━━━━━━━━━━━━━━━━━━━━━

🧮 *BASIC*
`2+2`, `5^2`, `10/3`

📊 *ADVANCED*
`sqrt(16)`, `log(10)`, `factorial(5)`

📐 *TRIG*
`sin(30)`, `cos(60)`

`/deg` `/rad`

━━━━━━━━━━━━━━━━━━━━━━
📈 *CALCULUS*
`diff(x^2,x)`
`integrate(x^2,x)`

📦 *MATRIX*
`Matrix([[1,2],[3,4]])`

🔢 *COMBINATORICS*
`comb(5,2)` `perm(5,2)`

📊 *STATS*
`mean(1,2,3)`
`variance(1,2,3)`

🎲 *PROBABILITY*
`Normal(0,1)`
`pdf(Normal(0,1),0)`

💰 *FINANCE*
`compound(1000,0.1,2)`
`emi(10000,0.1,12)`

📏 *UNITS*
`10 km to m`

📊 *GRAPH*
`/plot sin(x)`

📐 *LATEX*
`/latex diff(x^2,x)`

⚙️ *FUNCTIONS*
`f(x)=x^2`
`f(5)`

🧩 *SYSTEM*
`x+y=5,2x-y=1`

🐍 *PYTHON*
`/py 2**10`

━━━━━━━━━━━━━━━━━━━━━━
📂 *MEMORY*
`x=10` → `x+5`

━━━━━━━━━━━━━━━━━━━━━━
🗂 *COMMANDS*
`/history`
`/vars`
`/clear`
`/clearvars`
`/clearfuncs`

━━━━━━━━━━━━━━━━━━━━━━
🔥 Try:
`f(x)=x^2`
`f(10)`
`/plot x^2`

🚀 Enjoy!
"""

# ================= SAFE LOCALS =================
def get_safe_locals(chat_id=None):
    return {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "sqrt": sp.sqrt,
        "log": sp.log,
        "exp": sp.exp,
        "pi": sp.pi,
        "e": sp.E,
        "factorial": sp.factorial,
        "abs": sp.Abs,
        "diff": sp.diff,
        "integrate": sp.integrate,
        "Matrix": sp.Matrix,
        "comb": sp.binomial,
        "perm": lambda n, k: sp.factorial(n)/sp.factorial(n-k),
        "mean": lambda *x: float(np.mean(x)),
        "variance": lambda *x: float(np.var(x)),
        "Normal": Normal,
        "Binomial": Binomial,
        "pdf": lambda d, x: float(density(d)(x).doit()),
        "cdf": lambda d, x: float(P(d <= x)),
        "convert_to": convert_to,
        "m": units_mod.meter,
        "km": units_mod.kilometer,
        "kg": units_mod.kilogram,
        "g": units_mod.gram,
    }

# ================= EVALUATOR =================
def evaluate(expr, chat_id):
    expr = expr.replace("^", "**")

    if not re.match(r"^[\d+\-*/().\s^,a-zA-Z0-9_=,%[\]]+$", expr):
        return None

    try:
        res = sp.sympify(expr, locals=get_safe_locals(chat_id))
        return float(res.evalf())
    except:
        return None

# ================= ROOT =================
@app.get("/")
async def root():
    return {"status": "BOT LIVE 🚀"}

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

    # ===== HELP MENU =====
    if lower in ["/start", "/help"]:
        user = msg.get("from", {})
        name = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "there")
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
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Unsafe")
        else:
            try:
                res = eval(code, {"__builtins__": {}}, {})
                await asyncio.to_thread(bot.send_message, chat_id, str(res))
            except:
                await asyncio.to_thread(bot.send_message, chat_id, "❌ Error")

    # ===== NORMAL CALC =====
    else:
        result = evaluate(text, chat_id)
        if result is not None:
            await asyncio.to_thread(bot.send_message, chat_id, f"✅ `{result}`")
        else:
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Invalid input")

    return {"ok": True}
