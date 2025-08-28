import os
import json
import logging
import math
import time
import asyncio
import aiohttp
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, ContextTypes, filters
from telegram.error import Conflict, NetworkError

# Import our URL builder
from url_builder import ImmobilienScout24URLBuilder

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

# Initialize URL builder
url_builder = ImmobilienScout24URLBuilder()

# User session storage (in production, use Redis or database)
user_sessions: Dict[int, Dict[str, Any]] = {}

def get_user_session(user_id: int) -> Dict[str, Any]:
    """Get or create user session"""
    if user_id not in user_sessions:
        user_sessions[user_id] = {
            'step': 'start',
            'mode': 'location',  # 'location' or 'apartment'
            'data': {
                'viertel': None,
                'plz_list': [],
                'viertel_coords': None,
                'coordinates': None,
                'radius': None,
                'budget': None,
                'space': None,
                'rooms': None,
                'floors': None,
                'extras': {
                    'garden': False,
                    'balcony': False,
                    'cellar': False,
                    'pets': False,
                    'no_swaps': True,  # default enabled
                    'hide_promoted': True  # default enabled
                }
            }
        }
    return user_sessions[user_id]

def reset_user_session(user_id: int, mode: str = 'location'):
    """Reset user session to start state"""
    user_sessions[user_id] = {
        'step': 'viertel' if mode == 'apartment' else 'start',
        'mode': mode,
        'data': {
            'viertel': None,
            'plz_list': [],
            'viertel_coords': None,
            'coordinates': None,
            'radius': None,
            'budget': None,
            'space': None,
            'rooms': None,
            'floors': None,
            'extras': {
                'garden': False,
                'balcony': False,
                'cellar': False,
                'pets': False,
                'no_swaps': True,
                'hide_promoted': True
            }
        }
    }

async def search_viertel_info(viertel_name: str) -> Dict[str, Any]:
    """Search for Viertel information using web search"""
    try:
        queries = [
            f'"{viertel_name}" Berlin PLZ postal code coordinates',
            f'Berlin {viertel_name} postleitzahl coordinates',
            f'{viertel_name} Berlin district PLZ location'
        ]

        async with aiohttp.ClientSession() as session:
            for query in queries:
                try:
                    params = {
                        'q': f'{viertel_name}, Berlin, Germany',
                        'format': 'json',
                        'limit': 1,
                        'accept-language': 'en',
                        'addressdetails': 1
                    }
                    
                    async with session.get('https://nominatim.openstreetmap.org/search', 
                                         params=params) as response:
                        if response.status == 200:
                            data = await response.json()
                            
                            if data and len(data) > 0:
                                result = data[0]
                                coords = {
                                    'lat': float(result['lat']),
                                    'lon': float(result['lon'])
                                }

                                plz_list = []
                                if result.get('address') and result['address'].get('postcode'):
                                    plz_list = [result['address']['postcode']]
                                else:
                                    plz_list = url_builder.get_plz_for_viertel(viertel_name)

                                return {
                                    'found': True,
                                    'viertel': viertel_name,
                                    'coordinates': coords,
                                    'plz_list': plz_list,
                                    'display_name': result['display_name']
                                }
                                
                except Exception as e:
                    logger.error(f"Search attempt failed for query: {query}, error: {e}")
                    continue

        plz_list = url_builder.get_plz_for_viertel(viertel_name)
        if plz_list:
            return {
                'found': True,
                'viertel': viertel_name,
                'coordinates': None,
                'plz_list': plz_list,
                'display_name': f'{viertel_name}, Berlin'
            }

        return {'found': False}
        
    except Exception as e:
        logger.error(f'Error searching for Viertel: {e}')
        return {'found': False}

