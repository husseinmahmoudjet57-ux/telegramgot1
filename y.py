import asyncio
import os
from threading import Thread
from flask import Flask
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)



TOKEN = os.environ["BOT_TOKEN"]  # ضع التوكن في Secrets على Replit
OWNER_ID = int(os.environ.get("OWNER_ID", 5620426600))  # معرفك الشخصي

bot = Bot(token=TOKEN)
dp = Dispatcher()

# النماذج مع السعر
forms = {
    "نموذج 1": "1000 ل.س",
    "نموذج 2": "1500 ل.س",
    "نموذج 3": "2000 ل.س"
}

# أرقام الدفع
PAYMENT_NUMBERS = {
    "شام كاش": "0930XXXXXX",
    "سيرياتيل كاش": "0940XXXXXX"
}

BACK_BUTTON_TEXT = "🔙 رجوع"
ACCEPT_BUTTON_TEXT = "موافق ✅"

# تخزين بيانات المستخدمين والطلبات
user_selected_form = {}
user_selected_payment = {}
pending_orders = {}  # user_id: dict(form, payment, photo_file_id, username, button_message_id)
active_sessions = {}  # owner_id: user_id (جلسة إرسال الملف حالياً)
payment_approval = {}  # user_id: bool (هل وافق على الملاحظة)
can_send_photo = {}    # user_id: bool (هل يسمح بإرسال الصور)

# لوحات المفاتيح
def get_forms_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=form)] for form in forms.keys()],
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

def create_order_keyboard(user_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="أرسل الملف", callback_data=f"order_{user_id}"),
        InlineKeyboardButton(text="إزالة", callback_data=f"delete_{user_id}")
    ]])

