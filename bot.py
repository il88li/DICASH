import os
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import google.generativeai as genai

# --- الإعدادات ---
TOKEN = "8476324781:AAFljvUAT6GYoysL_mvl8rCoADMNXcH1n1g"
GEMINI_KEY = "AIzaSyABlAHgp2wpiH3OKzOHq2QKiI2xjIQaPAE"
# رابط الويب هوك الخاص بك
WEBHOOK_URL = f"https://dicash.onrender.com/webhook"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

# إعداد Gemini
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

PROMPT = "تقمص شخصية شاب مصري بائس وشيك. اكتب عبارة سوداء ساخرة (30 حرف) بقافية شعبية مصرية دارجة. أريد العبارة فقط."

# --- معالجة الويب هوك ---
@app.route('/webhook', methods=['POST'])
def getMessage():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return "!", 200
    return "Forbidden", 403

@app.route('/')
def index():
    return "Bot is running...", 200

# --- الأزرار والقوائم ---
def main_menu():
    markup = InlineKeyboardMarkup(row_width=1)
    markup.add(
        InlineKeyboardButton("📢 تعيين القناة", callback_data="set_channel"),
        InlineKeyboardButton("⏰ تعيين وقت النشر", callback_data="set_time"),
        InlineKeyboardButton("🖋️ توليد عبارة الآن", callback_data="generate_now")
    )
    return markup

@bot.message_handler(commands=['start'])
def start(message):
    bot.send_message(
        message.chat.id, 
        "أهلاً بك في لوحة تحكم بوت النكد الشيك.\nاختر ما تريد القيام به:", 
        reply_markup=main_menu()
    )

# --- معالجة الضغط على الأزرار ---
@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    if call.data == "generate_now":
        try:
            response = model.generate_content(PROMPT)
            quote = response.text.strip()
            bot.edit_message_text(f"العبارة المولدة:\n\n`{quote}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown", reply_markup=main_menu())
        except:
            bot.answer_callback_query(call.id, "فشل التوليد، حاول مجدداً.")
            
    elif call.data == "set_channel":
        bot.send_message(call.message.chat.id, "أرسل معرف القناة الآن (مثال: @mychannel أو ID القناة).")
        
    elif call.data == "set_time":
        bot.send_message(call.message.chat.id, "أرسل وقت النشر المطلوب (مثال: 12:00 PM).")

# --- تشغيل وتفعيل الويب هوك ---
bot.remove_webhook()
bot.set_webhook(url=WEBHOOK_URL)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