def parse_range(input_text: str, allow_plus: bool = False) -> Optional[Dict[str, float]]:
    """Parse range like '800-1500' or '2-4' or '2+'"""
    range_pattern = r'^(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)$'
    plus_pattern = r'^(\d+(?:\.\d+)?)\s*\+$'
    
    match = re.match(range_pattern, input_text)
    if match:
        return {'min': float(match.group(1)), 'max': float(match.group(2))}
    
    if allow_plus:
        match = re.match(plus_pattern, input_text)
        if match:
            return {'min': float(match.group(1)), 'max': 10.0}
    
    return None

def parse_space_and_rooms(input_text: str) -> Optional[Dict[str, Dict[str, float]]]:
    """Parse input like '42-68 m² | 2-4 rooms'"""
    pattern = r'(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*m²?\s*\|\s*(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*rooms?'
    match = re.search(pattern, input_text, re.IGNORECASE)
    
    if match:
        return {
            'space': {'min': float(match.group(1)), 'max': float(match.group(2))},
            'rooms': {'min': float(match.group(3)), 'max': float(match.group(4))}
        }
    return None

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command - show mode selection"""
    user = update.effective_user
    first_name = user.first_name or "there"
    user_id = update.effective_user.id
    reset_user_session(user_id, 'location')  # Default to location mode
    
    welcome_message = (
        f"Welcome {first_name}!\n\n"
        "Choose what you'd like to do:\n\n"
        "Location Sharing - Share location with custom radius\n"
        "Berlin Apartment Search - Find apartments with smart search\n\n"
        "What would you like to do?"
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Share Location", callback_data="mode_location")],
        [InlineKeyboardButton("Find Berlin Apartment", callback_data="mode_apartment")],
        [InlineKeyboardButton("Help", callback_data="show_help")]
    ])
    
    await update.message.reply_text(
        welcome_message,
        reply_markup=keyboard
    )
    
    logger.info(f"📱 /start command used by {first_name} ({update.effective_chat.id})")

async def apartment_search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /apartment command - direct apartment search"""
    user_id = update.effective_user.id
    reset_user_session(user_id, 'apartment')
    
    suggestions = url_builder.get_viertel_suggestions()
    suggestion_text = ', '.join(suggestions[:8])

    await update.message.reply_text(
        f'Welcome to Berlin Apartment Search!\n\n'
        f'In which Viertel (neighborhood) would you like to live?\n\n'
        f'Popular areas: {suggestion_text}\n\n'
        f'Just type the name of your preferred neighborhood:'
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /help command"""
    help_message = (
        "Multi-Purpose Bot Help\n\n"
        "Location Sharing Mode:\n"
        "• Share your location with a custom radius\n"
        "• Perfect for delivery zones, meeting points\n"
        "• Drag map to position, adjust radius (0.1-10 km)\n\n"
        "Berlin Apartment Search Mode:\n"
        "• Smart neighborhood-based apartment search\n"
        "• Choose Viertel → Set location → Define criteria\n"
        "• Generates direct ImmobilienScout24 links\n\n"
        "Commands:\n"
        "• /start - Choose your mode\n"
        "• /apartment - Direct apartment search\n"
        "• /help - Show this help\n\n"
        "Apartment Search Flow:\n"
        "1. Choose Berlin Viertel (e.g., Mitte, Kreuzberg)\n"
        "2. Refine exact location on map\n"
        "3. Set search radius\n"
        "4. Define budget range\n"
        "5. Specify size & room count\n"
        "6. Choose floor preferences\n"
        "7. Select features (balcony, garden, pets)\n"
        "8. Get your personalized search URL!\n\n"
        "Perfect for Berlin apartment hunting!"
    )
    
    await update.message.reply_text(help_message)

async def handle_mode_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mode selection (location vs apartment)"""
    query = update.callback_query
    await query.answer()
    
    user_id = update.effective_user.id
    mode = query.data.split('_')[1]  # 'location' or 'apartment'
    
    if mode == 'location':
        reset_user_session(user_id, 'location')
        
        message = (
            "Location Sharing Mode\n\n"
            "Tap the button below to open the map and:\n"
            "• Drag the map to position the pin\n"
            "• Adjust the radius with the slider (0.1-10 km)\n"
            "• Tap 'Fertig' to send location back\n\n"
            "Perfect for delivery zones!"
        )
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Open Location Map", web_app=WebAppInfo(url=WEB_APP_URL))]
        ])
        
        await query.edit_message_text(message, reply_markup=keyboard)
        
    elif mode == 'apartment':
        reset_user_session(user_id, 'apartment')
        
        suggestions = url_builder.get_viertel_suggestions()
        suggestion_text = ', '.join(suggestions[:8])

        message = (
            f'Berlin Apartment Search\n\n'
            f'In which Viertel (neighborhood) would you like to live?\n\n'
            f'Popular areas: {suggestion_text}\n\n'
            f'Just type the name of your preferred neighborhood:'
        )
        
        await query.edit_message_text(message)

