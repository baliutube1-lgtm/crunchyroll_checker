import os
import re
import asyncio
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import telebot
from fastapi import FastAPI, Request
import signal

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

MAX_HISTORY = 30
MAX_CHATS = 1000

# ================= TIMEOUT =================
def timeout_handler(signum, frame):
    raise TimeoutError()

signal.signal(signal.SIGALRM, timeout_handler)

# ================= HELPERS =================
def add_to_history(chat_id, expr, result):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expr, "result": result})
    if len(chat_history[chat_id]) > MAX_HISTORY:
        chat_history[chat_id].pop(0)

def get_angle_mode(chat_id):
    return chat_angle_mode.get(chat_id, "rad")

def create_trig(mode):
    if mode == "rad":
        return {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
                "asin": sp.asin, "acos": sp.acos, "atan": sp.atan}
    return {
        "sin": lambda x: sp.sin(sp.rad(x)),
        "cos": lambda x: sp.cos(sp.rad(x)),
        "tan": lambda x: sp.tan(sp.rad(x)),
        "asin": lambda x: sp.deg(sp.asin(x)),
        "acos": lambda x: sp.deg(sp.acos(x)),
        "atan": lambda x: sp.deg(sp.atan(x)),
    }

def make_func(expr, args):
    return lambda *vals: float(expr.subs(dict(zip(args, vals))).evalf())

def get_safe_locals(chat_id=None):
    mode = get_angle_mode(chat_id)
    variables = chat_variables.get(chat_id, {})
    trig = create_trig(mode)
    custom = chat_custom_funcs.get(chat_id, {})

    stats = {
        "mean": lambda *x: float(np.mean(x)),
        "median": lambda *x: float(np.median(x)),
        "stdev": lambda *x: float(np.std(x)),
        "variance": lambda *x: float(np.var(x)),
        "Normal": Normal,
        "Binomial": Binomial,
        "pdf": lambda d, x: float(density(d)(x).doit()),
        "cdf": lambda d, x: float(P(d <= x)),
        "expect": lambda d: float(stats_E(d)),
        "var": lambda d: float(stats_var(d)),
    }

    finance = {
        "compound": lambda p, r, t, n=1: p * (1 + r/n)**(n*t),
        "simple_interest": lambda p, r, t: p*r*t,
        "emi": lambda p, r, n: p*r*(1+r)**n/((1+r)**n-1) if r != 0 else p/n,
        "fv": lambda p, r, n: p*(1+r)**n,
    }

    unit_dict = {
        "m": units_mod.meter,
        "km": units_mod.kilometer,
        "cm": units_mod.centimeter,
        "kg": units_mod.kilogram,
        "g": units_mod.gram,
        "s": units_mod.second,
    }

    safe = {
        **trig,
        "sqrt": sp.sqrt,
        "log": sp.log,
        "exp": sp.exp,
        "pi": sp.pi,
        "e": sp.E,
        "abs": sp.Abs,
        "factorial": sp.factorial,
        "integrate": sp.integrate,
        "diff": sp.diff,
        "Matrix": sp.Matrix,
        "comb": sp.binomial,
        "perm": lambda n, k: sp.factorial(n)/sp.factorial(n-k),
        "convert_to": convert_to,
        **stats,
        **finance,
        **unit_dict,
        **variables
    }

    for name, (expr, args) in custom.items():
        safe[name] = make_func(expr, args)

    return safe

# ================= CUSTOM FUNCTION =================
def handle_function(text, chat_id):
    match = re.match(r'^\s*(?:def\s+)?(\w+)\((.*?)\)\s*=\s*(.+)$', text)
    if not match:
        return None
    name, args, body = match.groups()
    args = [a.strip() for a in args.split(",")]

    try:
        expr = sp.sympify(body.replace("^", "**"), locals=get_safe_locals(chat_id))
        chat_custom_funcs.setdefault(chat_id, {})[name] = (expr, args)
        return f"✅ Function `{name}` defined"
    except:
        return None

# ================= SYSTEM =================
def handle_system(text, chat_id):
    if "," not in text or "=" not in text:
        return None
    try:
        eqs = []
        for eq in text.split(","):
            l, r = eq.split("=")
            eqs.append(sp.Eq(sp.sympify(l), sp.sympify(r)))
        sol = sp.solve(eqs)
        return f"✅ {sol}"
    except:
        return None

# ================= UNIT =================
def handle_unit(text, chat_id):
    if " to " not in text:
        return None
    try:
        a, b = text.split(" to ")
        qty = sp.sympify(a, locals=get_safe_locals(chat_id))
        unit = get_safe_locals(chat_id).get(b.strip())
        return f"✅ {convert_to(qty, unit)}"
    except:
        return None

# ================= EVAL =================
def evaluate(expr, chat_id):
    expr = expr.replace("^", "**")

    if not re.match(r"^[\d+\-*/().\s^,a-zA-Z0-9_=,%[\]]+$", expr):
        return None

    safe = get_safe_locals(chat_id)

    try:
        signal.alarm(2)
        res = sp.sympify(expr, locals=safe)
        signal.alarm(0)
    except:
        return None

    try:
        return float(res.evalf())
    except:
        return str(res)

# ================= ROOT =================
@app.get("/")
async def root():
    return {"status": "LIVE 🔥"}

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

    # ===== COMMANDS =====
    if lower == "/start":
        await asyncio.to_thread(bot.send_message, chat_id, "🚀 Ultimate Calculator v8 Ready!")

    elif lower.startswith("/plot"):
        expr = text[5:].strip()
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

    else:
        # priority handlers
        for handler in [handle_function, handle_system, handle_unit]:
            result = handler(text, chat_id)
            if result:
                await asyncio.to_thread(bot.send_message, chat_id, result)
                return {"ok": True}

        result = evaluate(text, chat_id)
        if result is not None:
            await asyncio.to_thread(bot.send_message, chat_id, f"✅ {result}")
        else:
            await asyncio.to_thread(bot.send_message, chat_id, "❌ Invalid input")

    return {"ok": True}
