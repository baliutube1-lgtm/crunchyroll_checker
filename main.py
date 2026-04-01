import os
import re
import asyncio
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
import telebot
from fastapi import FastAPI, Request

# SymPy units for conversion
import sympy.physics.units as units_mod
from sympy.physics.units.util import convert_to

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
chat_angle_mode: dict[int, str] = {}   # "rad" or "deg"

def add_to_history(chat_id: int, expression: str, result: any):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expression, "result": result})
    if len(chat_history[chat_id]) > 20:
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

    unit_dict = {
        "m": units_mod.meter, "meter": units_mod.meter,
        "km": units_mod.kilometer, "kilometer": units_mod.kilometer,
        "cm": units_mod.centimeter, "centimeter": units_mod.centimeter,
        "mm": units_mod.millimeter, "millimeter": units_mod.millimeter,
        "mile": units_mod.mile,
        "yard": units_mod.yard,
        "ft": units_mod.foot, "foot": units_mod.foot,
        "inch": units_mod.inch,
        "kg": units_mod.kilogram, "kilogram": units_mod.kilogram,
        "g": units_mod.gram, "gram": units_mod.gram,
        "s": units_mod.second, "second": units_mod.second,
        "min": units_mod.minute, "minute": units_mod.minute,
        "h": units_mod.hour, "hour": units_mod.hour,
        "joule": units_mod.joule,
        "watt": units_mod.watt,
    }

    return {
        **trig,
        "sinh": sp.sinh, "cosh": sp.cosh, "tanh": sp.tanh,
        "asinh": sp.asinh, "acosh": sp.acosh, "atanh": sp.atanh,
        "sqrt": sp.sqrt,
        "log": sp.log, "log10": lambda x: sp.log(x, 10),
        "exp": sp.exp,
        "pi": sp.pi, "e": sp.E,
        "abs": sp.Abs,
        "factorial": sp.factorial,
        "floor": sp.floor,
        "ceil": sp.ceiling,
        "mod": sp.Mod,
        "rad": sp.rad,
        "deg": sp.deg,
        "integrate": sp.integrate,
        "diff": sp.diff,
        "Matrix": sp.Matrix,
        "convert_to": convert_to,
        **unit_dict,
        **variables
    }

# ====================== UNIT CONVERSION HELPER ======================
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
    except Exception:
        return None

