import os
from fastapi import FastAPI, Request
import telebot
import requests

# ========================== PUT YOUR TELEGRAM BOT TOKEN HERE ==========================
BOT_TOKEN = '8704844082:AAGJYybxhWMugb6oiL3ZglL4K2xvtEd7cVI'   # ←←←←←←←←←←←←←←←←←←←←←←←←←←←← REPLACE WITH YOUR REAL TOKEN

# ========================== CRUNCHYROLL CHECKER ==========================
def check_crunchyroll(email: str, password: str) -> str:
    try:
        login_resp = requests.post(
            'https://beta-api.crunchyroll.com/auth/v1/token',
            data={
                'username': email,
                'password': password,
                'grant_type': 'password',
                'scope': 'offline_access'
            },
            headers={'User-Agent': 'Crunchyroll/3.0.0 Android/5.1.1 okhttp/3.12.1'},
            auth=('cr_android', '1cf35dc5-b286-4551-8835-d4b1b4258445')
        )

        if login_resp.status_code != 200:
            return "❌ Invalid email or password"

        token = login_resp.json().get('access_token')

        profile_resp = requests.get(
            'https://beta-api.crunchyroll.com/accounts/v1/me',
            headers={
                'User-Agent': 'Crunchyroll/3.0.0 Android/5.1.1 okhttp/3.12.1',
                'Authorization': f'Bearer {token}'
            }
        )
        external_id = profile_resp.json().get('external_id')

        sub_resp = requests.get(
            f'https://beta-api.crunchyroll.com/subs/v1/subscriptions/{external_id}/benefits',
            headers={
                'User-Agent': 'Crunchyroll/3.0.0 Android/5.1.1 okhttp/3.12.1',
                'Authorization': f'Bearer {token}'
            }
        )

        if sub_resp.status_code == 200 and sub_resp.json().get('items'):
            benefit = sub_resp.json()['items'][0].get('benefit')
            if benefit == 'cr_premium':
                return "✅ **Premium Active**"
            else:
                return "⚠️ Free / Trial account"
        else:
            return "🔴 No active subscription"

    except Exception as e:
        return f"❌ Error occurred: {str(e)}"


# ========================== FASTAPI + TELEGRAM ==========================
app = FastAPI(title="Crunchyroll Checker Bot")
bot = telebot.TeleBot(BOT_TOKEN)


@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    update = telebot.types.Update.de_json(data)
    bot.process_new_updates([update])
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "✅ Crunchyroll Checker Bot is running with FastAPI + Uvicorn"}


# ========================== MESSAGE HANDLERS ==========================
@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, """👋 **Crunchyroll Subscription Checker Bot**

Just send your login details in this exact format:

`email:password`

**Example:**
`john@gmail.com:MyPass123`

⚠️ **Security note:**  
Credentials are used only for this one check and are **not stored**.""")


@bot.message_handler(func=lambda message: True)
def handle_credentials(message):
    text = message.text.strip()
    if ':' not in text:
        return

    try:
        email, password = [x.strip() for x in text.split(':', 1)]

        if not email or not password:
            bot.reply_to(message, "❌ Email and password cannot be empty!")
            return

        bot.reply_to(message, "🔄 Checking your Crunchyroll account...")

        result = check_crunchyroll(email, password)
        bot.reply_to(message, f"📊 **Result**\n\n{result}\n\n(Your credentials were **not** saved)")

    except Exception:
        bot.reply_to(message, "❌ Invalid format.\nPlease send exactly like: `email:password`")
