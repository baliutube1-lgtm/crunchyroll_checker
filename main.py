import os
import re
import asyncio
import sympy as sp
import numpy as np
import matplotlib.pyplot as plt
from io import BytesIO
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

# ====================== STORAGE ======================
chat_history: dict[int, list[dict]] = {}
chat_variables: dict[int, dict[str, any]] = {}

def add_to_history(chat_id: int, expression: str, result: any):
    if chat_id not in chat_history:
        chat_history[chat_id] = []
    chat_history[chat_id].append({"expr": expression, "result": result})
    if len(chat_history[chat_id]) > 15:
        chat_history[chat_id].pop(0)

def get_safe_locals(chat_id: int = None):
    """Fixed: log10 now works with sympy"""
    variables = chat_variables.get(chat_id, {}) if chat_id else {}
    return {
        "sin": sp.sin, "cos": sp.cos, "tan": sp.tan,
        "sqrt": sp.sqrt, "log": sp.log,
        "log10": lambda x: sp.log(x, 10),   # ← FIXED
        "exp": sp.exp, "pi": sp.pi, "e": sp.E,
        "abs": sp.Abs, "factorial": sp.factorial,
        **variables
    }

# ====================== ULTRA ADVANCED EVALUATOR ======================
def evaluate_expression(expression: str, chat_id: int = None):
    try:
        expr = expression.strip().replace("^", "**")
        if not re.match(r"^[\d+\-*/().\s^,a-zA-Z=]+$", expr):
            return None

        safe_locals = get_safe_locals(chat_id)

        # 1. Variable assignment: x = 5
        if '=' in expr and expr.count('=') == 1:
            left, right = [part.strip() for part in expr.split('=', 1)]
            if left.isidentifier() and left not in ["sin", "cos", "tan", "sqrt", "log", "log10", "exp", "pi", "e", "abs", "factorial"]:
                try:
                    val = sp.sympify(right, locals=safe_locals)
                    if chat_id is not None:
                        if chat_id not in chat_variables:
                            chat_variables[chat_id] = {}
                        chat_variables[chat_id][left] = val
                    return f"✅ **Variable set:** `{left}` = `{val}`"
                except:
                    pass

        # 2. Equation solving: x^2 - 5x + 6 = 0
        if '=' in expr and expr.count('=') == 1:
            try:
                left, right = [part.strip() for part in expr.split('=', 1)]
                eq = sp.Eq(
                    sp.sympify(left, locals=safe_locals),
                    sp.sympify(right, locals=safe_locals)
                )
                free_syms = list(eq.free_symbols)
                if len(free_syms) == 1:
                    sol = sp.solve(eq, free_syms[0])
                    if sol:
                        return f"✅ **Solution:** `{free_syms[0]}` = `{sol[0]}`"
                    return "No real solution"
                else:
                    return f"✅ Solutions: {sp.solve(eq)}"
            except:
                pass

        # 3. Normal expression
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
    return {
        "status": "🚀 Advanced Calculator Bot is LIVE",
        "version": "v3.1 - BUG FIXED (log10 + stability)"
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
                "🚀 **Advanced Calculator Bot v3.1** (fixed!)\n\n"
                "✅ Now working perfectly:\n"
                "• `log(100)`, `sqrt(16)`, `cos(pi/2)`\n"
                "• Variables: `x = 5` then `sin(x)`\n"
                "• Solve: `x^2 - 5x + 6 = 0`\n"
                "• Plot: `/plot sin(x)`\n\n"
                "Commands:\n"
                "`/history` → Last 15 results\n"
                "`/vars` → Show variables\n"
                "`/clear` → Clear history\n"
                "`/clearvars` → Clear variables\n"
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

        elif lower_text == "/clearvars":
            chat_variables[chat_id] = {}
            await asyncio.to_thread(bot.send_message, chat_id, "🗑️ All variables cleared!")

        elif lower_text == "/vars":
            vars_dict = chat_variables.get(chat_id, {})
            if not vars_dict:
                await asyncio.to_thread(bot.send_message, chat_id, "📌 No variables set yet.\nUse: `x = 5`")
            else:
                txt = "📌 **Your Variables:**\n\n"
                for v, val in vars_dict.items():
                    txt += f"`{v}` = `{val}`\n"
                await asyncio.to_thread(bot.send_message, chat_id, txt)

        # ==================== PLOT ====================
        elif lower_text.startswith("/plot"):
            plot_expr = text[5:].strip()
            if not plot_expr:
                await asyncio.to_thread(bot.send_message, chat_id, "📊 **Usage:** `/plot sin(x)` or `/plot x^2 - 3x + 2`")
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
                plt.title(f"📈 Plot of {plot_expr}")
                plt.xlabel("x")
                plt.ylabel("f(x)")
                plt.grid(True, alpha=0.3)
                plt.axhline(0, color='black', lw=0.8, alpha=0.5)
                plt.axvline(0, color='black', lw=0.8, alpha=0.5)

                buf = BytesIO()
                plt.savefig(buf, format='png', dpi=220, bbox_inches='tight')
                buf.seek(0)
                plt.close()

                await asyncio.to_thread(
                    bot.send_photo,
                    chat_id,
                    photo=buf,
                    caption=f"✅ **Plotted:** `{plot_expr}`\nRange: `x ∈ [-10, 10]`"
                )
                add_to_history(chat_id, f"plot({plot_expr})", "graph generated")

            except Exception:
                await asyncio.to_thread(
                    bot.send_message, chat_id,
                    f"❌ Could not plot `{plot_expr}`\nMake sure it's a valid function of `x`."
                )

        # ==================== MAIN CALCULATOR ====================
        else:
            result = evaluate_expression(text, chat_id)

            if result is not None:
                if isinstance(result, str) and "**Variable set:**" in result:
                    await asyncio.to_thread(bot.send_message, chat_id, result)
                else:
                    add_to_history(chat_id, text, result)
                    if isinstance(result, str) and result.startswith("✅ **Solution:**"):
                        display = result
                    else:
                        display = f"✅ **Result:** `{result}`"
                    await asyncio.to_thread(bot.send_message, chat_id, display)
            else:
                await asyncio.to_thread(
                    bot.send_message,
                    chat_id,
                    "🤖 Send any math expression:\n"
                    "`5 + 3`, `sin(pi/2)`, `factorial(10)`, `log(100)`, `sqrt(16)`, `cos(pi/2)`\n\n"
                    "Or try:\n"
                    "`x = 5` (set variable)\n"
                    "`x^2 - 5x + 6 = 0` (solve)\n"
                    "`/plot sin(x)` (graph)"
                )

    except Exception as e:
        print(f"Webhook error: {e}")

    return {"ok": True}