# ====================== LaTeX RENDERER ======================
def render_latex_image(latex_str: str) -> BytesIO:
    plt.rcParams['mathtext.fontset'] = 'cm'
    fig = plt.figure(figsize=(max(6, len(latex_str) // 8 + 1), 1.5))
    plt.text(0.5, 0.5, f"\( {latex_str} \)", fontsize=24, ha='center', va='center')
    plt.axis('off')
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=300, bbox_inches='tight', transparent=True, pad_inches=0.2)
    buf.seek(0)
    plt.close(fig)
    return buf

# ====================== ULTRA SCIENTIFIC EVALUATOR ======================
def evaluate_expression(expression: str, chat_id: int = None):
    try:
        expr = expression.strip().replace("^", "**")
        expr = re.sub(r'(\d+\.?\d*)\s*%', r'(\1/100)', expr)
        if not re.match(r"^[\d+\-*/().\s^,a-zA-Z=%[\],]+$", expr):
            return None

        safe_locals = get_safe_locals(chat_id)

        # Variable assignment
        if '=' in expr and expr.count('=') == 1:
            left, right = [part.strip() for part in expr.split('=', 1)]
            protected = {"sin","cos","tan","asin","acos","atan","sinh","cosh","tanh","asinh","acosh","atanh",
                         "sqrt","log","log10","exp","pi","e","abs","factorial","floor","ceil","mod","rad","deg",
                         "integrate","diff","Matrix","convert_to"}
            if left.isidentifier() and left not in protected:
                try:
                    val = sp.sympify(right, locals=safe_locals)
                    if chat_id is not None:
                        if chat_id not in chat_variables:
                            chat_variables[chat_id] = {}
                        chat_variables[chat_id][left] = val
                    return f"✅ **Variable set:** `{left}` = `{val}`"
                except:
                    pass

        # Equation solving
        if '=' in expr and expr.count('=') == 1:
            try:
                left, right = [part.strip() for part in expr.split('=', 1)]
                eq = sp.Eq(sp.sympify(left, locals=safe_locals), sp.sympify(right, locals=safe_locals))
                free_syms = list(eq.free_symbols)
                if len(free_syms) == 1:
                    sol = sp.solve(eq, free_syms[0])
                    return f"✅ **Solution:** `{free_syms[0]}` = `{sol[0]}`" if sol else "No real solution"
                return f"✅ Solutions: {sp.solve(eq)}"
            except:
                pass

        # Normal evaluation
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
    return {"status": "🚀 Full Scientific Calculator Bot LIVE", "version": "v5.0 - Matrices + Integrals + Derivatives + Units + LaTeX"}


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
                "🚀 **Scientific Calculator v5.0** — Everything you asked for!\n\n"
                f"📐 Angle mode: **{mode}**\n\n"
                "✅ **New powerful tools:**\n"
                "• `integrate(x**2, x)`  (indefinite)\n"
                "• `integrate(x**2, (x,0,1))`  (definite)\n"
                "• `diff(sin(x), x)`\n"
                "• Matrices: `Matrix([[1,2],[3,4]]).inv()` or `.det()`\n"
                "• Units: `5 km to m` or `1000 g to kg`\n"
                "• LaTeX: `/latex integrate(x^2, x)`\n\n"
                "Commands:\n"
                "`/deg` `/rad` `/plot` `/history` `/vars` `/clear` `/clearvars` `/latex`\n"
                "`/help` → Full list"
            )

        elif lower_text == "/deg":
            chat_angle_mode[chat_id] = "deg"
            await asyncio.to_thread(bot.send_message, chat_id, "📐 **DEGREE** mode activated\nsin(30) = 0.5")

        elif lower_text == "/rad":
            chat_angle_mode[chat_id] = "rad"
            await asyncio.to_thread(bot.send_message, chat_id, "📐 **RADIAN** mode activated\nsin(π/2) = 1")

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

        elif lower_text == "/clearvars":
            chat_variables[chat_id] = {}
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ All variables cleared!")

        elif lower_text == "/vars":
            vars_dict = chat_variables.get(chat_id, {})
            if not vars_dict:
                await asyncio.to_thread(bot.send_message, chat_id, "📌 No variables yet.\nTry: `x = 5`")
            else:
                txt = "📌 **Your Variables:**\n\n"
                for v, val in vars_dict.items():
                    txt += f"`{v}` = `{val}`\n"
                await asyncio.to_thread(bot.send_message, chat_id, txt)

        # ==================== PLOT ====================
        elif lower_text.startswith("/plot"):
            # (same as v4.0 - unchanged for brevity, full code kept in previous version)
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

        # ==================== LaTeX RENDERING ====================
        elif lower_text.startswith("/latex"):
            expr = text[6:].strip()
            if not expr:
                await asyncio.to_thread(bot.send_message, chat_id, "📐 Usage: `/latex integrate(x^2, x)` or any expression")
                return {"ok": True}
            try:
                safe = get_safe_locals(chat_id)
                sym_expr = sp.sympify(expr.replace("^", "**"), locals=safe)
                latex_str = sp.latex(sym_expr)
                result = evaluate_expression(expr, chat_id) or sym_expr
                buf = render_latex_image(latex_str)
                await asyncio.to_thread(
                    bot.send_photo,
                    chat_id,
                    photo=buf,
                    caption=f"📐 **LaTeX:** `{expr}`\n\n**Result:** `{result}`"
                )
                add_to_history(chat_id, f"latex({expr})", latex_str)
            except Exception:
                await asyncio.to_thread(bot.send_message, chat_id, f"❌ Could not render LaTeX for `{expr}`")

        # ==================== MAIN CALCULATOR ====================
        else:
            # First check for natural unit conversion
            unit_result = handle_unit_conversion(text, chat_id)
            if unit_result is not None:
                await asyncio.to_thread(bot.send_message, chat_id, unit_result)
                add_to_history(chat_id, text, unit_result)
            else:
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
                        "🤖 **Scientific Calculator Ready!**\n\n"
                        "Try these:\n"
                        "`integrate(x**2, x)`\n"
                        "`diff(cos(x), x)`\n"
                        "`Matrix([[1,2],[3,4]]).inv()`\n"
                        "`5 km to m`\n"
                        "`sin(30)` (DEG mode)\n"
                        "`200 * 5%`\n"
                        "`/latex x^2 + 3x + 2`\n"
                        "`/plot sin(x)`"
                    )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
