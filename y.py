import asyncio
import os
import json
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = int(os.environ.get("OWNER_ID", 8380675536))

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ===== تحميل النماذج من JSON
def load_forms():
    try:
        with open("forms.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {}

def save_forms():
    with open("forms.json", "w", encoding="utf-8") as f:
        json.dump(forms, f, ensure_ascii=False, indent=4)

forms = load_forms()

SECTIONS = {
    "الجزء الاول": ["النهايات","الاشتقاق","المتتاليات","نهاية المتتالية","التابع اللوغاريتمي","التابع الأسي","التكامل"],
    "الجزء الثاني": ["أشعة 1","أشعة 2","أشعة 3","الاعداد العقدية","تطبيقات العقدية","التحليل التوافقي","الاحتمالات"],
    "نماذج مختلطة (دمج وحدات)": [],
    "شوامل": []
}

PAYMENT_NUMBERS = {
    "شام كاش": "0930XXXXXX",
    "سيرياتيل كاش": "0940XXXXXX"
}

BACK_BUTTON_TEXT = "🔙 رجوع"
ACCEPT_BUTTON_TEXT = "موافق ✅"

user_selected_form = {}
user_selected_payment = {}
pending_orders = {}
active_sessions = {}
payment_approval = {}
can_send_photo = {}

user_section = {}
user_unit = {}

adding_session = {}

# ================= KEYBOARDS

def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=k)] for k in SECTIONS.keys()],
        resize_keyboard=True
    )

def units_menu(section):
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=u)] for u in SECTIONS[section]] + [[KeyboardButton(text=BACK_BUTTON_TEXT)]],
        resize_keyboard=True
    )

def forms_menu(section, unit=None):
    if unit:
        data = forms[section][unit]
    else:
        data = forms[section]

    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=f)] for f in data.keys()] + [[KeyboardButton(text=BACK_BUTTON_TEXT)]],
        resize_keyboard=True
    )

def get_payment_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="شام كاش")],
            [KeyboardButton(text="سيرياتيل كاش")],
            [KeyboardButton(text=BACK_BUTTON_TEXT)]
        ],
        resize_keyboard=True
    )

def create_order_keyboard(user_id):
    return InlineKeyboardMarkup(inline_keyboard=[[ 
        InlineKeyboardButton(text="أرسل الملف", callback_data=f"order_{user_id}"),
        InlineKeyboardButton(text="إزالة", callback_data=f"delete_{user_id}")
    ]])

# ================= START

@dp.message(CommandStart())
async def start(message: Message):
    if message.from_user.id == OWNER_ID:
        return
    await message.answer("اختر القسم:", reply_markup=main_menu())

# ================= ADD FORM

@dp.message(Command("addform"))
async def add_form_start(message: Message):
    if message.from_user.id != OWNER_ID:
        return
    adding_session[OWNER_ID] = {"step": "choose_section"}
    await message.answer("اختر القسم:", reply_markup=main_menu())

# ================= SEND ORDER OWNER

async def send_order_to_owner(user_id):
    order = pending_orders[user_id]
    msg = await bot.send_photo(
        OWNER_ID,
        order["photo_file_id"],
        caption=f"طلب جديد ⚡\nالمستخدم: @{order['username']}\nالنموذج: {order['form']}\nطريقة الدفع: {order['payment']}",
        reply_markup=create_order_keyboard(user_id)
    )
    pending_orders[user_id]["button_message_id"] = msg.message_id

# ================= MAIN HANDLER

