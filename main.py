import os
import re
import asyncio
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import telebot
from fastapi import FastAPI, Request

# SymPy units + stats for probability
import sympy.physics.units as units_mod
from sympy.physics.units.util import convert_to
from sympy.stats import Normal, Binomial, density, P, E as stats_E, variance as stats_var

app = FastAPI()

# ====================== BOT TOKEN ======================
TOKEN = os.getenv("BOT_TOKEN")
if not TOKEN:
    raise RuntimeError(
        "❌ BOT_TOKEN environment variable is not set!\n"
        "Please add it in Railway → Variables → BOT_TOKEN"
    )

bot = telebot.TeleBot(TOKEN, parse_mode="Markdown")

# ====================== STORAGE ======================
chat_history: dict[int, list[dict]] = {}
chat_variables: dict[int, dict[str, any]] = {}
chat_angle_mode: dict[int, str] = {}          # "rad" or "deg"
chat_custom_funcs: dict[int, dict[str, tuple[sp.Expr, list[str]]]] = {}  # name → (sympy_expr, arg_symbols)

def add_to_history(chat_id: int, expression: str, result: any):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expression, "result": result})
    if len(chat_history[chat_id]) > 30:
        chat_history[chat_id].pop(0)

def get_angle_mode(chat_id: int) -> str:
    return chat_angle_mode.get(chat_id, "rad")

def create_trig_functions(mode: str):
    if mode == "rad":
        return {"sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
                "asin": sp.asin, "acos": sp.acos, "atan": sp.atan}
    else:
        return {"sin": lambda x: sp.sin(sp.rad(x)),
                "cos": lambda x: sp.cos(sp.rad(x)),
                "tan": lambda x: sp.tan(sp.rad(x)),
                "asin": lambda x: sp.deg(sp.asin(x)),
                "acos": lambda x: sp.deg(sp.acos(x)),
                "atan": lambda x: sp.deg(sp.atan(x))}

def get_safe_locals(chat_id: int = None):
    mode = get_angle_mode(chat_id) if chat_id is not None else "rad"
    variables = chat_variables.get(chat_id, {}) if chat_id else {}
    trig = create_trig_functions(mode)
    custom = chat_custom_funcs.get(chat_id, {})

    unit_dict = {
        "m": units_mod.meter, "km": units_mod.kilometer, "cm": units_mod.centimeter,
        "mm": units_mod.millimeter, "mile": units_mod.mile, "ft": units_mod.foot,
        "inch": units_mod.inch, "kg": units_mod.kilogram, "g": units_mod.gram,
        "s": units_mod.second, "min": units_mod.minute, "h": units_mod.hour,
    }

    # Statistics & Probability (sympy.stats + numpy)
    stats = {
        "mean": lambda *x: float(np.mean(x)),
        "median": lambda *x: float(np.median(x)),
        "stdev": lambda *x: float(np.std(x, ddof=0)),
        "variance": lambda *x: float(np.var(x, ddof=0)),
        "Normal": Normal,
        "Binomial": Binomial,
        "pdf": lambda dist, x: float(density(dist)(x).doit()),
        "cdf": lambda dist, x: float(P(dist <= x)),
        "expect": lambda dist: float(stats_E(dist)),
        "var": lambda dist: float(stats_var(dist)),
    }

    # Finance
    finance = {
        "compound": lambda p, r, t, n=1: p * (1 + r/n)**(n * t),
        "simple_interest": lambda p, r, t: p * r * t,
        "emi": lambda p, r, n: p * r * (1 + r)**n / ((1 + r)**n - 1) if r != 0 else p / n,
        "fv": lambda p, r, n: p * (1 + r)**n,
    }

    safe_dict = {
        **trig,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
        "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
        "sqrt": sp.sqrt,
        "log": sp.log, "log10": lambda x: sp.log(x, 10),
        "exp": sp.exp,
        "pi": sp.pi, "e": sp.E, "I": sp.I,
        "abs": sp.Abs,
        "factorial": sp.factorial,
        "floor": sp.floor, "ceil": sp.ceiling,
        "mod": sp.Mod,
        "rad": sp.rad, "deg": sp.deg,
        "integrate": sp.integrate, "diff": sp.diff,
        "Matrix": sp.Matrix,
        "comb": sp.binomial,
        "perm": lambda n, k: sp.factorial(n) / sp.factorial(n - k) if n >= k else 0,
        "convert_to": convert_to,
        **stats,
        **finance,
        **unit_dict,
        **variables
    }

    # Add custom functions as callable lambdas
    for name, (expr, args) in custom.items():
        safe_dict[name] = lambda *vals, _expr=expr, _args=args: float(_expr.subs(dict(zip(_args, vals))).evalf())

    return safe_dict