async def handle_help_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle help button callback"""
    query = update.callback_query
    await query.answer()
    
    await help_command(update, context)

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages based on current session mode and step"""
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    mode = session['mode']
    step = session['step']
    text = update.message.text
    
    logger.info(f"📝 Text message from user {user_id}: '{text}' (mode: {mode}, step: {step})")
    
    # If user hasn't chosen mode yet, show options
    if mode == 'location' and step == 'start':
        await start_command(update, context)
        return
    
    # Handle apartment search dialogue
    if mode == 'apartment':
        await handle_apartment_search_text(update, context, session, step, text)
    else:
        # Fallback for location mode
        await handle_location_mode_text(update, context)

async def handle_apartment_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                     session: Dict, step: str, text: str):
    """Handle apartment search text messages"""
    user_id = update.effective_user.id
    
    if step == 'viertel':
        await update.message.reply_text('Searching for neighborhood information...')
        
        viertel_info = await search_viertel_info(text)
        
        if not viertel_info['found']:
            suggestions = url_builder.get_viertel_suggestions()
            keyboard = []
            for viertel in suggestions:
                keyboard.append([InlineKeyboardButton(viertel, callback_data=f'viertel_{viertel}')])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.message.reply_text(
                f'Sorry, I couldn\'t find "{text}" as a Berlin neighborhood.\n\n'
                f'Please choose from these popular areas:',
                reply_markup=reply_markup
            )
            return

        # Store viertel information
        session['data']['viertel'] = viertel_info['viertel']
        session['data']['plz_list'] = viertel_info['plz_list']
        session['data']['viertel_coords'] = viertel_info['coordinates']
        session['step'] = 'location'

        plz_display = ''
        if viertel_info['plz_list']:
            plz_list = viertel_info['plz_list'][:3]
            plz_display = f" (PLZ: {', '.join(plz_list)}{'...' if len(viertel_info['plz_list']) > 3 else ''})"

        # Create MiniApp URL with coordinates for apartment search
        coords_param = ''
        if viertel_info['coordinates']:
            coords = viertel_info['coordinates']
            coords_param = f"&lat={coords['lat']}&lng={coords['lon']}&zoom=14&viertel={viertel_info['viertel']}&mode=apartment"
        else:
            coords_param = f"&mode=apartment&viertel={viertel_info['viertel']}"
        
        miniapp_url = WEB_APP_URL + coords_param
        web_app = WebAppInfo(url=miniapp_url)
        keyboard = [[InlineKeyboardButton('Refine Location in Map', web_app=web_app)]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await update.message.reply_text(
            f'Found: {viertel_info["viertel"]}{plz_display}\n\n'
            f'Now refine your exact preferred location within the neighborhood:',
            reply_markup=reply_markup
        )

    elif step == 'budget':
        budget = parse_range(text)
        if not budget or budget['min'] <= 0 or budget['max'] <= budget['min'] or budget['max'] > 10000:
            await update.message.reply_text('Please use format: min-max (e.g., 800-1500, max €10,000)')
            return
        
        session['data']['budget'] = budget
        session['step'] = 'space_rooms'
        
        await update.message.reply_text(
            f'Budget: €{int(budget["min"])} - €{int(budget["max"])}/month\n\n'
            f'Living space and rooms:\n'
            f'Format: [space] m² | [rooms] rooms\n'
            f'Example: 42-68 m² | 2-4 rooms'
        )
        
    elif step == 'space_rooms':
        space_rooms = parse_space_and_rooms(text)
        if not space_rooms:
            await update.message.reply_text('Please use format: 42-68 m² | 2-4 rooms')
            return
        
        session['data']['space'] = space_rooms['space']
        session['data']['rooms'] = space_rooms['rooms']
        session['step'] = 'floors'
        
        space = space_rooms['space']
        rooms = space_rooms['rooms']
        
        await update.message.reply_text(
            f'{int(space["min"])}-{int(space["max"])} m² | {int(rooms["min"])}-{int(rooms["max"])} rooms\n\n'
            f'Preferred floors?\nFormat: 1-3 or type "any"'
        )
        
    elif step == 'floors':
        floors = None
        if text.lower() != 'any':
            floors = parse_range(text)
            if not floors:
                await update.message.reply_text('Please use format: 1-3 or type "any"')
                return
        
        session['data']['floors'] = floors
        session['step'] = 'extras'
        
        extras_keyboard = [
            [
                InlineKeyboardButton('Garden', callback_data='toggle_garden'),
                InlineKeyboardButton('Balcony', callback_data='toggle_balcony'),
                InlineKeyboardButton('Cellar', callback_data='toggle_cellar')
            ],
            [
                InlineKeyboardButton('Pets OK', callback_data='toggle_pets'),
                InlineKeyboardButton('✅ No Swaps', callback_data='toggle_no_swaps'),
                InlineKeyboardButton('✅ Hide Promoted', callback_data='toggle_hide_promoted')
            ],
            [InlineKeyboardButton('✅ Done & Search', callback_data='generate_url')]
        ]
        reply_markup = InlineKeyboardMarkup(extras_keyboard)
        
        floors_text = f'{int(floors["min"])}-{int(floors["max"])}' if floors else 'Any'
        
        await update.message.reply_text(
            f'Floors: {floors_text}\n\n'
            f'Select extras (tap to toggle):\n\n'
            f'Selected: No Swaps, Hide Promoted',
            reply_markup=reply_markup
        )
        
    else:
        # Handle any other step or unknown input
        await update.message.reply_text(
            f'I\'m not sure what to do with "{text}" at this step. '
            f'Current step: {step}. Try /start to begin again.'
        )

async def handle_location_mode_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle text messages for location mode"""
    message = (
        "Location Sharing Mode\n\n"
        "To share a location with radius, please use the map below.\n\n"
        "Or send /start to choose a different mode."
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Open Location Map", web_app=WebAppInfo(url=WEB_APP_URL))],
        [InlineKeyboardButton("Back to Menu", callback_data="back_to_start")]
    ])
    
    await update.message.reply_text(message, reply_markup=keyboard)

async def handle_web_app_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle data from the Mini App - FIXED VERSION"""
    try:
        user_id = update.effective_user.id
        first_name = update.effective_user.first_name or "User"
        
        logger.info(f"📱 Web app data received from user {user_id}")
        
        # Check if web app data exists
        if not update.effective_message or not update.effective_message.web_app_data:
            logger.error("No web app data in message")
            await update.effective_message.reply_text("No location data received. Please try the map again.")
            return

        # Parse the JSON data
        try:
            data = json.loads(update.effective_message.web_app_data.data)
            logger.info(f"📍 Parsed web app data: {data}")
        except json.JSONDecodeError as e:
            logger.error(f"JSON decode error: {e}")
            await update.effective_message.reply_text("Invalid location data format. Please try again.")
            return

        # Extract required fields
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        radius = data.get('radius')
        
        if not all([latitude, longitude, radius]):
            logger.error(f"Missing data: lat={latitude}, lon={longitude}, radius={radius}")
            await update.effective_message.reply_text("Incomplete location data. Please try the map again.")
            return

        # Get user session
        session = get_user_session(user_id)
        logger.info(f"📋 Current session before update: mode={session.get('mode')}, step={session.get('step')}")
        
        # Store coordinates in session
        session['data']['coordinates'] = {'lat': float(latitude), 'lon': float(longitude)}
        session['data']['radius'] = float(radius)

        # Check what mode we're in
        current_mode = session.get('mode', 'location')
        web_app_mode = data.get('mode', 'location')
        
        logger.info(f"🔄 Mode check: session_mode={current_mode}, webapp_mode={web_app_mode}")

        # If apartment mode, continue the search flow
        if current_mode == 'apartment' or web_app_mode == 'apartment':
            # Ensure we're in apartment mode and set correct step
            session['mode'] = 'apartment'
            session['step'] = 'budget'
            
            # Update session in storage
            user_sessions[user_id] = session
            
            viertel = session['data'].get('viertel', 'Selected Area')
            
            logger.info(f"🏠 Continuing apartment search: viertel={viertel}, coordinates=({latitude}, {longitude}), radius={radius}")
            
            message = (
                f"Location set in {viertel}\n"
                f"Coordinates: {latitude:.6f}, {longitude:.6f}\n"
                f"Radius: {radius} km\n\n"
                f"What's your monthly budget?\n"
                f"Please reply with format: min-max\n"
                f"Example: 800-1500"
            )
            
            # Send the message
            await update.effective_message.reply_text(message)
            logger.info(f"✅ Budget request sent to user {user_id}")
            
        else:
            # Location sharing mode
            logger.info(f"📍 Processing location sharing mode")
            await handle_location_sharing_simple(update, context, latitude, longitude, radius, first_name)
            logger.info(f"✅ Location shared for user {user_id}")

    except Exception as e:
        logger.error(f"❌ Critical error in handle_web_app_data: {e}", exc_info=True)
        try:
            await update.effective_message.reply_text(
                "Something went wrong processing your location. Please try /start to begin again."
            )
        except Exception as send_error:
            logger.error(f"Failed to send error message to user: {send_error}")

async def handle_location_sharing_simple(update: Update, context: ContextTypes.DEFAULT_TYPE, 
                                       latitude: float, longitude: float, radius: str, first_name: str):
    """Simplified location sharing handler"""
    try:
        chat_id = update.effective_chat.id
        
        # Create location message
        location_message = (
            f"{first_name}'s Location\n\n"
            f"Coordinates:\n"
            f"• Latitude: {latitude:.6f}\n"
            f"• Longitude: {longitude:.6f}\n\n"
            f"Radius: {radius} km\n"
            f"Shared: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
            f"Open in Google Maps: https://maps.google.com/maps?q={latitude},{longitude}"
        )
        
        # Create action buttons
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Google Maps", url=f"https://maps.google.com/maps?q={latitude},{longitude}"),
                InlineKeyboardButton("Directions", url=f"https://maps.google.com/maps?daddr={latitude},{longitude}")
            ],
            [
                InlineKeyboardButton("Share New Location", web_app=WebAppInfo(url=WEB_APP_URL))
            ]
        ])
        
        # Send location message
        await update.effective_message.reply_text(
            location_message,
            reply_markup=keyboard,
            disable_web_page_preview=False
        )
        
        # Send actual location pin
        await context.bot.send_location(
            chat_id=chat_id,
            latitude=latitude,
            longitude=longitude
        )
        
        # Calculate area
        area = 3.14159 * (float(radius) ** 2)
        coverage_message = (
            f"Coverage Area\n\n"
            f"Radius of {radius} km covers approximately {area:.1f} km²\n\n"
            f"Perfect for delivery zones!"
        )
        
        await update.effective_message.reply_text(coverage_message)
        
    except Exception as e:
        logger.error(f"Error in location sharing: {e}")
        await update.effective_message.reply_text("Location received, but couldn't format display properly.")

