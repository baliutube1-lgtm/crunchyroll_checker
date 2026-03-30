import os
from fastapi import FastAPI, Request
import telebot
import requests

# ========================== YOUR TELEGRAM BOT TOKEN ==========================
BOT_TOKEN = '8704844082:AAGJYybxhWMugb6oiL3ZglL4K2xvtEd7cVI'   # ←←← REPLACE WITH YOUR REAL TOKEN

# ========================== LATEST CRUNCHYROLL CHECKER (March 2026) ==========================
def check_crunchyroll(email: str, password: str) -> str:
    try:
        # Updated client credentials (new as of 2026)
        login_resp = requests.post(
            'https://www.crunchyroll.com/auth/v1/token',
            data={
                'username': email,
                'password': password,
                'grant_type': 'password',
                'scope': 'offline_access'
            },
            headers={
                'User-Agent': 'Crunchyroll/4.10.0 Android/15 okhttp/4.12.1',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json'
            },
            auth=('anydazwaxclrocanwho3', '88gnIsucV-Q7sYrY29uOW_JGlMqx1mBN')
        )

        # Debug output if it still fails
        if login_resp.status_code != 200:
            error_text = login_resp.text[:500]
            return f"""❌ Login failed

Status Code: {login_resp.status_code}
Response:
{error_text}"""

        token = login_resp.json().get('access_token')

        # Get external_id
        profile_resp = requests.get(
            'https://www.crunchyroll.com/accounts/v1/me',
            headers={
                'User-Agent': 'Crunchyroll/4.10.0 Android/15 okhttp/4.12.1',
                'Authorization': f'Bearer {token}'
            }
        )
        external_id = profile_resp.json().get('external_id')

        # Check subscription
        sub_resp = requests.get(
            f'https://www.crunchyroll.com/subs/v1/subscriptions/{external_id}/benefits',
            headers={
                'User-Agent': 'Crunchyroll/4.10.0 Android/15 okhttp/4.12.1',
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
        return f"❌ Unexpected error: {str(e)}"


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
    return {"message": "✅ Bot running"}


@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    bot.reply_to(message, """👋 **Crunchyroll Subscription Checker Bot**

Send: `email:password`

**Example:** `john@gmail.com:MyPass123`""")


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

        bot.reply_to(message, "🔄 Checking...")

        result = check_crunchyroll(email, password)
        bot.reply_to(message, f"📊 **Result**\n\n{result}\n\n(Your credentials were **not** saved)")

    except Exception:
        bot.reply_to(message, "❌ Invalid format. Use `email:password`")


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