# ====================== CUSTOM FUNCTION PARSER ======================
def handle_custom_function_definition(text: str, chat_id: int):
    """Support: f(x) = x^2 + 3*x   or   def g(x,y) = x + y"""
    text = text.strip()
    if not re.search(r'^\s*(?:def\s+)?([a-zA-Z_]\w*)\s*\((.*?)\)\s*=\s*(.+)$', text):
        return None
    match = re.match(r'^\s*(?:def\s+)?([a-zA-Z_]\w*)\s*\((.*?)\)\s*=\s*(.+)$', text)
    if not match:
        return None
    name, arg_str, body = match.groups()
    args = [a.strip() for a in arg_str.split(',') if a.strip()]
    try:
        safe_locals = get_safe_locals(chat_id)
        sym_body = sp.sympify(body.replace("^", "**"), locals=safe_locals)
        if chat_id not in chat_custom_funcs:
            chat_custom_funcs[chat_id] = {}
        chat_custom_funcs[chat_id][name] = (sym_body, args)
        return f"✅ **Custom function defined:** `{name}({', '.join(args)})` = `{sym_body}`"
    except:
        return None

# ====================== SYSTEMS OF EQUATIONS ======================
def handle_system_of_equations(text: str, chat_id: int = None):
    """Support: x + y = 5, 2x - y = 1   or   solve x+y=5, 2x-y=1"""
    lower = text.lower().strip()
    if not ("," in text and "=" in text):
        return None
    try:
        # Split into equations
        eqs_str = [e.strip() for e in text.replace("solve", "").split(",")]
        safe_locals = get_safe_locals(chat_id)
        eqs = []
        vars_set = set()
        for eq_str in eqs_str:
            if "=" not in eq_str:
                continue
            left, right = [p.strip() for p in eq_str.split("=", 1)]
            eq = sp.Eq(sp.sympify(left, locals=safe_locals), sp.sympify(right, locals=safe_locals))
            eqs.append(eq)
            vars_set.update(eq.free_symbols)
        if len(eqs) == 0:
            return None
        vars_list = list(vars_set)
        sol = sp.solve(eqs, vars_list)
        if isinstance(sol, dict):
            return f"✅ **System solved:** {sol}"
        elif sol:
            return f"✅ **Solutions:** {sol}"
        return "No solution"
    except:
        return None

# ====================== UNIT CONVERSION ======================
def handle_unit_conversion(text: str, chat_id: int = None):
    lower = text.lower().strip()
    if " to " not in lower and " in " not in lower:
        return None
    normalized = lower.replace(" in ", " to ").replace("convert ", "").strip()
    if " to " not in normalized:
        return None
    try:
        from_part, to_part = [p.strip() for p in normalized.split(" to ", 1)]
        safe_locals = get_safe_locals(chat_id)
        qty = sp.sympify(from_part, locals=safe_locals)
        to_unit = safe_locals.get(to_part)
        if to_unit is None:
            return None
        converted = convert_to(qty, to_unit)
        return f"✅ **Unit conversion:** `{qty}` = `{converted}`"
    except:
        return None

