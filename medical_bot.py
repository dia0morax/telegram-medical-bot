# -*- coding: utf-8 -*-

import sqlite3
import logging
import os # <--- تم إضافة هذه المكتبة لقراءة متغيرات البيئة

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, MessageHandler, Filters, CallbackContext

# --- الإعدادات الأساسية (قراءة من متغيرات البيئة) ---
# يجب عليك توفير هذه المتغيرات (BOT_TOKEN و OWNER_ID) في إعدادات الاستضافة (Render)
BOT_TOKEN = os.environ.get("BOT_TOKEN") 
OWNER_ID = int(os.environ.get("OWNER_ID")) if os.environ.get("OWNER_ID") else 0

# إعداد تسجيل الأخطاء
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- إدارة قاعدة البيانات ---

def db_connect():
    """الاتصال بقاعدة البيانات وإنشاء الجداول إذا لم تكن موجودة."""
    # ملاحظة: سيتم إنشاء ملف bot_database.db تلقائيًا في نفس مجلد البوت
    conn = sqlite3.connect('bot_database.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # جدول المشرفين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS admins (
            user_id INTEGER PRIMARY KEY
        )
    ''')
    
    # جدول الأزرار (لتخزين هيكل القوائم)
    # parent_id يحدد الزر الذي ينتمي إليه هذا الزر (0 يعني أنه في القائمة الرئيسية)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS buttons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text TEXT NOT NULL,
            parent_id INTEGER NOT NULL
        )
    ''')
    
    # جدول المحتوى المرتبط بالأزرار
    # content_type يمكن أن يكون: text, photo, document, link
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS content (
            button_id INTEGER PRIMARY KEY,
            content_type TEXT NOT NULL,
            content_value TEXT NOT NULL
        )
    ''')
    
    conn.commit()
    return conn, cursor

def is_admin(user_id):
    """التحقق مما إذا كان المستخدم مشرفًا."""
    if user_id == OWNER_ID:
        return True
    conn, cursor = db_connect()
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result is not None

# --- دوال الأوامر العامة والخاصة بالمالك/المشرفين ---

def start(update: Update, context: CallbackContext):
    """دالة البدء: تعرض القائمة الرئيسية للمستخدمين وقائمة الأوامر للمشرفين/المالك."""
    user = update.effective_user
    help_text = "أهلاً بك في بوت المحاضرات الطبية.\nاستخدم الأزرار أدناه لتصفح المواد.\n\n"
    
    # قائمة الأوامر الإدارية التي تظهر فقط للمشرفين والمالك
    if is_admin(user.id):
        help_text += (
            "===== أوامر الإدارة =====\n"
            "/help - عرض هذه الرسالة\n"
            "/addadmin <user_id> - إضافة مشرف جديد (للمالك فقط)\n"
            "/removeadmin <user_id> - إزالة مشرف (للمالك فقط)\n"
            "/addbutton <parent_id> <button_text> - إضافة زر جديد\n"
            "/setcontent <button_id> - (بالرد على رسالة) لربطها بالزر\n"
            "/deletebutton <button_id> - لحذف زر (سيحذف كل الأزرار والمحتوى الفرعي له)\n"
            "--------------------------\n"
            "ملاحظات هامة للمشرفين:\n"
            "- `parent_id`: استخدم 0 لإنشاء زر في القائمة الرئيسية.\n"
            "- الأرقام المعروضة بين قوسين بجانب الأزرار (مثل (1)) هي `button_id`.\n"
        )
        
    conn, cursor = db_connect()
    # جلب الأزرار في القائمة الرئيسية (parent_id = 0)
    cursor.execute("SELECT id, text FROM buttons WHERE parent_id = 0")
    main_buttons = cursor.fetchall()
    conn.close()

    keyboard = []
    for btn_id, btn_text in main_buttons:
        # إضافة ID الزر في التسمية للمشرفين لسهولة الإدارة
        display_text = f"{btn_text} ({btn_id})" if is_admin(user.id) else btn_text
        keyboard.append([InlineKeyboardButton(display_text, callback_data=f"nav_{btn_id}")])

    reply_markup = InlineKeyboardMarkup(keyboard)
    # استخدام edit_message_text لتجنب رسائل متكررة إذا كان المستخدم يضغط على /start مراراً
    if update.callback_query:
        update.callback_query.edit_message_text(help_text, reply_markup=reply_markup)
    else:
        update.message.reply_text(help_text, reply_markup=reply_markup)

def help_command(update: Update, context: CallbackContext):
    """يعرض نفس رسالة البدء."""
    start(update, context)

# --- دوال الإدارة (للمالك والمشرفين) ---

def add_admin(update: Update, context: CallbackContext):
    """إضافة مشرف جديد (للمالك فقط)."""
    user = update.effective_user
    if user.id != OWNER_ID:
        update.message.reply_text("هذا الأمر مخصص لمالك البوت فقط.")
        return

    try:
        new_admin_id = int(context.args[0])
        conn, cursor = db_connect()
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        update.message.reply_text(f"تمت إضافة المستخدم {new_admin_id} كمشرف بنجاح.")
    except (IndexError, ValueError):
        update.message.reply_text("الاستخدام: /addadmin <user_id>")

def remove_admin(update: Update, context: CallbackContext):
    """إزالة مشرف (للمالك فقط)."""
    # ... (الكود كما هو في الشرح السابق)

def add_button(update: Update, context: CallbackContext):
    """إضافة زر جديد لقائمة معينة."""
    user = update.effective_user
    if not is_admin(user.id):
        update.message.reply_text("هذا الأمر للمشرفين فقط.")
        return
        
    try:
        parent_id = int(context.args[0])
        button_text = " ".join(context.args[1:])
        if not button_text:
            raise ValueError
        
        conn, cursor = db_connect()
        # التأكد من أن الـ parent_id موجود إذا لم يكن 0
        if parent_id != 0:
            cursor.execute("SELECT id FROM buttons WHERE id = ?", (parent_id,))
            if cursor.fetchone() is None:
                update.message.reply_text(f"خطأ: الـ parent_id رقم {parent_id} غير موجود.")
                conn.close()
                return

        cursor.execute("INSERT INTO buttons (text, parent_id) VALUES (?, ?)", (button_text, parent_id))
        conn.commit()
        new_button_id = cursor.lastrowid
        conn.close()
        update.message.reply_text(f"تم إنشاء الزر '{button_text}' بنجاح. رقمه التعريفي هو: {new_button_id}")

    except (IndexError, ValueError):
        update.message.reply_text("الاستخدام الصحيح: /addbutton <parent_id> <النص المطلوب للزر>")

def set_content(update: Update, context: CallbackContext):
    """ربط محتوى (ملف، صورة، نص) بزر معين."""
    user = update.effective_user
    if not is_admin(user.id):
        update.message.reply_text("هذا الأمر للمشرفين فقط.")
        return
        
    if not update.message.reply_to_message:
        update.message.reply_text("يجب استخدام هذا الأمر بالرد على الرسالة التي تحتوي على المحتوى (صورة، ملف، نص، رابط).")
        return

    try:
        button_id = int(context.args[0])
        replied_message = update.message.reply_to_message
        content_type = ""
        content_value = ""

        if replied_message.text:
            content_type = "text"
            content_value = replied_message.text
        elif replied_message.photo:
            content_type = "photo"
            content_value = replied_message.photo[-1].file_id # أفضل جودة
        elif replied_message.document:
            content_type = "document"
            content_value = replied_message.document.file_id
        else:
            update.message.reply_text("نوع المحتوى هذا غير مدعوم حاليًا (يجب أن يكون نصًا أو صورة أو ملف).")
            return

        conn, cursor = db_connect()
        # التأكد من أن الزر موجود قبل ربط المحتوى به
        cursor.execute("SELECT id FROM buttons WHERE id = ?", (button_id,))
        if cursor.fetchone() is None:
            update.message.reply_text(f"خطأ: الزر رقم {button_id} غير موجود.")
            conn.close()
            return

        cursor.execute("INSERT OR REPLACE INTO content (button_id, content_type, content_value) VALUES (?, ?, ?)", 
                       (button_id, content_type, content_value))
        conn.commit()
        conn.close()
        update.message.reply_text(f"تم ربط المحتوى بنجاح بالزر رقم {button_id}.")

    except (IndexError, ValueError):
        update.message.reply_text("الاستخدام الصحيح: /setcontent <button_id> (مع الرد على رسالة المحتوى)")

def delete_button(update: Update, context: CallbackContext):
    """حذف زر وكل ما يتعلق به."""
    # ... (الكود كما هو في الشرح السابق)

# --- معالجة الضغط على الأزرار ---

def button_callback_handler(update: Update, context: CallbackContext):
    """تستجيب عند الضغط على أي زر في القوائم."""
    query = update.callback_query
    query.answer() 

    # إذا كان المستخدم يضغط على /start للرجوع للقائمة الرئيسية
    if query.data == "back_0":
        return start(update, context)

    data_parts = query.data.split('_')
    action = data_parts[0]
    button_id = int(data_parts[1])

    conn, cursor = db_connect()

    if action == "nav":
        # عرض الأزرار الفرعية أو إرسال المحتوى
        cursor.execute("SELECT id, text, parent_id FROM buttons WHERE parent_id = ?", (button_id,))
        sub_buttons = cursor.fetchall()
        
        cursor.execute("SELECT content_type, content_value FROM content WHERE button_id = ?", (button_id,))
        content = cursor.fetchone()

        if sub_buttons:
            # إذا كان هناك أزرار فرعية، اعرضها
            keyboard = []
            for btn_id, btn_text, _ in sub_buttons:
                # عرض ID الزر للمشرفين فقط
                display_text = f"{btn_text} ({btn_id})" if is_admin(query.from_user.id) else btn_text
                keyboard.append([InlineKeyboardButton(display_text, callback_data=f"nav_{btn_id}")])
            
            # زر الرجوع: نمرر الـ ID الخاص بالزر الحالي لكي نتمكن من العودة إليه (أب القائمة الحالية)
            keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{button_id}")])
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # جلب اسم الزر الحالي للعرض في رسالة
            cursor.execute("SELECT text FROM buttons WHERE id = ?", (button_id,))
            current_button_text = cursor.fetchone()[0]
            
            query.edit_message_text(text=f"**القائمة: {current_button_text}**\nاختر من الأزرار التالية:", 
                                     reply_markup=reply_markup, parse_mode='Markdown')
        
        elif content:
            # إذا كان هناك محتوى، أرسله للمستخدم
            content_type, content_value = content
            chat_id = query.message.chat_id
            
            # منع المستخدمين من تعديل الرسائل التي تحتوي على قوائم عند إرسال محتوى
            context.bot.send_message(chat_id=chat_id, text="... يتم إرسال المحتوى المطلوب ...")

            if content_type == "text":
                context.bot.send_message(chat_id=chat_id, text=content_value)
            elif content_type == "photo":
                context.bot.send_photo(chat_id=chat_id, photo=content_value)
            elif content_type == "document":
                context.bot.send_document(chat_id=chat_id, document=content_value)
            
            # بعد إرسال المحتوى، نعيد عرض نفس القائمة لسهولة التصفح
            # هنا يجب عليك استدعاء دالة عرض القائمة الفرعية مرة أخرى (نفس منطق nav)
            # للتبسيط، يمكننا إرسال رسالة نصية بسيطة:
            query.edit_message_text(text="تم إرسال المحتوى. يمكنك الاستمرار في التصفح.", 
                                     reply_markup=query.message.reply_markup)

        else:
            # الزر فارغ
            query.edit_message_text(text="هذا الزر فارغ حاليًا. يمكنك إضافة محتوى أو أزرار فرعية إليه.", 
                                     reply_markup=query.message.reply_markup)

    elif action == "back":
        # التعامل مع زر الرجوع
        
        #button_id هنا هو الـ ID الخاص بالزر الأب للقائمة الحالية (الزر الذي كنا داخله)
        cursor.execute("SELECT parent_id FROM buttons WHERE id = ?", (button_id,))
        result = cursor.fetchone()
        
        # إذا كان result هو None فهذا يعني أن الزر الأب محذوف، لذا نعود للرئيسية
        current_parent_id = result[0] if result is not None else 0 
        
        if current_parent_id == 0:
            # الرجوع إلى القائمة الرئيسية (parent_id = 0)
            conn.close()
            return start(update, context)

        # إذا لم يكن في القائمة الرئيسية، نذهب لأب الأب (القائمة السابقة)
        cursor.execute("SELECT id, text FROM buttons WHERE parent_id = ?", (current_parent_id,))
        buttons_to_show = cursor.fetchall()

        keyboard = []
        for btn_id, btn_text in buttons_to_show:
            display_text = f"{btn_text} ({btn_id})" if is_admin(query.from_user.id) else btn_text
            keyboard.append([InlineKeyboardButton(display_text, callback_data=f"nav_{btn_id}")])
        
        # زر الرجوع الجديد (يعود إلى أب القائمة السابقة)
        keyboard.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"back_{current_parent_id}")]) 
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        cursor.execute("SELECT text FROM buttons WHERE id = ?", (current_parent_id,))
        parent_button_text = cursor.fetchone()[0]
        
        query.edit_message_text(text=f"**القائمة: {parent_button_text}**\nاختر من الأزرار التالية:", 
                                 reply_markup=reply_markup, parse_mode='Markdown')
        

    conn.close()

# --- الدالة الرئيسية لتشغيل البوت ---

def main():
    """الدالة الرئيسية لتشغيل البوت."""
    
    # التحقق من وجود التوكن والـ ID
    if not BOT_TOKEN or OWNER_ID == 0:
        logger.error("خطأ: الرجاء التأكد من تعيين متغيرات البيئة BOT_TOKEN و OWNER_ID.")
        return

    updater = Updater(BOT_TOKEN)
    dispatcher = updater.dispatcher
    
    # ربط دوال الأوامر بمعالجات الأوامر
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("help", help_command))
    dispatcher.add_handler(CommandHandler("addadmin", add_admin))
    dispatcher.add_handler(CommandHandler("removeadmin", remove_admin))
    dispatcher.add_handler(CommandHandler("addbutton", add_button))
    dispatcher.add_handler(CommandHandler("setcontent", set_content))
    dispatcher.add_handler(CommandHandler("deletebutton", delete_button))

    # ربط دالة معالجة الضغط على الأزرار
    dispatcher.add_handler(CallbackQueryHandler(button_callback_handler))

    # بدء تشغيل البوت
    updater.start_polling()
    logger.info("Bot started polling...")
    updater.idle()

if __name__ == '__main__':
    main()