# All the other handler functions remain the same...
async def handle_viertel_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle Viertel quick selection buttons"""
    query = update.callback_query
    await query.answer()
    
    viertel = query.data.split('_', 1)[1]
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    await query.edit_message_text('Searching for neighborhood information...')
    
    viertel_info = await search_viertel_info(viertel)
    
    # Store viertel information
    session['data']['viertel'] = viertel_info['viertel']
    session['data']['plz_list'] = viertel_info['plz_list']
    session['data']['viertel_coords'] = viertel_info['coordinates']
    session['step'] = 'location'

    plz_display = ''
    if viertel_info['plz_list']:
        plz_list = viertel_info['plz_list'][:3]
        plz_display = f" (PLZ: {', '.join(plz_list)}{'...' if len(viertel_info['plz_list']) > 3 else ''})"

    # Create MiniApp URL with coordinates
    coords_param = ''
    if viertel_info['coordinates']:
        coords = viertel_info['coordinates']
        coords_param = f"&lat={coords['lat']}&lng={coords['lon']}&zoom=14&viertel={viertel_info['viertel']}&mode=apartment"
    else:
        coords_param = f"&mode=apartment&viertel={viertel_info['viertel']}"
    
    miniapp_url = WEB_APP_URL + coords_param
    web_app = WebAppInfo(url=miniapp_url)
    keyboard = [[InlineKeyboardButton('Refine Location in Map', web_app=web_app)]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(
        f'Found: {viertel_info["viertel"]}{plz_display}\n\n'
        f'Now refine your exact preferred location within the neighborhood:',
        reply_markup=reply_markup
    )

async def handle_extras_toggle(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle extras toggles"""
    query = update.callback_query
    await query.answer()
    
    extra = query.data.split('_', 1)[1]
    user_id = update.effective_user.id
    session = get_user_session(user_id)
    
    # Toggle the extra
    current = session['data']['extras'].get(extra, False)
    session['data']['extras'][extra] = not current
    
    # Update the extras display
    extras = session['data']['extras']
    selected = []
    
    if extras.get('garden'):
        selected.append('Garden')
    if extras.get('balcony'):
        selected.append('Balcony')
    if extras.get('cellar'):
        selected.append('Cellar')
    if extras.get('pets'):
        selected.append('Pets OK')
    if extras.get('no_swaps'):
        selected.append('No Swaps')
    if extras.get('hide_promoted'):
        selected.append('Hide Promoted')
    
    extras_keyboard = [
        [
            InlineKeyboardButton('✅ Garden' if extras.get('garden') else 'Garden', callback_data='toggle_garden'),
            InlineKeyboardButton('✅ Balcony' if extras.get('balcony') else 'Balcony', callback_data='toggle_balcony'),
            InlineKeyboardButton('✅ Cellar' if extras.get('cellar') else 'Cellar', callback_data='toggle_cellar')
        ],
        [
            InlineKeyboardButton('✅ Pets OK' if extras.get('pets') else 'Pets OK', callback_data='toggle_pets'),
            InlineKeyboardButton('✅ No Swaps' if extras.get('no_swaps') else 'No Swaps', callback_data='toggle_no_swaps'),
            InlineKeyboardButton('✅ Hide Promoted' if extras.get('hide_promoted') else 'Hide Promoted', callback_data='toggle_hide_promoted')
        ],
        [InlineKeyboardButton('✅ Done & Search', callback_data='generate_url')]
    ]
    reply_markup = InlineKeyboardMarkup(extras_keyboard)