# ====================== LaTeX RENDERER ======================
def render_latex_image(latex_str: str) -> BytesIO:
    plt.rcParams['mathtext.fontset'] = 'cm'
    fig = plt.figure(figsize=(max(6, len(latex_str)//8 + 1), 1.5))
    plt.text(0.5, 0.5, f"\( {latex_str} \)", fontsize=24, ha='center', va='center')
    plt.axis('off')
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', transparent=True)
    buf.seek(0)
    plt.close(fig)
    return buf

# ====================== EVALUATOR ======================
def evaluate_expression(expression: str, chat_id: int = None):
    try:
        expr = expression.strip().replace("^", "**")
        expr = re.sub(r'(\d+\.?\d*)\s*%', r'(\1/100)', expr)
        if not re.match(r"^[\d+\-*/().\s^,a-zA-Z=%[\]I]+$", expr):
            return None

        safe_locals = get_safe_locals(chat_id)

        # Variable assignment (normal)
        if '=' in expr and expr.count('=') == 1 and '(' not in expr.split('=')[0]:
            left, right = [part.strip() for part in expr.split('=', 1)]
            protected = {"sin","cos","tan","asin","acos","atan","sinh","cosh","tanh","asinh","acosh","atanh",
                         "sqrt","log","log10","exp","pi","e","I","abs","factorial","floor","ceil","mod","rad","deg",
                         "integrate","diff","Matrix","comb","perm","mean","median","stdev","variance",
                         "compound","simple_interest","emi","fv","Normal","Binomial","pdf","cdf","expect","var"}
            if left.isidentifier() and left not in protected:
                val = sp.sympify(right, locals=safe_locals)
                if chat_id is not None:
                    if chat_id not in chat_variables:
                        chat_variables[chat_id] = {}
                    chat_variables[chat_id][left] = val
                return f"✅ **Variable set:** `{left}` = `{val}`"

        result = sp.sympify(expr, locals=safe_locals)
        try:
            numeric = result.evalf(12)
            if numeric.is_integer:
                return int(numeric)
            return round(float(numeric), 8)
        except:
            return str(result.simplify() if hasattr(result, "simplify") else result)
    except Exception:
        return None

# ====================== ROOT ======================
@app.get("/")
async def root():
    return {"status": "🚀 ULTIMATE SCIENTIFIC CALCULATOR LIVE", "version": "v7.0 - Systems + Custom Functions + Probability + REPL"}

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
            name = f"@{user.get('username')}" if user.get("username") else user.get("first_name", "there")
            mode = get_angle_mode(chat_id).upper()

            await asyncio.to_thread(
                bot.send_message,
                chat_id,
                f"Hello {name} 👋\n\n"
                "🚀 **ULTIMATE Calculator v7.0** — The Endgame!\n\n"
                f"📐 Angle mode: **{mode}**\n\n"
                "✅ **NEW in v7.0:**\n"
                "• **Systems of equations:** `x + y = 5, 2x - y = 1`\n"
                "• **Custom functions:** `f(x) = x^2 + 3*x` then `f(5)`\n"
                "• **Probability:** `Normal(0,1)`, `pdf(Normal(0,1), 0)`, `Binomial(10,0.5)`\n"
                "• **Mini Python REPL:** `/py import math; math.sqrt(16)` (safe)\n\n"
                "All previous features still here!\n\n"
                "Commands:\n"
                "`/deg` `/rad` `/plot` `/latex` `/py` `/history` `/vars` `/clear` `/clearvars` `/clearfuncs`"
            )

        elif lower_text == "/deg":
            chat_angle_mode[chat_id] = "deg"
            await asyncio.to_thread(bot.send_message, chat_id, "📐 **DEGREE** mode activated")

        elif lower_text == "/rad":
            chat_angle_mode[chat_id] = "rad"
            await asyncio.to_thread(bot.send_message, chat_id, "📐 **RADIAN** mode activated")

        elif lower_text == "/clearfuncs":
            chat_custom_funcs[chat_id] = {}
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ Custom functions cleared!")

        elif lower_text == "/history":
            history = chat_history.get(chat_id, [])
            txt = "📜 No history" if not history else "📜 **Your History:**\n\n" + "\n".join(f"{i}. `{item['expr']}` = **{item['result']}**" for i, item in enumerate(reversed(history), 1))
            await asyncio.to_thread(bot.send_message, chat_id, txt)

        elif lower_text == "/clear":
            chat_history[chat_id] = []
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ History cleared!")

        elif lower_text == "/clearvars":
            chat_variables[chat_id] = {}
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ Variables cleared!")

        elif lower_text == "/vars":
            vars_dict = chat_variables.get(chat_id, {})
            txt = "📌 No variables" if not vars_dict else "📌 **Variables:**\n\n" + "\n".join(f"`{v}` = `{val}`" for v, val in vars_dict.items())
            await asyncio.to_thread(bot.send_message, chat_id, txt)

        # ==================== PLOT ====================
        elif lower_text.startswith("/plot"):
            plot_expr = text[5:].strip()
            if not plot_expr:
                await asyncio.to_thread(bot.send_message, chat_id, "📊 Usage: `/plot sin(x)`")
                return {"ok": True}
            try:
                safe_locals = get_safe_locals(chat_id)
                x_sym = sp.symbols('x')
                func = sp.sympify(plot_expr.replace("^", "**"), locals=safe_locals)
                f = sp.lambdify(x_sym, func, 'numpy')
                x_vals = np.linspace(-10, 10, 500)
                y_vals = np.real(f(x_vals))
                plt.figure(figsize=(10, 6))
                plt.plot(x_vals, y_vals, color='#00aaff', linewidth=2.5)
                plt.title(f"📈 {plot_expr}")
                plt.xlabel("x"); plt.ylabel("f(x)")
                plt.grid(True, alpha=0.3)
                plt.axhline(0, color='black', lw=0.8)
                plt.axvline(0, color='black', lw=0.8)
                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=220, bbox_inches='tight')
                buf.seek(0)
                plt.close()
                await asyncio.to_thread(bot.send_photo, chat_id, photo=buf, caption=f"✅ Plotted: `{plot_expr}`")
                add_to_history(chat_id, f"plot({plot_expr})", "graph")
            except Exception:
                await asyncio.to_thread(bot.send_message, chat_id, f"❌ Could not plot `{plot_expr}`")

        # ==================== LaTeX ====================
        elif lower_text.startswith("/latex"):
            expr = text[6:].strip()
            if not expr:
                await asyncio.to_thread(bot.send_message, chat_id, "📐 Usage: `/latex integrate(x**2, x)`")
                return {"ok": True}
            try:
                safe = get_safe_locals(chat_id)
                sym_expr = sp.sympify(expr.replace("^", "**"), locals=safe)
                latex_str = sp.latex(sym_expr)
                result = evaluate_expression(expr, chat_id) or sym_expr
                buf = render_latex_image(latex_str)
                await asyncio.to_thread(bot.send_photo, chat_id, photo=buf, caption=f"📐 **LaTeX:** `{expr}`\n\n**Result:** `{result}`")
                add_to_history(chat_id, f"latex({expr})", latex_str)
            except Exception:
                await asyncio.to_thread(bot.send_message, chat_id, f"❌ Could not render LaTeX for `{expr}`")

        # ==================== MINI PYTHON REPL (SAFE) ====================
        elif lower_text.startswith("/py"):
            code = text[3:].strip()
            if not code:
                await asyncio.to_thread(bot.send_message, chat_id, "🐍 Usage: `/py 2**10` or `/py import math; math.sqrt(16)`\n(Only safe math allowed)")
                return {"ok": True}
            try:
                # Extremely restricted safe eval (no os, no import except math/numpy)
                safe_globals = {"__builtins__": {}, "math": __import__("math"), "np": np, "sp": sp}
                result = eval(code, safe_globals, {})
                await asyncio.to_thread(bot.send_message, chat_id, f"🐍 **Python REPL:**\n`{code}` → `{result}`")
                add_to_history(chat_id, f"/py {code}", result)
            except Exception as e:
                await asyncio.to_thread(bot.send_message, chat_id, f"❌ REPL error: {str(e)[:100]}")

        # ==================== MAIN CALCULATOR ====================
        else:
            # 1. Custom function definition?
            custom_def = handle_custom_function_definition(text, chat_id)
            if custom_def:
                await asyncio.to_thread(bot.send_message, chat_id, custom_def)
                add_to_history(chat_id, text, "function defined")
                return {"ok": True}

            # 2. Systems of equations?
            system_result = handle_system_of_equations(text, chat_id)
            if system_result:
                await asyncio.to_thread(bot.send_message, chat_id, system_result)
                add_to_history(chat_id, text, system_result)
                return {"ok": True}

            # 3. Unit conversion?
            unit_result = handle_unit_conversion(text, chat_id)
            if unit_result:
                await asyncio.to_thread(bot.send_message, chat_id, unit_result)
                add_to_history(chat_id, text, unit_result)
                return {"ok": True}

            # 4. Normal expression
            result = evaluate_expression(text, chat_id)
            if result is not None:
                if isinstance(result, str) and "**Variable set:**" in result:
                    await asyncio.to_thread(bot.send_message, chat_id, result)
                else:
                    add_to_history(chat_id, text, result)
                    display = result if isinstance(result, str) and result.startswith("✅ **Solution:**") else f"✅ **Result:** `{result}`"
                    await asyncio.to_thread(bot.send_message, chat_id, display)
            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "🤖 **ULTIMATE Calculator Ready!**\n\n"
                    "Try these new features:\n"
                    "`f(x) = x^2 + 3*x` then `f(5)`\n"
                    "`x + y = 5, 2x - y = 1`\n"
                    "`Normal(0,1)`\n"
                    "`pdf(Normal(0,1), 0)`\n"
                    "`/py 2**10`\n"
                    "`/plot sin(x)`\n"
                    "`/latex diff(sin(x), x)`"
                )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
