import os
import asyncio
import aiohttp
from aiohttp_socks import ProxyConnector
from fastapi import FastAPI, Request
from telegram import Update, Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Dispatcher, CommandHandler, MessageHandler, CallbackQueryHandler, filters

BOT_TOKEN = os.getenv("8677251975:AAGuEGmCIVQLUKO4j4dM7wGYMAExldG7ftM")

app = FastAPI()
bot = Bot(token=BOT_TOKEN)
dispatcher = Dispatcher(bot=bot, update_queue=None, use_context=True)

# ---------------- SETTINGS ----------------
TIMEOUT = 5
CONCURRENT_TASKS = 100

# ---------------- PROXY PARSER ----------------
def format_proxy(proxy):
    proxy = proxy.strip()

    if proxy.startswith("socks5://") or proxy.startswith("socks4://"):
        return proxy
    return f"http://{proxy}"

# ---------------- PROXY CHECK ----------------
async def check_proxy(proxy):
    proxy_url = format_proxy(proxy)

    try:
        if proxy_url.startswith("socks"):
            connector = ProxyConnector.from_url(proxy_url)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get("http://httpbin.org/ip", timeout=TIMEOUT) as r:
                    if r.status == 200:
                        return proxy, True
        else:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    "http://httpbin.org/ip",
                    proxy=proxy_url,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT)
                ) as r:
                    if r.status == 200:
                        return proxy, True
    except:
        return proxy, False

    return proxy, False

# ---------------- BULK CHECK ----------------
async def check_all(proxies):
    sem = asyncio.Semaphore(CONCURRENT_TASKS)

    async def task(proxy):
        async with sem:
            return await check_proxy(proxy)

    results = await asyncio.gather(*[task(p) for p in proxies])

    live = [p for p, s in results if s]
    dead = [p for p, s in results if not s]

    return live, dead

# ---------------- COMMAND ----------------
async def start(update: Update, context):
    await update.message.reply_text(
        "🔥 PRO Proxy Checker Bot\n\n"
        "Send proxies OR upload .txt file\n\n"
        "Supported:\n"
        "• HTTP\n• HTTPS\n• SOCKS4\n• SOCKS5"
    )

# ---------------- HANDLE TEXT ----------------
async def handle_text(update: Update, context):
    proxies = list(set(update.message.text.splitlines()))

    await process_proxies(update, context, proxies)

# ---------------- HANDLE FILE ----------------
async def handle_file(update: Update, context):
    file = await update.message.document.get_file()
    content = await file.download_as_bytearray()

    proxies = content.decode().splitlines()
    proxies = list(set(proxies))

    await process_proxies(update, context, proxies)

# ---------------- PROCESS ----------------
async def process_proxies(update, context, proxies):
    if len(proxies) > 5000:
        await update.message.reply_text("⚠️ Max limit: 5000 proxies")
        return

    msg = await update.message.reply_text("⏳ Checking proxies...")

    live, dead = await check_all(proxies)

    context.user_data["live"] = live  # store for download

    text = (
        f"✅ LIVE: {len(live)}\n"
        f"❌ DEAD: {len(dead)}\n\n"
        f"Sample LIVE:\n" + "\n".join(live[:20])
    )

    keyboard = [
        [InlineKeyboardButton("📥 Download LIVE", callback_data="download")],
        [InlineKeyboardButton("🔁 Recheck", callback_data="recheck")]
    ]

    await msg.edit_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ---------------- BUTTONS ----------------
async def buttons(update: Update, context):
    query = update.callback_query
    await query.answer()

    if query.data == "download":
        live = context.user_data.get("live", [])

        if not live:
            await query.message.reply_text("No live proxies.")
            return

        file_path = "live_proxies.txt"
        with open(file_path, "w") as f:
            f.write("\n".join(live))

        await query.message.reply_document(document=open(file_path, "rb"))

    elif query.data == "recheck":
        await query.message.reply_text("Send proxies again to recheck.")

# ---------------- HANDLERS ----------------
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
dispatcher.add_handler(MessageHandler(filters.Document.ALL, handle_file))
dispatcher.add_handler(CallbackQueryHandler(buttons))

# ---------------- WEBHOOK ----------------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    update = Update.de_json(data, bot)
    dispatcher.process_update(update)
    return {"ok": True}

@app.get("/")
def home():
    return {"status": "🔥 PRO Bot Running"}
