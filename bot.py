import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler
import asyncio
import json
import os

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Global variables to store data
USER_DATA_FILE = "user_data.json"
user_data = {"collected_ids": [], "target_group_id": None, "message_to_send": ""}

# Helper functions
async def load_data():
    global user_data
    if os.path.exists(USER_DATA_FILE):
        with open(USER_DATA_FILE, "r") as f:
            user_data = json.load(f)

async def save_data():
    with open(USER_DATA_FILE, "w") as f:
        json.dump(user_data, f)

# Command handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /start is issued."""
    keyboard = [
        [InlineKeyboardButton("Collect IDs from a group", callback_data="collect_ids")],
        [InlineKeyboardButton("Send message to collected IDs", callback_data="send_pm")],
        [InlineKeyboardButton("Send message to group members", callback_data="send_group")],
        [InlineKeyboardButton("Move members to another group", callback_data="move_members")],
        [InlineKeyboardButton("Add collected IDs to a group", callback_data="add_to_group")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose an action:", reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message when the command /help is issued."""
    help_text = """
Available commands:
/start - Show main menu
/collect_ids <group_id> - Collect user IDs from a group
/send_pm <message> - Send a PM to all collected IDs
/send_group <group_id> <message> - Send message to all users in a group
/move <source_group_id> <target_group_id> - Move members from one group to another
/add_to_group <group_id> - Add collected IDs to a group
/help - Show this help message

Group ID Format:
- You can use just the numeric ID (e.g., "1234567890")
- The bot will automatically add "-100" prefix if needed
- Or you can use the full format: "-1001234567890"

Note: To get a group's ID, forward a message from the group to @userinfobot
"""
    await update.message.reply_text(help_text)

async def collect_ids_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Collect user IDs from a group."""
    if not context.args:
        await update.message.reply_text("Please provide the group ID: /collect_ids <group_id>")
        return
    
    try:
        group_id = context.args[0]
        
        # Format group ID if needed (add -100 prefix for supergroups if it's missing)
        if group_id.isdigit():
            group_id = f"-100{group_id}"
        elif group_id.startswith('-') and group_id[1:].isdigit() and not group_id.startswith('-100'):
            # If it starts with a single dash but not with -100
            group_id = f"-100{group_id[1:]}"
            
        await update.message.reply_text(f"Starting to collect IDs from group {group_id}...")
        
        # Try to get the chat members
        try:
            chat = await context.bot.get_chat(group_id)
            
            # Check if the bot is a member of the group
            bot_member = await context.bot.get_chat_member(chat.id, context.bot.id)
            
            if bot_member.status == 'kicked' or bot_member.status == 'left':
                await update.message.reply_text("Error: Bot is not a member of this group. Please add the bot to the group first.")
                return
                
            # Check if the bot has admin rights
            if bot_member.status != 'administrator' and bot_member.status != 'creator':
                await update.message.reply_text("Warning: Bot is not an administrator in this group. Only admins will be collected.")
            
            members = await context.bot.get_chat_administrators(chat.id)
            
            user_data["collected_ids"] = []
            for member in members:
                user_data["collected_ids"].append(member.user.id)
                
            await save_data()
            await update.message.reply_text(f"Collected {len(user_data['collected_ids'])} IDs from administrators.")
            
            # Note: Getting all members requires higher API privileges for bots
            await update.message.reply_text("Note: Due to Telegram API limitations, only administrators could be collected. For all members, you'll need to use a user account API.")
        
        except Exception as e:
            error_message = str(e)
            if "Chat not found" in error_message:
                await update.message.reply_text("Error: Chat not found. Please ensure:\n1. The group ID is correct\n2. The bot is a member of the group\n3. The group is a supergroup, not a basic group")
            else:
                await update.message.reply_text(f"Error collecting IDs: {error_message}")
    
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def send_pm_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a PM to all collected IDs."""
    if not context.args:
        await update.message.reply_text("Please provide the message: /send_pm <message>")
        return
    
    message = " ".join(context.args)
    user_data["message_to_send"] = message
    await save_data()
    
    if not user_data["collected_ids"]:
        await update.message.reply_text("No IDs collected. Please use /collect_ids first.")
        return
    
    await update.message.reply_text(f"Starting to send message to {len(user_data['collected_ids'])} users...")
    
    success_count = 0
    for user_id in user_data["collected_ids"]:
        try:
            await context.bot.send_message(chat_id=user_id, text=message)
            success_count += 1
            await asyncio.sleep(0.5)  # Delay to avoid hitting limits
        except Exception as e:
            logger.error(f"Failed to send message to {user_id}: {str(e)}")
    
    await update.message.reply_text(f"Message sent successfully to {success_count} out of {len(user_data['collected_ids'])} users.")

async def send_group_message_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a message to all users in a group one by one."""
    if len(context.args) < 2:
        await update.message.reply_text("Please provide the group ID and message: /send_group <group_id> <message>")
        return
    
    group_id = context.args[0]
    
    # Format group ID if needed
    if group_id.isdigit():
        group_id = f"-100{group_id}"
    elif group_id.startswith('-') and group_id[1:].isdigit() and not group_id.startswith('-100'):
        group_id = f"-100{group_id[1:]}"
    
    message = " ".join(context.args[1:])
    
    await update.message.reply_text(f"Starting to send message to members of group {group_id}...")
    
    try:
        chat = await context.bot.get_chat(group_id)
        members = await context.bot.get_chat_administrators(chat.id)
        
        success_count = 0
        for member in members:
            try:
                await context.bot.send_message(chat_id=member.user.id, text=message)
                success_count += 1
                await asyncio.sleep(0.5)  # Delay to avoid hitting limits
            except Exception as e:
                logger.error(f"Failed to send message to {member.user.id}: {str(e)}")
        
        await update.message.reply_text(f"Message sent successfully to {success_count} out of {len(members)} administrators.")
        await update.message.reply_text("Note: Due to Telegram API limitations, messages were only sent to administrators. For all members, you'll need to use a user account API.")
    
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def move_members_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Move members from one group to another specified group."""
    if len(context.args) < 2:
        await update.message.reply_text("Please provide source and target group IDs: /move <source_group_id> <target_group_id>")
        return
    
    source_group_id = context.args[0]
    target_group_id = context.args[1]
    
    # Format group IDs if needed
    if source_group_id.isdigit():
        source_group_id = f"-100{source_group_id}"
    elif source_group_id.startswith('-') and source_group_id[1:].isdigit() and not source_group_id.startswith('-100'):
        source_group_id = f"-100{source_group_id[1:]}"
        
    if target_group_id.isdigit():
        target_group_id = f"-100{target_group_id}"
    elif target_group_id.startswith('-') and target_group_id[1:].isdigit() and not target_group_id.startswith('-100'):
        target_group_id = f"-100{target_group_id[1:]}"
    
    await update.message.reply_text(f"Starting to move members from {source_group_id} to {target_group_id}...")
    
    try:
        # Get source group members
        chat = await context.bot.get_chat(source_group_id)
        members = await context.bot.get_chat_administrators(chat.id)
        
        # Try to add to target group
        success_count = 0
        for member in members:
            try:
                # Create an invite link for the target group
                invite_link = await context.bot.create_chat_invite_link(target_group_id)
                
                # Send the invite link to the user
                await context.bot.send_message(
                    chat_id=member.user.id,
                    text=f"You are invited to join a new group: {invite_link.invite_link}"
                )
                success_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to invite {member.user.id}: {str(e)}")
        
        await update.message.reply_text(f"Invitation sent to {success_count} out of {len(members)} users.")
        await update.message.reply_text("Note: Due to Telegram API limitations, only administrators could be processed. For all members, you'll need to use a user account API.")
    
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def add_to_group_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Add users with known IDs to a group."""
    if not context.args:
        await update.message.reply_text("Please provide the group ID: /add_to_group <group_id>")
        return
    
    target_group_id = context.args[0]
    
    # Format group ID if needed
    if target_group_id.isdigit():
        target_group_id = f"-100{target_group_id}"
    elif target_group_id.startswith('-') and target_group_id[1:].isdigit() and not target_group_id.startswith('-100'):
        target_group_id = f"-100{target_group_id[1:]}"
    
    if not user_data["collected_ids"]:
        await update.message.reply_text("No IDs collected. Please use /collect_ids first.")
        return
    
    await update.message.reply_text(f"Starting to add {len(user_data['collected_ids'])} users to group {target_group_id}...")
    
    try:
        # Create an invite link
        invite_link = await context.bot.create_chat_invite_link(target_group_id)
        
        # Send the invite link to collected users
        success_count = 0
        for user_id in user_data["collected_ids"]:
            try:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=f"You are invited to join a new group: {invite_link.invite_link}"
                )
                success_count += 1
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Failed to invite {user_id}: {str(e)}")
        
        await update.message.reply_text(f"Invitation sent to {success_count} out of {len(user_data['collected_ids'])} users.")
    
    except Exception as e:
        await update.message.reply_text(f"Error: {str(e)}")

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle button callbacks."""
    query = update.callback_query
    await query.answer()
    
    if query.data == "collect_ids":
        await query.message.reply_text("Please use command: /collect_ids <group_id>")
    elif query.data == "send_pm":
        await query.message.reply_text("Please use command: /send_pm <message>")
    elif query.data == "send_group":
        await query.message.reply_text("Please use command: /send_group <group_id> <message>")
    elif query.data == "move_members":
        await query.message.reply_text("Please use command: /move <source_group_id> <target_group_id>")
    elif query.data == "add_to_group":
        await query.message.reply_text("Please use command: /add_to_group <group_id>")

def main() -> None:
    """Start the bot."""
    # Create the Application
    application = Application.builder().token("8040696912:AAFE94BWNzyfAmFzbj59_-mSQhk-Wt5oDXM").build()
    
    # Don't try to load data this way - will be loaded when application starts
    # application.create_task(load_data())
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("collect_ids", collect_ids_command))
    application.add_handler(CommandHandler("send_pm", send_pm_command))
    application.add_handler(CommandHandler("send_group", send_group_message_command))
    application.add_handler(CommandHandler("move", move_members_command))
    application.add_handler(CommandHandler("add_to_group", add_to_group_command))
    
    # Add callback query handler
    application.add_handler(CallbackQueryHandler(button))
    
    # Setup post_init callback to load data when the application starts
    async def post_init(app: Application) -> None:
        await load_data()
    
    application.post_init = post_init
    
    # Run the bot until the user presses Ctrl-C
    application.run_polling()

if __name__ == "__main__":
    main() 