# بدء البوت
@dp.message(CommandStart())
async def start(message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    if user_id == OWNER_ID:
        if pending_orders:
            for uid in pending_orders.keys():
                await send_order_to_owner(uid)
        else:
            await message.answer("لا توجد طلبات جديدة حالياً.")
    else:
        await message.answer("أهلاً في بوت باقة رياضيات سورية 👋\nاضغط على /forms لرؤية النماذج.")

# عرض النماذج للمشتري
@dp.message(Command(commands=["forms"]))
async def show_forms(message: Message):
    if not message.from_user:
        return
    if message.from_user.id == OWNER_ID:
        return
    await message.answer("اختر النموذج الذي تريد شراءه:", reply_markup=get_forms_keyboard())

# إرسال الطلب للمالك مع زر مستقل
async def send_order_to_owner(user_id: int):
    order = pending_orders[user_id]
    msg = await bot.send_photo(
        chat_id=OWNER_ID,
        photo=order["photo_file_id"],
        caption=(
            f"طلب جديد ⚡\n"
            f"المستخدم: @{order['username']}\n"
            f"النموذج: {order['form']}\n"
            f"طريقة الدفع: {order['payment']}"
        ),
        reply_markup=create_order_keyboard(user_id)
    )
    pending_orders[user_id]["button_message_id"] = msg.message_id

# التعامل مع المشتري والمالك
@dp.message()
async def handle_message(message: Message):
    if not message.from_user:
        return
    user_id = message.from_user.id
    text = message.text

    # المالك يرسل الملف للمشتري
    if user_id == OWNER_ID:
        if user_id in active_sessions:
            target_id = active_sessions[user_id]
            if message.document:
                await bot.send_document(chat_id=target_id, document=message.document.file_id)
            elif message.photo:
                await bot.send_photo(chat_id=target_id, photo=message.photo[-1].file_id)

            # إزالة زر الطلب بعد الإرسال
            button_message_id = pending_orders[target_id]["button_message_id"]
            await bot.edit_message_reply_markup(
                chat_id=OWNER_ID,
                message_id=button_message_id,
                reply_markup=None
            )

            # تأكيد للمالك
            await bot.send_message(
                chat_id=OWNER_ID,
                text=f"تم الإرسال ✅ للمستخدم @{pending_orders[target_id]['username']}"
            )

            # حذف الطلب من القوائم
            pending_orders.pop(target_id)
            active_sessions.pop(user_id)
        return

    # الرجوع
    if text == BACK_BUTTON_TEXT:
        payment_approval[user_id] = False
        can_send_photo[user_id] = False  # منع إرسال الصور بعد الرجوع
        if user_id in user_selected_payment:
            # رجوع من طريقة الدفع إلى النماذج
            user_selected_payment.pop(user_id)
        await message.answer("اختر النموذج الذي تريد شراءه:", reply_markup=get_forms_keyboard())
        return

    # اختيار نموذج
    if text in forms:
        user_selected_form[user_id] = text
        can_send_photo[user_id] = False  # إعادة تعطيل الصور حتى اختيار طريقة الدفع
        await message.answer(
            f"لقد اخترت {text} بسعر: {forms[text]}\nاختر طريقة الدفع:",
            reply_markup=get_payment_keyboard()
        )
        return

    # اختيار طريقة الدفع
    if text in ["شام كاش", "سيرياتيل كاش"]:
        if user_id not in user_selected_form:
            await message.answer("يرجى اختيار النموذج أولاً.")
            return
        user_selected_payment[user_id] = text
        payment_approval[user_id] = False
        can_send_photo[user_id] = False  # لن يسمح بإرسال الصور قبل الموافقة على الملاحظة

        # عرض الملاحظة أولاً قبل التفاصيل
        if text == "سيرياتيل كاش":
            note_text = (
                "⚠️ ملاحظة مهمة لسيرياتيل كاش:\n"
                "- يجب استخدام التحويل اليدوي من تطبيق اقرب إليك.\n"
                " أو من ماكينة الخدمة الذاتية لسيرياتيل\n"
                "- الحوالة يجب أن تكون من الرقم الشخصي حصراً."
            )
        else:
            note_text = "⚠️ ملاحظة: يرجى عدم تفعيل خيار إخفاء الهوية أثناء التحويل."

        keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text=ACCEPT_BUTTON_TEXT)],
                [KeyboardButton(text=BACK_BUTTON_TEXT)]
            ],
            resize_keyboard=True
        )
        await message.answer(note_text, reply_markup=keyboard)
        return

    # موافقة على الملاحظة
    if text == ACCEPT_BUTTON_TEXT:
        payment_approval[user_id] = True
        can_send_photo[user_id] = True  # السماح بإرسال الصور بعد الموافقة
        form_name = user_selected_form[user_id]
        payment = user_selected_payment[user_id]
        price = forms[form_name]
        payment_number = PAYMENT_NUMBERS[payment]
        await message.answer(
            f"لقد اخترت الدفع بـ {payment}.\n"
            f"الطلب: {form_name} بسعر {price}\n"
            f"رقم الحساب: {payment_number}\n"
            "يرجى تحويل المبلغ على الرقم أعلاه ثم إرسال صورة شاشة لعملية التحويل:",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text=BACK_BUTTON_TEXT)]], resize_keyboard=True)
        )
        return

    # إرسال صورة التحويل
    if message.photo:
        if not can_send_photo.get(user_id):
            await message.answer("يرجى اختيار طريقة الدفع أولاً قبل إرسال صورة التحويل.")
            return
        form_name = user_selected_form[user_id]
        payment = user_selected_payment[user_id]
        username = message.from_user.username if message.from_user and message.from_user.username else message.from_user.full_name

        pending_orders[user_id] = {
            "form": form_name,
            "payment": payment,
            "photo_file_id": message.photo[-1].file_id,
            "username": username
        }

        # إشعار للمالك مع زر مستقل لكل طلب
        await send_order_to_owner(user_id)

        await message.answer("تم استلام صورة التحويل ✅ سيتم مراجعة الطلب والرد في أقرب وقت ممكن.")
        return

# المالك يضغط على زر "أرسل الملف" أو "إزالة الرسالة"
@dp.callback_query(F.data.startswith(("order_", "delete_")))
async def handle_order_or_delete(query: CallbackQuery):
    if not query.from_user or query.from_user.id != OWNER_ID:
        return
    if not query.data:
        return

    action, user_id = query.data.split("_")
    user_id = int(user_id)

    if action == "order":
        active_sessions[query.from_user.id] = user_id
        await bot.send_message(
            chat_id=OWNER_ID,
            text=f"أرسل الملف الآن إلى @{pending_orders[user_id]['username']}"
        )
    elif action == "delete":
        # زر إزالة الطلب
        if user_id in pending_orders:
            await bot.delete_message(chat_id=OWNER_ID, message_id=pending_orders[user_id]["button_message_id"])
            pending_orders.pop(user_id)
    await query.answer()

# Flask app صغير للحفاظ على البوت شغال
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port= int(os.environ.get("PORT",3000))
    app.run(host="0.0.0.0", port=port)

# تشغيل Flask في Thread منفصل
Thread(target=run_flask).start()

# تشغيل البوت
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


