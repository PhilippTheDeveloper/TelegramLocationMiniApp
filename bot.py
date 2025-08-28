import os
import json
import logging
import math
import time
import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError

# Enable logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
BOT_TOKEN = os.environ.get('BOT_TOKEN')
WEB_APP_URL = f'https://philippthedeveloper.github.io/TelegramLocationMiniApp/?v={int(time.time())}'

if not BOT_TOKEN:
    logger.error("❌ BOT_TOKEN environment variable is required!")
    exit(1)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command"""
    user = update.effective_user
    first_name = user.first_name or "there"
    
    welcome_message = (
        f"🌟 Welcome {first_name}!\n\n"
        "📍 Use this bot to share your location with a custom radius.\n\n"
        "🗺️ Tap the button below to open the map and:\n"
        "• Drag the map to position the pin\n"
        "• Adjust the radius with the slider (0.1-10 km)\n"
        "• Tap 'Done' to send location back\n\n"
        "Let's get started! 🚀"
    )
    
    # Create Mini App button
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺️ Open Location Map", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    
    await update.message.reply_text(
        welcome_message, 
        reply_markup=keyboard,
        parse_mode='HTML'
    )
    
    logger.info(f"📱 /start command used by {first_name} ({update.effective_chat.id})")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = (
        "🤖 <b>Location Bot Help</b>\n\n"
        "<b>Commands:</b>\n"
        "• /start - Open the location map\n"
        "• /help - Show this help message\n\n"
        "<b>How to use:</b>\n"
        "1️⃣ Tap \"Open Location Map\" button\n"
        "2️⃣ Drag the map to position the fixed pin\n"
        "3️⃣ Adjust the radius with the slider\n"
        "4️⃣ Tap \"Done\" to send location back\n\n"
        "<b>Features:</b>\n"
        "📍 Fixed pin with draggable map\n"
        "📏 Adjustable radius (0.1-10 km)\n"
        "🎯 Real-time coverage display\n"
        "📱 Mobile-optimized interface\n\n"
        "Perfect for setting delivery zones! 🚀"
    )
    
    await update.message.reply_text(help_message, parse_mode='HTML')
    logger.info(f"❓ Help requested by user {update.effective_chat.id}")

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data from the Mini App"""
    user = update.effective_user
    first_name = user.first_name or "User"
    chat_id = update.effective_chat.id
    
    try:
        # Parse the data from Mini App
        data = json.loads(update.effective_message.web_app_data.data)
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        radius = data.get('radius')
        timestamp = data.get('timestamp')
        
        logger.info(f"📍 Location data received from {first_name}: {latitude}, {longitude}, {radius}km")
        
        # Validate data
        if not all([latitude, longitude, radius]):
            raise ValueError("Invalid location data received")
        
        # Format timestamp
        if timestamp:
            dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
            formatted_time = dt.strftime('%Y-%m-%d %H:%M:%S')
        else:
            formatted_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # Create location message
        location_message = (
            f"📍 <b>{first_name}'s Location</b>\n\n"
            f"🎯 <b>Coordinates:</b>\n"
            f"• Latitude: <code>{latitude:.6f}</code>\n"
            f"• Longitude: <code>{longitude:.6f}</code>\n\n"
            f"📏 <b>Radius:</b> {radius} km\n"
            f"🕒 <b>Shared:</b> {formatted_time}\n\n"
            f"🗺️ <a href='https://maps.google.com/maps?q={latitude},{longitude}'>Open in Google Maps</a>"
        )
        
        # Create action buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("🗺️ Google Maps", url=f"https://maps.google.com/maps?q={latitude},{longitude}"),
                InlineKeyboardButton("🧭 Directions", url=f"https://maps.google.com/maps?daddr={latitude},{longitude}")
            ],
            [
                InlineKeyboardButton("📋 Copy Coordinates", callback_data=f"copy_coords_{latitude}_{longitude}_{radius}")
            ],
            [
                InlineKeyboardButton("🗺️ Share New Location", web_app=WebAppInfo(url=WEB_APP_URL))
            ]
        ])
        
        # Send formatted location message
        await update.effective_message.reply_text(
            location_message,
            reply_markup=keyboard,
            parse_mode='HTML',
            disable_web_page_preview=False
        )
        
        # Send actual location pin
        await context.bot.send_location(
            chat_id=chat_id,
            latitude=latitude,
            longitude=longitude
        )
        
        # Calculate and send coverage area info
        area = math.pi * (float(radius) ** 2)
        circumference = 2 * math.pi * float(radius)
        
        coverage_message = (
            f"🔵 <b>Coverage Area</b>\n\n"
            f"The selected radius of <b>{radius} km</b> covers:\n"
            f"• Area: <b>{area:.2f} km²</b>\n"
            f"• Circumference: <b>{circumference:.2f} km</b>\n\n"
            f"Perfect for delivery zones, service areas, or meeting points! 🎯"
        )
        
        await update.effective_message.reply_text(coverage_message, parse_mode='HTML')
        
        logger.info(f"✅ Location processed successfully for user {chat_id}")
        
    except Exception as error:
        logger.error(f"❌ Error processing web app data: {error}")
        await update.effective_message.reply_text(
            "❌ Error processing location data. Please try again with the map."
        )

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle button clicks"""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    chat_id = update.effective_chat.id
    
    logger.info(f"🔘 Callback query: {data} from user {chat_id}")
    
    if data.startswith('copy_coords_'):
        # Extract coordinates from callback data
        parts = data.replace('copy_coords_', '').split('_')
        lat = float(parts[0])
        lng = float(parts[1])
        radius = parts[2]
        
        coords_text = (
            f"📍 Location Data:\n\n"
            f"Latitude: {lat:.6f}\n"
            f"Longitude: {lng:.6f}\n"
            f"Radius: {radius} km\n\n"
            f"🗺️ Google Maps: https://maps.google.com/maps?q={lat},{lng}"
        )
        
        # Send coordinates as copyable text
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"<code>{coords_text}</code>",
            parse_mode='HTML'
        )
        
        # Show confirmation
        await query.edit_message_reply_markup()
        await context.bot.send_message(
            chat_id=chat_id,
            text="📋 Coordinates sent as copyable text!"
        )

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle direct location messages"""
    location = update.message.location
    latitude = location.latitude
    longitude = location.longitude
    chat_id = update.effective_chat.id
    
    logger.info(f"📍 Direct location received from user {chat_id}: {latitude}, {longitude}")
    
    message = (
        f"📍 <b>Location Received!</b>\n\n"
        f"🎯 <b>Coordinates:</b>\n"
        f"• Latitude: <code>{latitude}</code>\n"
        f"• Longitude: <code>{longitude}</code>\n\n"
        f"💡 <i>Tip: Use the Mini App below to set a custom radius around this location!</i>"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺️ Open with Radius Selector", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    
    await update.message.reply_text(
        message,
        reply_markup=keyboard,
        parse_mode='HTML'
    )

async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle any text messages (fallback)"""
    if update.message.text.startswith('/'):
        return  # Skip commands
    
    fallback_message = (
        "🤖 Hi! I'm a location sharing bot.\n\n"
        "📍 Use /start to open the interactive map\n"
        "❓ Use /help for more information\n\n"
        "Or just send me your location and I'll help you set a radius! 🗺️"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🗺️ Open Location Map", web_app=WebAppInfo(url=WEB_APP_URL))]
    ])
    
    await update.message.reply_text(
        fallback_message,
        reply_markup=keyboard
    )

def main():
    """Start the bot with proper conflict handling"""
    logger.info("🚀 Starting Location Bot with conflict handling...")
    
    # Add delay to let old instances shut down completely
    logger.info("⏳ Waiting for any existing instances to shut down...")
    time.sleep(10)
    
    max_retries = 3
    retry_delay = 15
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Bot startup attempt {attempt + 1}/{max_retries}")
            
            # Create application with conflict handling
            application = Application.builder().token(BOT_TOKEN).build()
            
            # Add handlers
            application.add_handler(CommandHandler("start", start_command))
            application.add_handler(CommandHandler("help", help_command))
            application.add_handler(MessageHandler(filters.StatusUpdate.WEB_APP_DATA, handle_web_app_data))
            application.add_handler(CallbackQueryHandler(handle_callback_query))
            application.add_handler(MessageHandler(filters.LOCATION, handle_location))
            application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
            
            logger.info("✅ Location Bot is starting...")
            logger.info(f"🌐 Mini App URL: {WEB_APP_URL}")
            logger.info("📱 Send /start to begin...")
            
            # Start the bot with conflict handling
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,  # Drop any pending updates to avoid conflicts
                close_loop=False
            )
            
            # If we get here, the bot shut down normally
            logger.info("🛑 Bot shut down normally")
            break
            
        except Conflict as e:
            logger.warning(f"⚠️ Conflict detected on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error("❌ Max retries reached. Bot startup failed.")
                raise
                
        except Exception as e:
            logger.error(f"❌ Unexpected error on attempt {attempt + 1}: {e}")
            if attempt < max_retries - 1:
                logger.info(f"⏳ Waiting {retry_delay} seconds before retry...")
                time.sleep(retry_delay)
            else:
                raise

if __name__ == '__main__':
    main()