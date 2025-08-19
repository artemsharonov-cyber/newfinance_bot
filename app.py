import os
import psycopg2
from psycopg2 import pool
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackContext, CallbackQueryHandler, MessageHandler, Filters

# Конфигурация PostgreSQL
DATABASE_URL = os.getenv('DATABASE_URL')
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)

# Инициализация БД
def init_db():
    conn = db_pool.getconn()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS transactions (
            user_id BIGINT,
            type TEXT,
            amount REAL,
            category TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS feedback (
            user_id BIGINT,
            message TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    db_pool.putconn(conn)

init_db()

# Токен бота
TOKEN = os.getenv('TELEGRAM_TOKEN')

# Категории для кнопок
CATEGORIES_EXPENSE = ['Еда', 'Транспорт', 'Развлечения', 'Жилье', 'Другое']
CATEGORIES_INCOME = ['Зарплата', 'Фриланс', 'Подарки', 'Другое']

# Команда /start
async def start(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    await update.message.reply_text(
        f'Привет! Я бот для трекинга финансов.\n'
        f'Добавляй траты: /add_expense сумма\n'
        f'Добавляй доходы: /add_income сумма\n'
        f'Смотри статистику: /stats\n'
        f'Оставь отзыв: /feedback\n'
        f'Поделись мной с друзьями! 😊'
    )

# Добавление расхода
async def add_expense(update: Update, context: CallbackContext):
    try:
        amount = float(context.args[0])
        context.user_data['amount'] = amount
        context.user_data['type'] = 'expense'
        
        keyboard = [[InlineKeyboardButton(cat, callback_data=cat) for cat in CATEGORIES_EXPENSE[i:i+2]] 
                   for i in range(0, len(CATEGORIES_EXPENSE), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(f'Выберите категорию для расхода {amount}:', reply_markup=reply_markup)
    except:
        await update.message.reply_text('Используй: /add_expense сумма (например, /add_expense 500)')

# Добавление дохода
async def add_income(update: Update, context: CallbackContext):
    try:
        amount = float(context.args[0])
        context.user_data['amount'] = amount
        context.user_data['type'] = 'income'
        
        keyboard = [[InlineKeyboardButton(cat, callback_data=cat) for cat in CATEGORIES_INCOME[i:i+2]] 
                   for i in range(0, len(CATEGORIES_INCOME), 2)]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(f'Выберите категорию для дохода {amount}:', reply_markup=reply_markup)
    except:
        await update.message.reply_text('Используй: /add_income сумма (например, /add_income 10000)')

# Обработка выбора категории
async def button_callback(update: Update, context: CallbackContext):
    query = update.callback_query
    await query.answer()
    
    category = query.data
    amount = context.user_data.get('amount')
    trans_type = context.user_data.get('type')
    user_id = query.from_user.id
    
    if amount and trans_type:
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO transactions (user_id, type, amount, category) VALUES (%s, %s, %s, %s)',
                       (user_id, trans_type, amount, category))
        conn.commit()
        db_pool.putconn(conn)
        
        await query.edit_message_text(text=f'{trans_type.capitalize()} {amount} в категории "{category}" добавлен.')
        context.user_data.clear()
    else:
        await query.edit_message_text(text='Ошибка: попробуйте заново.')

# Статистика
async def stats(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    conn = db_pool.getconn()
    cursor = conn.cursor()
    
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = %s AND type = %s', (user_id, 'income'))
    total_income = cursor.fetchone()[0] or 0
    cursor.execute('SELECT SUM(amount) FROM transactions WHERE user_id = %s AND type = %s', (user_id, 'expense'))
    total_expense = cursor.fetchone()[0] or 0
    balance = total_income - total_expense
    
    cursor.execute('SELECT category, SUM(amount) FROM transactions WHERE user_id = %s AND type = %s GROUP BY category', 
                   (user_id, 'expense'))
    categories = cursor.fetchall()
    
    reply = f'📊 Статистика:\nБаланс: {balance}\nДоходы: {total_income}\nРасходы: {total_expense}\n\nРасходы по категориям:'
    for cat, amt in categories:
        reply += f'\n{cat}: {amt}'
    if not categories:
        reply += '\nПока нет расходов.'
    
    db_pool.putconn(conn)
    await update.message.reply_text(reply)

# Отзыв
async def feedback(update: Update, context: CallbackContext):
    await update.message.reply_text('Напишите ваш отзыв или предложение, и я передам его создателю!')
    context.user_data['feedback_mode'] = True

# Обработка текстовых сообщений (для отзывов)
async def handle_message(update: Update, context: CallbackContext):
    if context.user_data.get('feedback_mode'):
        user_id = update.message.from_user.id
        message = update.message.text
        
        conn = db_pool.getconn()
        cursor = conn.cursor()
        cursor.execute('INSERT INTO feedback (user_id, message) VALUES (%s, %s)', (user_id, message))
        conn.commit()
        db_pool.putconn(conn)
        
        await update.message.reply_text('Спасибо за отзыв! Он передан создателю.')
        context.user_data['feedback_mode'] = False
        # Отправка отзыва тебе (замени YOUR_CHAT_ID на твой Telegram ID)
        await context.bot.send_message(chat_id='YOUR_CHAT_ID', text=f'Отзыв от {user_id}: {message}')
    else:
        await update.message.reply_text('Используй команды: /start, /add_expense, /add_income, /stats, /feedback')

# Главная функция
def main():
    application = Application.builder().token(TOKEN).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('add_expense', add_expense))
    application.add_handler(CommandHandler('add_income', add_income))
    application.add_handler(CommandHandler('stats', stats))
    application.add_handler(CommandHandler('feedback', feedback))
    application.add_handler(CallbackQueryHandler(button_callback))
    application.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))
    
    import asyncio
    async def set_webhook():
        webhook_url = f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}/webhook"
        await application.bot.set_webhook(webhook_url)
    
    asyncio.run(set_webhook())
    
    application.run_polling()

if __name__ == '__main__':
    main()
