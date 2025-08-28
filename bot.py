import logging
import json
from telegram import Update, WebAppInfo, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# --- CONFIGURATION ---
# Paste your bot's token here. Use the NEW one if you created one.
BOT_TOKEN = "PASTE_YOUR_TELEGRAM_BOT_TOKEN_HERE"

# IMPORTANT: Use a new cache-busting version number at the end of the URL.
# If you used ?v=6 last time, use ?v=7 now.
WEBAPP_URL = "https://philippthedeveloper.github.io/TelegramLocationMiniApp/?v=7"

# Enable logging to see errors and information in your console
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# This function handles the /start command.
# It replies with a button that opens your Mini App.
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton(
            "📍 Open Mini-App",
            web_app=WebAppInfo(url=WEBAPP_URL)
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Please click the button below to open the location selector:",
        reply_markup=reply_markup
    )


# This function handles the data sent back from the Mini App.
async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data_str = update.message.web_app_data.data
    logger.info("Raw WebApp data received: %s", data_str)

    try:
        # The data is a JSON string, so we parse it.
        data = json.loads(data_str)
        status = data.get('status')
        message = data.get('message')

        # Create a nice confirmation message to send back to the user.
        response_text = f"✅ Got it!\nStatus: {status}\nMessage: {message}"
        
        await update.message.reply_text(response_text)

    except json.JSONDecodeError:
        logger.error("Failed to parse JSON from WebApp data.")
        await update.message.reply_text("There was an error processing the data from the Mini App.")
    except Exception as e:
        logger.error("An unexpected error occurred: %s", e)
        await update.message.reply_text(f"An unexpected error occurred: {e}")


def main():
    logger.info("Starting bot...")
    
    # Create the Application and pass it your bot's token.
    application = ApplicationBuilder().token(BOT_TOKEN).build()

    # Register the command and message handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))

    # Start the bot using polling
    logger.info("Bot started and is now polling for updates.")
    application.run_polling()


if __name__ == '__main__':
    main()