@dp.message()
async def handle(message: Message):
    uid = message.from_user.id
    text = message.text

    # ===== نظام إضافة نموذج =====
    if uid == OWNER_ID and uid in adding_session:
        session = adding_session[uid]

        if session["step"] == "choose_section":
            session["section"] = text

            if text in ["نماذج مختلطة (دمج وحدات)", "شوامل"]:
                session["step"] = "enter_name"
                await message.answer("اكتب اسم النموذج:")
                return

            session["step"] = "choose_unit"
            await message.answer("اختر الوحدة:", reply_markup=units_menu(text))
            return

        if session["step"] == "choose_unit":
            session["unit"] = text
            session["step"] = "enter_name"
            await message.answer("اكتب اسم النموذج:")
            return

        if session["step"] == "enter_name":
            session["name"] = text
            session["step"] = "enter_price"
            await message.answer("اكتب السعر رقم فقط:")
            return

        if session["step"] == "enter_price":
            if not text.isdigit():
                await message.answer("اكتب رقم فقط.")
                return

            price = f"{text} ل.س"
            section = session["section"]

            if section in ["نماذج مختلطة (دمج وحدات)", "شوامل"]:
                forms[section][session["name"]] = price
            else:
                unit = session["unit"]
                forms[section][unit][session["name"]] = price

            save_forms()
            adding_session.pop(uid)
            await message.answer("تمت إضافة النموذج ✅")
            return

    # ===== بقية كودك كما هو =====

    if text == BACK_BUTTON_TEXT:
        can_send_photo[uid] = False
        await message.answer("اختر القسم:", reply_markup=main_menu())
        return

    if text in SECTIONS:
        user_section[uid] = text
        if SECTIONS[text]:
            await message.answer("اختر الوحدة:", reply_markup=units_menu(text))
        else:
            await message.answer("اختر النموذج:", reply_markup=forms_menu(text))
        return

    if uid in user_section and text in SECTIONS[user_section[uid]]:
        user_unit[uid] = text
        await message.answer("اختر النموذج:", reply_markup=forms_menu(user_section[uid], text))
        return

    # اختيار نموذج
    if uid in user_section:
        section = user_section[uid]
        unit = user_unit.get(uid)

        if unit and text in forms[section][unit]:
            user_selected_form[uid] = text
            price = forms[section][unit][text]
        elif text in forms[section]:
            user_selected_form[uid] = text
            price = forms[section][text]
        else:
            price = None

        if price:
            await message.answer(
                f"لقد اخترت {text} بسعر: {price}\nاختر طريقة الدفع:",
                reply_markup=get_payment_keyboard()
            )
            return

    if text in ["شام كاش","سيرياتيل كاش"]:
        user_selected_payment[uid]=text
        can_send_photo[uid]=False

        if text=="سيرياتيل كاش":
            note_text="⚠️ ملاحظة مهمة لسيرياتيل كاش:\n- يجب استخدام التحويل اليدوي من تطبيق اقرب إليك.\n أو من ماكينة الخدمة الذاتية لسيرياتيل\n- الحوالة يجب أن تكون من الرقم الشخصي حصراً."
        else:
            note_text="⚠️ ملاحظة: يرجى عدم تفعيل خيار إخفاء الهوية أثناء التحويل."

        await message.answer(note_text,reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=ACCEPT_BUTTON_TEXT)],[KeyboardButton(text=BACK_BUTTON_TEXT)]],
            resize_keyboard=True))
        return

    if text==ACCEPT_BUTTON_TEXT:
        can_send_photo[uid]=True
        f=user_selected_form[uid]
        p=user_selected_payment[uid]
        await message.answer(
            f"لقد اخترت الدفع بـ {p}.\nالطلب: {f}\nرقم الحساب: {PAYMENT_NUMBERS[p]}\nيرجى تحويل المبلغ على الرقم أعلاه ثم إرسال صورة لرسالة التحويل أو صورة لسجل التحويلات",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BACK_BUTTON_TEXT)]],resize_keyboard=True))
        return

    if message.photo:
        if not can_send_photo.get(uid):
            await message.answer("يرجى اختيار طريقة الدفع أولاً قبل إرسال صورة التحويل.")
            return

        pending_orders[uid]={
            "form":user_selected_form[uid],
            "payment":user_selected_payment[uid],
            "photo_file_id":message.photo[-1].file_id,
            "username":message.from_user.username or message.from_user.full_name
        }

        await send_order_to_owner(uid)
        await message.answer("تم استلام صورة التحويل ✅ سيتم مراجعة الطلب والرد في أقرب وقت ممكن.")
        return

# ================= OWNER BUTTONS

@dp.callback_query(F.data.startswith(("order_","delete_")))
async def owner_cb(q:CallbackQuery):
    action,uid=q.data.split("_")
    uid=int(uid)

    if action=="order":
        active_sessions[q.from_user.id]=uid
        await bot.send_message(OWNER_ID,f"أرسل الملف الآن إلى @{pending_orders[uid]['username']}")

    if action=="delete":
        await bot.delete_message(OWNER_ID,pending_orders[uid]["button_message_id"])
        pending_orders.pop(uid)

    await q.answer()

# ================= FLASK

app=Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port=int(os.environ.get("PORT",3000))
    app.run("0.0.0.0",port)

Thread(target=run_flask).start()

async def main():
    await dp.start_polling(bot)

if __name__=="__main__":
    asyncio.run(main())
