from telethon import TelegramClient, events, sync, version
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest, GetParticipantsRequest
from telethon.tl.functions.messages import AddChatUserRequest, GetDialogsRequest
from telethon.tl.types import InputPeerChannel, InputPeerUser, PeerUser, PeerChannel, ChannelParticipantsSearch, InputChannel
from telethon.errors import FloodWaitError, UserPrivacyRestrictedError, UserNotMutualContactError
import asyncio
import json
import os
import logging
from datetime import datetime

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# API credentials
# You must get these from https://my.telegram.org
# 1. Visit https://my.telegram.org and login with your phone number
# 2. Click on "API Development tools"
# 3. Create a new application and fill in the required fields
# 4. Copy the "api_id" and "api_hash" below
API_ID = 23440370  # Replace with your API ID (numbers only, no quotes)
API_HASH = '2664b9ce2d22499e4228a27e9c7ddd11'  # Replace with your API HASH (include quotes)

# Print Telethon version for debugging
print(f"Using Telethon version: {version.__version__}")

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

def format_group_id(group_id):
    """Format group ID by adding -100 prefix if needed"""
    if group_id.isdigit():
        return f"-100{group_id}"
    elif group_id.startswith('-') and group_id[1:].isdigit() and not group_id.startswith('-100'):
        return f"-100{group_id[1:]}"
    return group_id

async def ensure_entity(client, entity_id):
    """Convert entity_id to an entity object"""
    try:
        # Format the entity ID properly
        entity_id = format_group_id(entity_id)
        
        # Try direct approach first
        try:
            return await client.get_entity(entity_id)
        except ValueError:
            # If that fails, try converting to integer if it's a channel ID
            if entity_id.startswith('-100'):
                channel_id = int(entity_id[4:])
                return await client.get_entity(PeerChannel(channel_id))
            elif entity_id.isdigit():
                return await client.get_entity(int(entity_id))
            else:
                # Last attempt - try as username
                return await client.get_entity(entity_id)
    except Exception as e:
        logger.error(f"Error getting entity: {e}")
        return None

class TelegramUserBot:
    def __init__(self):
        try:
            # Ensure API_ID is an integer
            api_id = int(API_ID)
            
            print(f"Initializing client with API_ID: {api_id}")
            print(f"API_HASH length: {len(API_HASH)} characters")
            
            self.client = TelegramClient('user_session', api_id, API_HASH)
            self.client.start()
            
            me = self.client.get_me()
            print(f"UserBot started!")
            print(f"Logged in as: {me.first_name} (@{me.username})")
            
            # Load data at startup
            loop = asyncio.get_event_loop()
            loop.run_until_complete(load_data())
            
            self.setup_handlers()
        except ValueError as e:
            print(f"Error: API_ID must be an integer. Current value: {API_ID}")
            raise
        except Exception as e:
            print(f"Error initializing UserBot: {e}")
            print("\nPossible solutions:")
            print("1. Make sure your API_ID and API_HASH are correct from my.telegram.org")
            print("2. Update Telethon: pip install -U telethon")
            print("3. Check your internet connection")
            print("4. Try again with a new API_ID and API_HASH")
            raise

    def setup_handlers(self):
        """Setup message handlers"""
        @self.client.on(events.NewMessage(pattern='/help'))
        async def help_handler(event):
            help_text = """
Available commands:
/collect_ids <group_id> - Collect user IDs from a group's members
/chat_collect <group_id> - Collect user IDs from people who sent messages
/join <group_username> - Join a group by username 
/join_collect <group_username> - Join a group and collect IDs in one step
/send_pm <message> - Send a PM to all collected IDs
/chat_send <group_id> <message> - Send message to users active in a chat
/send_group <group_id> <message> - Send message to all users in a group
/move <source_group_id> <target_group_id> - Move members from one group to another
/add <group_id> - Add collected IDs to a group
/my_groups - List all your groups for easier selection
/help - Show this help message

Special features:
- Send a t.me link to automatically join and collect IDs from that group
- You can use group username without @ symbol
            """
            await event.respond(help_text)

        @self.client.on(events.NewMessage(pattern='/debug_group'))
        async def debug_group_id(event):
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the group ID to debug: /debug_group <group_id>")
                return
            
            group_id = args[1].strip()
            await event.respond(f"Debugging group ID: {group_id}")
            
            try:
                # Try different formats to find the group
                formats_to_try = [
                    group_id,
                    f"-100{group_id}" if group_id.isdigit() else group_id,
                    group_id[1:] if group_id.startswith('@') else group_id,
                    int(group_id) if group_id.isdigit() else group_id,
                ]
                
                if group_id.isdigit():
                    # Try with channel format
                    formats_to_try.append(int(group_id))
                    formats_to_try.append(int(f"-100{group_id}"))
                    
                    # Try with InputChannel format
                    channel_id = int(group_id)
                    formats_to_try.append(InputChannel(channel_id, 0))
                    formats_to_try.append(InputChannel(channel_id, 99))
                
                success = False
                for format_id in formats_to_try:
                    try:
                        await event.respond(f"Trying format: {format_id} (type: {type(format_id).__name__})")
                        entity = await self.client.get_entity(format_id)
                        await event.respond(f"✅ Success! Found entity: {entity.title} (ID: {entity.id}, type: {type(entity).__name__})")
                        
                        # Try to get participants with this entity
                        try:
                            if hasattr(entity, 'id') and hasattr(entity, 'access_hash'):
                                input_channel = InputChannel(entity.id, entity.access_hash)
                                await event.respond(f"Created InputChannel with ID: {entity.id}, access_hash: {entity.access_hash}")
                                
                                # Try direct API call
                                result = await self.client(GetParticipantsRequest(
                                    channel=input_channel,
                                    filter=ChannelParticipantsSearch(''),
                                    offset=0,
                                    limit=10,
                                    hash=0
                                ))
                                await event.respond(f"✅ Successfully fetched {len(result.participants)} participants!")
                                success = True
                                break
                        except Exception as pe:
                            await event.respond(f"❌ Could not get participants: {str(pe)}")
                    except Exception as e:
                        await event.respond(f"❌ Format failed: {str(e)}")
                
                if not success:
                    # Last resort - try using dialogs
                    await event.respond("Trying to find group in your dialogs...")
                    found = False
                    async for dialog in self.client.iter_dialogs():
                        if dialog.is_group or dialog.is_channel:
                            if str(dialog.id) == str(group_id) or str(abs(dialog.id)) == str(group_id) or str(dialog.id).endswith(str(group_id)):
                                await event.respond(f"✅ Found matching dialog: {dialog.title} (ID: {dialog.id})")
                                found = True
                                
                                try:
                                    participants = await self.client.get_participants(dialog.entity, limit=10)
                                    await event.respond(f"✅ Successfully fetched {len(participants)} participants!")
                                    
                                    # Show the command to use
                                    actual_id = dialog.id
                                    if actual_id < 0 and not str(actual_id).startswith("-100"):
                                        actual_id = f"-100{abs(actual_id)}"
                                    await event.respond(f"Use this command: `/collect_ids {actual_id}`")
                                    break
                                except Exception as pe:
                                    await event.respond(f"❌ Could not get participants: {str(pe)}")
                    
                    if not found:
                        await event.respond("❌ Could not find this group in your dialogs. Make sure you are a member of this group.")
            
            except Exception as e:
                await event.respond(f"Debug error: {str(e)}")

        @self.client.on(events.NewMessage(pattern='/collect_ids'))
        async def collect_ids_handler(event):
            await load_data()
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the group ID: /collect_ids <group_id> or /collect_ids @username")
                return
            
            group_id = args[1].strip()
            await event.respond(f"Starting to collect IDs from group {group_id}...")
            
            try:
                # Try to find the group in your dialogs first (most reliable)
                group_entity = None
                async for dialog in self.client.iter_dialogs():
                    dialog_id = dialog.id
                    # Match by complete ID or by the trailing digits
                    if str(dialog_id) == str(group_id) or str(abs(dialog_id)) == str(group_id) or \
                       (group_id.isdigit() and str(abs(dialog_id)).endswith(str(group_id))):
                        group_entity = dialog.entity
                        await event.respond(f"Found group: {dialog.title}")
                        # Store the found group ID for future use in other commands
                        user_data["last_group_id"] = str(dialog_id)
                        user_data["last_group_title"] = dialog.title
                        await save_data()
                        break
                
                # If not found in dialogs, try direct approach
                if not group_entity:
                    # Handle username case
                    if not group_id.isdigit() and not group_id.startswith('-'):
                        # Clean up username
                        if group_id.startswith('@'):
                            group_id = group_id[1:]
                        
                        try:
                            group_entity = await self.client.get_entity(group_id)
                            await event.respond(f"Found group by username: {group_entity.title}")
                            # Store for future use
                            user_data["last_group_id"] = str(group_entity.id)
                            user_data["last_group_title"] = group_entity.title
                            await save_data()
                        except Exception as e:
                            await event.respond(f"Error finding group by username: {str(e)}")
                    else:
                        # Try numeric approaches
                        try:
                            if group_id.isdigit():
                                # Try with -100 prefix for supergroups
                                channel_id = int(f"-100{group_id}")
                                group_entity = await self.client.get_entity(channel_id)
                                # Store for future use
                                user_data["last_group_id"] = str(channel_id)
                            else:
                                # Use as is if it already has a negative prefix
                                group_entity = await self.client.get_entity(int(group_id))
                                # Store for future use
                                user_data["last_group_id"] = group_id
                                
                            if hasattr(group_entity, 'title'):
                                user_data["last_group_title"] = group_entity.title
                                await event.respond(f"Found group: {group_entity.title}")
                            await save_data()
                        except Exception as e:
                            await event.respond(f"Error finding group by ID: {str(e)}")
                
                if not group_entity:
                    await event.respond("Could not find this group. Please try using /my_groups to list your groups, or /debug_group to diagnose the issue.")
                    return
                
                # Store the found entity in memory (outside of user_data since entities can't be serialized)
                if not hasattr(self, 'found_entities'):
                    self.found_entities = {}
                
                # Store using multiple keys for reliable lookup later
                entity_id = str(group_entity.id)
                self.found_entities[entity_id] = group_entity
                self.found_entities[str(abs(group_entity.id))] = group_entity
                if group_id.isdigit():
                    self.found_entities[group_id] = group_entity
                    
                # Also store formatted -100 version if needed
                if entity_id.startswith('-'):
                    if not entity_id.startswith('-100'):
                        self.found_entities[f"-100{abs(int(entity_id))}"] = group_entity
                else:
                    self.found_entities[f"-100{entity_id}"] = group_entity
                
                # Now collect participants
                try:
                    participants = []
                    if hasattr(group_entity, 'id') and hasattr(group_entity, 'access_hash'):
                        # Channel/Supergroup approach
                        input_channel = InputChannel(group_entity.id, group_entity.access_hash)
                        
                        # Use direct API call with pagination for larger groups
                        offset = 0
                        limit = 200
                        all_participants = []
                        
                        while True:
                            result = await self.client(GetParticipantsRequest(
                                channel=input_channel,
                                filter=ChannelParticipantsSearch(''),
                                offset=offset,
                                limit=limit,
                                hash=0
                            ))
                            if not result.participants:
                                break
                            all_participants.extend(result.participants)
                            offset += len(result.participants)
                            await event.respond(f"Collected {len(all_participants)} users so far...")
                            if len(result.participants) < limit:
                                break
                        
                        participants = all_participants
                    else:
                        # Normal group approach
                        participants = await self.client.get_participants(group_entity)
                    
                    # Process participants
                    user_data["collected_ids"] = []
                    
                    # Debug info about participants
                    if participants and len(participants) > 0:
                        first_participant = participants[0]
                        await event.respond(f"Debug: First participant type: {type(first_participant).__name__}")
                        
                        # Show available attributes for debugging
                        attrs = dir(first_participant)
                        important_attrs = [attr for attr in attrs if not attr.startswith('_') and not callable(getattr(first_participant, attr))]
                        await event.respond(f"Available attributes: {', '.join(important_attrs)}")
                        
                        # Check if has user attribute
                        if hasattr(first_participant, 'user'):
                            user_attrs = dir(first_participant.user)
                            user_important_attrs = [attr for attr in user_attrs if not attr.startswith('_') and not callable(getattr(first_participant.user, attr))]
                            await event.respond(f"User attributes: {', '.join(user_important_attrs)}")
                    
                    # Process all participants
                    for participant in participants:
                        # For ChannelParticipant and similar objects that have user_id directly
                        if hasattr(participant, 'user_id'):
                            user_data["collected_ids"].append(participant.user_id)
                            continue
                            
                        # For other participant types
                        # Safely check if participant is a bot
                        is_bot = False
                        if hasattr(participant, 'bot'):
                            is_bot = participant.bot
                        elif hasattr(participant, 'user') and hasattr(participant.user, 'bot'):
                            is_bot = participant.user.bot
                        
                        # Only add if not a bot
                        if not is_bot:
                            # Get user ID, which may be directly in participant or in user attribute
                            user_id = getattr(participant, 'id', None)
                            if user_id is None and hasattr(participant, 'user'):
                                user_id = getattr(participant.user, 'id', None)
                            
                            # Add user ID if valid
                            if user_id is not None:
                                user_data["collected_ids"].append(user_id)
                            else:
                                await event.respond(f"Warning: Could not get ID for participant: {participant}")
                    
                    # Save and report results
                    await save_data()
                    await event.respond(f"Successfully collected {len(user_data['collected_ids'])} user IDs from the group.")
                    
                except Exception as e:
                    await event.respond(f"Error collecting participants: {str(e)}")
                    await event.respond("Try using the /debug_group command to diagnose the issue.")
                    
            except Exception as e:
                logger.error(f"Error collecting IDs: {e}")
                await event.respond(f"Error: {str(e)}\n\nTry using /my_groups to list your groups first.")

        @self.client.on(events.NewMessage(pattern='/send_pm'))
        async def send_pm_handler(event):
            await load_data()
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the message: /send_pm <message>")
                return
            
            message = args[1].strip()
            user_data["message_to_send"] = message
            await save_data()
            
            if not user_data["collected_ids"]:
                await event.respond("No IDs collected. Please use /collect_ids first.")
                return
                
            # Check for force option to bypass safety measures
            force_mode = False
            if "--force" in message:
                message = message.replace("--force", "").strip()
                force_mode = True
                await event.respond("Force mode enabled: Will attempt to bypass safety measures")
            
            # Check for ignore-errors option
            ignore_errors = False
            if "--ignore-errors" in message:
                message = message.replace("--ignore-errors", "").strip()
                ignore_errors = True
                await event.respond("Ignore errors mode enabled: Will continue sending even after errors")
                
            # Get my ID to avoid sending to self
            my_id = (await self.client.get_me()).id
            
            # Filter suspected bots based on ID patterns and known bot IDs
            # Most Telegram bots have IDs over 1 billion and/or end with "bot"
            known_bot_ids = {6800837494, 609517172, 8009020222, 1449288127}  # Add known bot IDs from your log
            
            # Filter out bots and self
            original_count = len(user_data["collected_ids"])
            filtered_ids = []
            for uid in user_data["collected_ids"]:
                if uid == my_id:
                    continue  # Skip self
                if uid in known_bot_ids:
                    continue  # Skip known bots
                filtered_ids.append(uid)
                
            removed_count = original_count - len(filtered_ids)
            if removed_count > 0:
                await event.respond(f"⚠️ Filtered out {removed_count} suspected bots and self from sending list")
            
            await event.respond(f"Starting to send message to {len(filtered_ids)} users...")
            
            # Configure rate limiting parameters - Telegram is strict about messaging
            batch_size = 5  # Send to this many users before taking a break
            batch_delay = 60  # Seconds to wait between batches (1 minute)
            message_delay = 3  # Seconds between individual messages
            
            # For larger numbers, take bigger breaks
            if len(filtered_ids) > 30:
                long_break_interval = 30  # Every 30 users
                long_break_duration = 300  # 5 minutes
                await event.respond(f"⚠️ Large number of users detected! Will take {long_break_duration//60} minute breaks every {long_break_interval} users")
            
            # Track progress
            success_count = 0
            error_count = 0
            total_users = len(filtered_ids)
            
            # Process in batches with retries
            for i, user_id in enumerate(filtered_ids):
                try:
                    # Double check if this is a bot - some bots don't have bot flag set properly
                    try:
                        user = await self.client.get_entity(user_id)
                        
                        # Skip users that look like bots based on username/name patterns if not in force mode
                        if not force_mode and hasattr(user, 'username') and user.username:
                            bot_keywords = ['bot', 'robot', 'assistant', 'helper', 'info', 'news', 'alert']
                            if any(keyword in user.username.lower() for keyword in bot_keywords):
                                await event.respond(f"⚠️ Skipping likely bot: @{user.username}")
                                continue
                                
                        # Also check the actual bot flag
                        if hasattr(user, 'bot') and user.bot:
                            logger.warning(f"Skipping confirmed bot: {user_id}")
                            continue
                    except Exception as e:
                        if not ignore_errors:
                            logger.error(f"Error checking user {user_id}: {str(e)}")
                            error_count += 1
                            continue
                    
                    # Send the message
                    await self.client.send_message(user, message)
                    success_count += 1
                    
                    # Show progress periodically
                    if success_count % 5 == 0 or success_count == total_users:
                        await event.respond(f"Progress: Successfully sent to {success_count}/{total_users} users")
                        
                    # Apply rate limiting
                    if i < total_users - 1:  # Skip delay for the last user
                        # Take a short break between each message
                        await asyncio.sleep(message_delay)
                        
                        # Take a longer break after each batch
                        if (i + 1) % batch_size == 0:
                            await event.respond(f"Taking a {batch_delay}s break to avoid rate limits... ({i+1}/{total_users} processed)")
                            await asyncio.sleep(batch_delay)
                            
                        # For large numbers, take an even longer break periodically
                        if len(filtered_ids) > 30 and (i + 1) % long_break_interval == 0:
                            await event.respond(f"Taking a longer {long_break_duration}s break... ({i+1}/{total_users} processed)")
                            await asyncio.sleep(long_break_duration)
                
                except FloodWaitError as e:
                    # Telegram is forcing us to wait
                    wait_time = e.seconds
                    await event.respond(f"⚠️ Telegram rate limit hit! Forced to wait for {wait_time} seconds...")
                    await asyncio.sleep(wait_time)
                    
                    # Try again with the same user after waiting
                    try:
                        user = await self.client.get_entity(user_id)
                        await self.client.send_message(user, message)
                        success_count += 1
                        await event.respond(f"Resumed after waiting. Progress: {success_count}/{total_users}")
                    except Exception as retry_error:
                        error_count += 1
                        logger.error(f"Failed to send message to {user_id} even after waiting: {str(retry_error)}")
                
                except Exception as e:
                    error_count += 1
                    error_msg = str(e)
                    logger.error(f"Failed to send message to {user_id}: {error_msg}")
                    
                    # In ignore_errors mode, continue without breaking the loop
                    if ignore_errors:
                        if error_count % 5 == 0:  # Don't spam with every error
                            await event.respond(f"⚠️ Encountered {error_count} errors so far, but continuing...")
                        # Add a small delay to not hammer the rate limit
                        await asyncio.sleep(1)
                    else:
                        # If too many consequential errors, take a break
                        if error_count >= 5:
                            await event.respond(f"⚠️ Hit {error_count} errors in a row. Taking a 2 minute break...")
                            await asyncio.sleep(120)  # 2 minute break
                            error_count = 0  # Reset counter after break
            
            # Final report
            await event.respond(f"📊 Message sending complete!\n✅ Successfully sent to {success_count} out of {total_users} users.\n❌ Failed for {error_count} users.")
            
            # Advice for the user if success rate is low
            if success_count < total_users * 0.5:  # Less than 50% success
                await event.respond("💡 Tip: Telegram limits how many messages you can send in a short time. Try:\n"
                                   "1. Using '--ignore-errors' flag for persistent sending\n"
                                   "2. Waiting a few hours before sending again\n"
                                   "3. Sending to smaller batches of users")

        @self.client.on(events.NewMessage(pattern='/send_group'))
        async def send_group_message_handler(event):
            args = event.text.split(' ', 2)
            
            if len(args) < 3:
                await event.respond("Please provide the group ID and message: /send_group <group_id> <message>")
                return
            
            group_id = args[1].strip()
            message = args[2].strip()
            
            await event.respond(f"Starting to send message to members of group {group_id}...")
            
            try:
                # First try to use cached entity from previous commands
                group_entity = None
                
                # Check if we have a cached entity from collect_ids
                if hasattr(self, 'found_entities') and group_id in self.found_entities:
                    group_entity = self.found_entities[group_id]
                    await event.respond(f"Using cached group: {getattr(group_entity, 'title', 'Unknown')}")
                
                # Check if we just recently collected from a group
                elif "last_group_id" in user_data and (
                    user_data["last_group_id"] == group_id or 
                    user_data["last_group_id"] == str(abs(int(group_id))) if group_id.startswith('-') and group_id[1:].isdigit() else False
                ):
                    try:
                        # Try to get entity from the stored ID
                        last_id = user_data["last_group_id"]
                        group_entity = await self.client.get_entity(int(last_id))
                        await event.respond(f"Using last collected group: {user_data.get('last_group_title', 'Unknown')}")
                    except Exception as e:
                        await event.respond(f"Error retrieving last group: {str(e)}")
                
                # If not found from cache, try normal methods
                if not group_entity:
                    # Try to find in current dialog list
                    async for dialog in self.client.iter_dialogs():
                        dialog_id = dialog.id
                        # Match by complete ID or by the trailing digits
                        if str(dialog_id) == str(group_id) or str(abs(dialog_id)) == str(group_id) or \
                        (group_id.isdigit() and str(abs(dialog_id)).endswith(str(group_id))):
                            group_entity = dialog.entity
                            await event.respond(f"Found group in dialogs: {dialog.title}")
                            break
                
                # Last resort - try direct lookup
                if not group_entity and group_id.isdigit():
                    try:
                        # Try with -100 prefix for supergroups
                        channel_id = int(f"-100{group_id}")
                        group_entity = await self.client.get_entity(channel_id)
                        await event.respond(f"Found group by ID: {getattr(group_entity, 'title', 'Unknown')}")
                    except Exception as e:
                        await event.respond(f"Could not find group with ID {group_id}: {str(e)}")
                
                if not group_entity:
                    await event.respond("Error: Could not find group. Please first use /collect_ids with this group, or try /my_groups to list available groups.")
                    return
                
                # Now get participants
                participants = []
                try:
                    if hasattr(group_entity, 'id') and hasattr(group_entity, 'access_hash'):
                        # For supergroups/channels
                        input_channel = InputChannel(group_entity.id, group_entity.access_hash)
                        
                        # Use direct API call with pagination for larger groups
                        offset = 0
                        limit = 200
                        all_participants = []
                        
                        await event.respond("Getting participants from channel/supergroup...")
                        while True:
                            try:
                                result = await self.client(GetParticipantsRequest(
                                    channel=input_channel,
                                    filter=ChannelParticipantsSearch(''),
                                    offset=offset,
                                    limit=limit,
                                    hash=0
                                ))
                                if not result.participants:
                                    break
                                all_participants.extend(result.participants)
                                offset += len(result.participants)
                                await event.respond(f"Found {len(all_participants)} users so far...")
                                if len(result.participants) < limit:
                                    break
                            except Exception as e:
                                await event.respond(f"Error getting more participants: {str(e)}")
                                break
                        
                        participants = all_participants
                    else:
                        # For normal groups
                        await event.respond("Getting participants from normal group...")
                        participants = await self.client.get_participants(group_entity)
                except Exception as e:
                    await event.respond(f"Error getting participants: {str(e)}")
                    return
                
                if not participants:
                    await event.respond("No participants found in the group.")
                    return
                
                await event.respond(f"Found {len(participants)} participants. Starting to send messages...")
                
                # Process participants
                success_count = 0
                for participant in participants:
                    # For ChannelParticipant objects that have user_id directly
                    if hasattr(participant, 'user_id'):
                        try:
                            user_to_message = await self.client.get_entity(participant.user_id)
                            await self.client.send_message(user_to_message, message)
                            success_count += 1
                            await asyncio.sleep(1)  # Delay to avoid hitting limits
                        except Exception as e:
                            logger.error(f"Failed to send message to {participant.user_id}: {str(e)}")
                        continue
                
                    # For other participant types
                    # Safely check if user is a bot
                    is_bot = False
                    if hasattr(participant, 'bot'):
                        is_bot = participant.bot
                    elif hasattr(participant, 'user') and hasattr(participant.user, 'bot'):
                        is_bot = participant.user.bot
                    
                    # Only process if not a bot
                    if not is_bot:
                        try:
                            # Get user entity - this might be participant directly or participant.user
                            user_to_message = participant
                            if hasattr(participant, 'user'):
                                user_to_message = participant.user
                            
                            await self.client.send_message(user_to_message, message)
                            success_count += 1
                            await asyncio.sleep(1)  # Delay to avoid hitting limits
                        except FloodWaitError as e:
                            wait_time = e.seconds
                            await event.respond(f"Hit rate limit. Waiting for {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            # Try again after waiting
                            try:
                                await self.client.send_message(user_to_message, message)
                                success_count += 1
                            except Exception as e2:
                                user_id = getattr(participant, 'id', 'unknown')
                                if hasattr(participant, 'user') and hasattr(participant.user, 'id'):
                                    user_id = participant.user.id
                                logger.error(f"Failed to send message to {user_id} after waiting: {str(e2)}")
                        except Exception as e:
                            user_id = getattr(participant, 'id', 'unknown')
                            if hasattr(participant, 'user') and hasattr(participant.user, 'id'):
                                user_id = participant.user.id
                            logger.error(f"Failed to send message to {user_id}: {str(e)}")
                
                await event.respond(f"Message sent successfully to {success_count} out of {len(participants)} users.")
            
            except Exception as e:
                logger.error(f"Error in send_group: {e}")
                await event.respond(f"Error: {str(e)}")
                await event.respond("Try using /my_groups to list available groups first.")

        @self.client.on(events.NewMessage(pattern='/move'))
        async def move_members_handler(event):
            args = event.text.split(' ', 2)
            
            if len(args) < 3:
                await event.respond("Please provide source and target group IDs: /move <source_group_id> <target_group_id>")
                return
            
            source_group_id = args[1].strip()
            target_group_id = args[2].strip()
            
            await event.respond(f"Starting to move members from {source_group_id} to {target_group_id}...")
            
            try:
                # Find source group entity
                source_entity = None
                
                # Check if we have a cached entity
                if hasattr(self, 'found_entities') and source_group_id in self.found_entities:
                    source_entity = self.found_entities[source_group_id]
                    await event.respond(f"Using cached source group: {getattr(source_entity, 'title', 'Unknown')}")
                else:
                    # Try to find in dialogs
                    async for dialog in self.client.iter_dialogs():
                        dialog_id = dialog.id
                        if str(dialog_id) == str(source_group_id) or str(abs(dialog_id)) == str(source_group_id) or \
                           (source_group_id.isdigit() and str(abs(dialog_id)).endswith(str(source_group_id))):
                            source_entity = dialog.entity
                            await event.respond(f"Found source group in dialogs: {dialog.title}")
                            break
                    
                    # If still not found, try direct lookup
                    if not source_entity and source_group_id.isdigit():
                        try:
                            channel_id = int(f"-100{source_group_id}")
                            source_entity = await self.client.get_entity(channel_id)
                            await event.respond(f"Found source group by ID: {getattr(source_entity, 'title', 'Unknown')}")
                        except Exception as e:
                            await event.respond(f"Could not find source group with ID {source_group_id}: {str(e)}")
                
                # Find target group entity with the same approach
                target_entity = None
                
                # Check if we have a cached entity
                if hasattr(self, 'found_entities') and target_group_id in self.found_entities:
                    target_entity = self.found_entities[target_group_id]
                    await event.respond(f"Using cached target group: {getattr(target_entity, 'title', 'Unknown')}")
                else:
                    # Try to find in dialogs
                    async for dialog in self.client.iter_dialogs():
                        dialog_id = dialog.id
                        if str(dialog_id) == str(target_group_id) or str(abs(dialog_id)) == str(target_group_id) or \
                           (target_group_id.isdigit() and str(abs(dialog_id)).endswith(str(target_group_id))):
                            target_entity = dialog.entity
                            await event.respond(f"Found target group in dialogs: {dialog.title}")
                            break
                    
                    # If still not found, try direct lookup
                    if not target_entity and target_group_id.isdigit():
                        try:
                            channel_id = int(f"-100{target_group_id}")
                            target_entity = await self.client.get_entity(channel_id)
                            await event.respond(f"Found target group by ID: {getattr(target_entity, 'title', 'Unknown')}")
                        except Exception as e:
                            await event.respond(f"Could not find target group with ID {target_group_id}: {str(e)}")
                
                if not source_entity or not target_entity:
                    await event.respond("Error: Could not find one or both groups. Please use /my_groups to list available groups.")
                    return
                
                # Cache these entities for future use
                if not hasattr(self, 'found_entities'):
                    self.found_entities = {}
                self.found_entities[source_group_id] = source_entity
                self.found_entities[target_group_id] = target_entity
                
                # Get source group participants
                try:
                    participants = []
                    if hasattr(source_entity, 'id') and hasattr(source_entity, 'access_hash'):
                        # For supergroups/channels
                        input_channel = InputChannel(source_entity.id, source_entity.access_hash)
                        
                        # Use direct API call with pagination
                        offset = 0
                        limit = 200
                        all_participants = []
                        
                        await event.respond("Getting participants from source group...")
                        while True:
                            try:
                                result = await self.client(GetParticipantsRequest(
                                    channel=input_channel,
                                    filter=ChannelParticipantsSearch(''),
                                    offset=offset,
                                    limit=limit,
                                    hash=0
                                ))
                                if not result.participants:
                                    break
                                all_participants.extend(result.participants)
                                offset += len(result.participants)
                                await event.respond(f"Found {len(all_participants)} users so far...")
                                if len(result.participants) < limit:
                                    break
                            except Exception as e:
                                await event.respond(f"Error getting more participants: {str(e)}")
                                break
                        
                        participants = all_participants
                    else:
                        # For normal groups
                        await event.respond("Getting participants from normal group...")
                        participants = await self.client.get_participants(source_entity)
                except Exception as e:
                    await event.respond(f"Error getting participants: {str(e)}")
                    return
                
                if not participants:
                    await event.respond("No participants found in the source group.")
                    return
                
                # Target group info for the add_to_channel function
                try:
                    target_channel = await self.client.get_entity(target_entity)
                    
                    # Determine if target is a basic group or a supergroup/channel
                    is_target_basic_group = False
                    
                    # Check group ID format - basic groups have regular negative IDs (not -100...)
                    target_id_str = str(target_channel.id)
                    if target_id_str.startswith('-') and not target_id_str.startswith('-100'):
                        is_target_basic_group = True
                        
                    await event.respond(f"Target group type: {'Basic group' if is_target_basic_group else 'Supergroup/Channel'}")
                    
                    # For basic groups, we need to extract the chat_id (remove the negative sign)
                    if is_target_basic_group:
                        target_chat_id = abs(target_channel.id)
                        await event.respond(f"Using AddChatUserRequest for basic target group (chat_id: {target_chat_id})")
                    
                except Exception as e:
                    await event.respond(f"Error getting target group entity: {str(e)}")
                    return
                
                await event.respond(f"Found {len(participants)} participants. Starting to add them to target group...")
                
                # Process participants
                success_count = 0
                channel_errors = 0
                my_id_obj = await self.client.get_me()
                my_id = my_id_obj.id
                for participant in participants:
                    # For ChannelParticipant objects with direct user_id
                    if hasattr(participant, 'user_id'):
                        user_id = participant.user_id
                        if user_id != my_id:  # Skip yourself
                            try:
                                user_to_add = await self.client.get_entity(user_id)
                                
                                # Use appropriate API call based on target group type
                                if is_target_basic_group:
                                    # Add to basic group
                                    await self.client(AddChatUserRequest(
                                        chat_id=target_chat_id,
                                        user_id=user_to_add,
                                        fwd_limit=100
                                    ))
                                else:
                                    # Add to supergroup/channel
                                    await self.client(InviteToChannelRequest(
                                        channel=target_channel,
                                        users=[user_to_add]
                                    ))
                                    
                                success_count += 1
                                await asyncio.sleep(1)  # Delay to avoid hitting limits
                            except Exception as e:
                                error_msg = str(e)
                                # If we encounter an InputPeerChat error, we may have misidentified the group type
                                if "Cannot cast InputPeerChat to any kind of InputChannel" in error_msg:
                                    channel_errors += 1
                                    logger.error(f"Failed to add {user_id}: {error_msg}")
                                    
                                    # If we have multiple errors of this type, switch to basic group method
                                    if channel_errors >= 2 and not is_target_basic_group and success_count == 0:
                                        await event.respond("Detected possible basic group. Switching methods...")
                                        
                                        # Try using AddChatUserRequest instead
                                        try:
                                            target_chat_id = abs(target_channel.id)
                                            await event.respond(f"Trying AddChatUserRequest with chat_id: {target_chat_id}")
                                            
                                            # Try again with the basic group method
                                            await self.client(AddChatUserRequest(
                                                chat_id=target_chat_id,
                                                user_id=user_to_add,
                                                fwd_limit=100
                                            ))
                                            success_count += 1
                                            
                                            # If successful, change mode for remaining users
                                            is_target_basic_group = True
                                            await event.respond("Switching to basic group mode for remaining users")
                                        except Exception as ce:
                                            logger.error(f"Failed with basic group method too: {str(ce)}")
                                else:
                                    if isinstance(e, FloodWaitError):
                                        wait_time = e.seconds
                                        await event.respond(f"Hit rate limit. Waiting for {wait_time} seconds...")
                                        await asyncio.sleep(wait_time)
                                        # Try again after waiting
                                        try:
                                            user_to_add = await self.client.get_entity(user_id)
                                            
                                            # Use appropriate API call based on group type
                                            if is_target_basic_group:
                                                await self.client(AddChatUserRequest(
                                                    chat_id=target_chat_id,
                                                    user_id=user_to_add,
                                                    fwd_limit=100
                                                ))
                                            else:
                                                await self.client(InviteToChannelRequest(
                                                    channel=target_channel,
                                                    users=[user_to_add]
                                                ))
                                                
                                            success_count += 1
                                        except Exception as e2:
                                            logger.error(f"Failed to add {user_id} after waiting: {str(e2)}")
                                    elif isinstance(e, (UserPrivacyRestrictedError, UserNotMutualContactError)):
                                        logger.warning(f"Couldn't add {user_id} due to privacy settings")
                                    else:
                                        logger.error(f"Failed to add {user_id}: {str(e)}")
                        continue
                                
                    # For other types of participants
                    # Safely check if user is a bot
                    is_bot = False
                    if hasattr(participant, 'bot'):
                        is_bot = participant.bot
                    elif hasattr(participant, 'user') and hasattr(participant.user, 'bot'):
                        is_bot = participant.user.bot
                    
                    # Get user ID safely
                    user_id = getattr(participant, 'id', None)
                    if user_id is None and hasattr(participant, 'user'):
                        user_id = getattr(participant.user, 'id', None)
                    
                    # Only process if not a bot and not yourself
                    if not is_bot and user_id is not None and user_id != my_id:
                        try:
                            # Get user entity to add
                            user_to_add = await self.client.get_entity(user_id)
                            
                            # Use appropriate API call based on target group type
                            if is_target_basic_group:
                                # Add to basic group
                                await self.client(AddChatUserRequest(
                                    chat_id=target_chat_id,
                                    user_id=user_to_add,
                                    fwd_limit=100
                                ))
                            else:
                                # Add to supergroup/channel
                                await self.client(InviteToChannelRequest(
                                    channel=target_channel,
                                    users=[user_to_add]
                                ))
                                
                            success_count += 1
                            await asyncio.sleep(1)  # Delay to avoid hitting limits
                        except Exception as e:
                            error_msg = str(e)
                            # If we encounter an InputPeerChat error, we may have misidentified the group type
                            if "Cannot cast InputPeerChat to any kind of InputChannel" in error_msg:
                                channel_errors += 1
                                logger.error(f"Failed to add {user_id}: {error_msg}")
                                
                                # If we have multiple errors of this type, switch to basic group method
                                if channel_errors >= 2 and not is_target_basic_group and success_count == 0:
                                    await event.respond("Detected possible basic group. Switching methods...")
                                    
                                    # Try using AddChatUserRequest instead
                                    try:
                                        target_chat_id = abs(target_channel.id)
                                        await event.respond(f"Trying AddChatUserRequest with chat_id: {target_chat_id}")
                                        
                                        # Try again with the basic group method
                                        await self.client(AddChatUserRequest(
                                            chat_id=target_chat_id,
                                            user_id=user_to_add,
                                            fwd_limit=100
                                        ))
                                        success_count += 1
                                        
                                        # If successful, change mode for remaining users
                                        is_target_basic_group = True
                                        await event.respond("Switching to basic group mode for remaining users")
                                    except Exception as ce:
                                        logger.error(f"Failed with basic group method too: {str(ce)}")
                            else:
                                if isinstance(e, FloodWaitError):
                                    wait_time = e.seconds
                                    await event.respond(f"Hit rate limit. Waiting for {wait_time} seconds...")
                                    await asyncio.sleep(wait_time)
                                    # Try again after waiting
                                    try:
                                        user_to_add = await self.client.get_entity(user_id)
                                        
                                        # Use appropriate API call based on group type
                                        if is_target_basic_group:
                                            await self.client(AddChatUserRequest(
                                                chat_id=target_chat_id,
                                                user_id=user_to_add,
                                                fwd_limit=100
                                            ))
                                        else:
                                            await self.client(InviteToChannelRequest(
                                                channel=target_channel,
                                                users=[user_to_add]
                                            ))
                                            
                                        success_count += 1
                                    except Exception as e2:
                                        logger.error(f"Failed to add {user_id} after waiting: {str(e2)}")
                                elif isinstance(e, (UserPrivacyRestrictedError, UserNotMutualContactError)):
                                    logger.warning(f"Couldn't add {user_id} due to privacy settings")
                                else:
                                    logger.error(f"Failed to add {user_id}: {str(e)}")
                
                await event.respond(f"Successfully added {success_count} out of {len(participants)} users to the target group.")
            
            except Exception as e:
                logger.error(f"Error in move_members: {e}")
                await event.respond(f"Error: {str(e)}")
                await event.respond("Try using /my_groups to list available groups first.")

        @self.client.on(events.NewMessage(pattern='/add'))
        async def add_to_group_handler(event):
            """Handler for the add command. Adds users from collected IDs to a group."""
            try:
                # Format: /add @group_username or /add -100123456789
                args = event.text.split(maxsplit=1)
                if len(args) < 2:
                    await event.respond("Usage: /add @group_username or /add -100123456789")
                    return
                
                target_entity = args[1].strip()
                
                # Check if we have collected user IDs
                if not user_data.get("collected_ids", []):
                    await event.respond("No IDs collected. Please use /collect_ids first.")
                    return
                
                # Target group info for the add_to_channel function
                try:
                    target_channel = await self.client.get_entity(target_entity)
                    
                    # Determine if target is a basic group or a supergroup/channel
                    is_basic_group = False
                    
                    # Check group ID format - basic groups have regular negative IDs (not -100...)
                    target_id_str = str(target_channel.id)
                    if target_id_str.startswith('-') and not target_id_str.startswith('-100'):
                        is_basic_group = True
                        
                    await event.respond(f"Target group type: {'Basic group' if is_basic_group else 'Supergroup/Channel'}")
                    await event.respond(f"Target group ID: {target_channel.id}")
                    
                    # For basic groups, we need to extract the chat_id (remove the negative sign)
                    chat_id = None
                    if is_basic_group:
                        chat_id = abs(target_channel.id)
                        await event.respond(f"Using AddChatUserRequest for basic group (chat_id: {chat_id})")
                    
                except Exception as e:
                    await event.respond(f"Error getting target group entity: {str(e)}")
                    return
                
                success_count = 0
                channel_errors = 0
                my_id_obj = await self.client.get_me()
                my_id = my_id_obj.id
                
                # Process each ID with appropriate error handling
                for user_id in user_data["collected_ids"]:
                    if user_id == my_id:  # Skip self
                        continue
                        
                    try:
                        # Get user entity to add
                        user_to_add = await self.client.get_entity(user_id)
                        
                        # Use appropriate API call based on group type
                        if is_basic_group:
                            await self.client(AddChatUserRequest(
                                chat_id=chat_id,
                                user_id=user_to_add,
                                fwd_limit=100
                            ))
                        else:
                            await self.client(InviteToChannelRequest(
                                channel=target_channel,
                                users=[user_to_add]
                            ))
                            
                        success_count += 1
                        await asyncio.sleep(2)  # Wait to avoid rate limits
                    except Exception as e:
                        error_msg = str(e)
                        # If we encounter an InputPeerChat error, we may have misidentified the group type
                        if "Cannot cast InputPeerChat to any kind of InputChannel" in error_msg:
                            channel_errors += 1
                            logger.error(f"Failed to add {user_id}: {error_msg}")
                            
                            # If we have multiple errors of this type, switch to basic group method
                            if channel_errors >= 2 and not is_basic_group and success_count == 0:
                                await event.respond("Detected possible basic group. Switching methods...")
                                
                                # Try using AddChatUserRequest instead
                                try:
                                    chat_id = abs(target_channel.id)
                                    await event.respond(f"Trying AddChatUserRequest with chat_id: {chat_id}")
                                    
                                    # Try again with the basic group method
                                    await self.client(AddChatUserRequest(
                                        chat_id=chat_id,
                                        user_id=user_to_add,
                                        fwd_limit=100
                                    ))
                                    success_count += 1
                                    
                                    # If successful, change mode for remaining users
                                    is_basic_group = True
                                    await event.respond("Switching to basic group mode for remaining users")
                                except Exception as ce:
                                    logger.error(f"Failed with basic group method too: {str(ce)}")
                        else:
                            if isinstance(e, FloodWaitError):
                                wait_time = e.seconds
                                await event.respond(f"Hit rate limit. Waiting for {wait_time} seconds...")
                                await asyncio.sleep(wait_time)
                                
                                # Try again after waiting
                                try:
                                    user_to_add = await self.client.get_entity(user_id)
                                    
                                    # Use appropriate API call based on group type
                                    if is_basic_group:
                                        await self.client(AddChatUserRequest(
                                            chat_id=chat_id,
                                            user_id=user_to_add,
                                            fwd_limit=100
                                        ))
                                    else:
                                        await self.client(InviteToChannelRequest(
                                            channel=target_channel,
                                            users=[user_to_add]
                                        ))
                                        
                                    success_count += 1
                                except Exception as e2:
                                    logger.error(f"Failed to add {user_id} after waiting: {str(e2)}")
                            elif isinstance(e, (UserPrivacyRestrictedError, UserNotMutualContactError)):
                                logger.warning(f"Couldn't add {user_id} due to privacy settings")
                            else:
                                logger.error(f"Failed to add {user_id}: {str(e)}")
                
                await event.respond(f"Successfully added {success_count} out of {len(user_data['collected_ids'])} users to the target group.")
            
            except Exception as e:
                await event.respond(f"Error in add_to_group: {str(e)}")

        @self.client.on(events.NewMessage(pattern='/chat_collect'))
        async def chat_collect_handler(event):
            """Collects user IDs from chat messages in a group."""
            try:
                # Parse command arguments more carefully
                text = event.text.strip()
                parts = text.split(maxsplit=2)  # Split into command, group_id, and possibly limit
                
                if len(parts) < 2:
                    await event.respond("Please provide the group ID or username: /chat_collect <group_id/username> [limit]")
                    return
                
                # Get group ID (second part)
                target_info = parts[1].strip()
                
                # Check for limit parameter (optional, third part if exists)
                limit = 100  # Default limit
                if len(parts) > 2 and parts[2].isdigit():
                    limit = int(parts[2])
                    limit = min(limit, 500)  # Cap at 500 to avoid overload
                
                await event.respond(f"Target group: {target_info}, Limit: {limit}")
                
                # Find the target chat - try to handle different ID formats
                try:
                    target_chat = None
                    
                    # For numerical IDs, try to handle standard formats
                    if target_info.lstrip('-').isdigit():
                        # Format ID properly - handle both with and without -100 prefix
                        formatted_ids = [
                            target_info,  # Original ID
                            f"-100{target_info.lstrip('-')}",  # With -100 prefix
                        ]
                        
                        # If ID starts with -100, also try without it
                        if target_info.startswith('-100'):
                            formatted_ids.append(target_info[4:])  # Without -100 prefix
                            
                        # Try each format
                        for formatted_id in formatted_ids:
                            try:
                                target_chat = await self.client.get_entity(int(formatted_id))
                                await event.respond(f"Found chat by ID format: {formatted_id}")
                                break
                            except Exception:
                                continue
                    
                    # If still not found, try to find in dialogs
                    if not target_chat:
                        await event.respond("Searching for group in your dialogs...")
                        async for dialog in self.client.iter_dialogs():
                            # Match numerical IDs
                            if target_info.lstrip('-').isdigit():
                                dialog_id = str(dialog.id)
                                # Try different ID format matching
                                if (dialog_id == target_info or 
                                    str(abs(dialog.id)) == target_info.lstrip('-') or
                                    (target_info.startswith('-100') and dialog_id.endswith(target_info[4:])) or
                                    (dialog_id.startswith('-100') and dialog_id.endswith(target_info.lstrip('-')))):
                                    target_chat = dialog.entity
                                    await event.respond(f"Found group in dialogs: {dialog.title} (ID: {dialog.id})")
                                    break
                            # Match by name or username
                            elif ((not target_info.lstrip('-').isdigit()) and 
                                  (dialog.title.lower() == target_info.lower() or
                                  (hasattr(dialog.entity, 'username') and 
                                   dialog.entity.username and 
                                   dialog.entity.username.lower() == target_info.lower().strip('@')))):
                                target_chat = dialog.entity
                                await event.respond(f"Found group in dialogs: {dialog.title} (ID: {dialog.id})")
                                break
                    
                    # Last attempt - try direct lookup if all else failed
                    if not target_chat:
                        try:
                            # Try as username if not numeric
                            if not target_info.lstrip('-').isdigit():
                                if target_info.startswith('@'):
                                    target_info = target_info[1:]
                                await event.respond(f"Trying to find group by username: {target_info}")
                                target_chat = await self.client.get_entity(target_info)
                            # Last resort for numeric ID
                            else:
                                await event.respond("All ID formats failed, trying as PeerChannel...")
                                if target_info.startswith('-100'):
                                    channel_id = int(target_info[4:])
                                    target_chat = await self.client.get_entity(PeerChannel(channel_id))
                        except Exception as e:
                            await event.respond(f"Final lookup attempt failed: {str(e)}")
                    
                    if not target_chat:
                        await event.respond("Could not find the specified chat. Try one of these options:\n1. Use /my_groups to see your available groups\n2. Make sure the ID format is correct\n3. Make sure you are a member of this group")
                        return
                    
                    await event.respond(f"Successfully found group: {getattr(target_chat, 'title', 'Unknown')}")
                    
                    # Get messages from the chat
                    await event.respond(f"Retrieving up to {limit} messages from the chat...")
                    messages = await self.client.get_messages(target_chat, limit=limit)
                    
                    # Collect unique user IDs from messages
                    user_ids = set()
                    sender_names = {}
                    
                    for message in messages:
                        if message.sender_id and message.sender_id > 0:  # Skip null or channel IDs
                            user_ids.add(message.sender_id)
                            if hasattr(message, 'sender') and message.sender:
                                sender_name = f"{getattr(message.sender, 'first_name', '')} {getattr(message.sender, 'last_name', '')}".strip()
                                if sender_name:
                                    sender_names[message.sender_id] = sender_name
                    
                    # Display results and save to user_data
                    user_data["collected_ids"] = list(user_ids)
                    await save_data()
                    
                    # Show first few users with names if available
                    await event.respond(f"Successfully collected {len(user_ids)} unique user IDs from chat messages.")
                    if sender_names:
                        sample_users = list(sender_names.items())[:5]  # Show first 5 users
                        users_info = "\n".join([f"- ID: {uid}, Name: {name}" for uid, name in sample_users])
                        await event.respond(f"Sample users:\n{users_info}\n...")
                    
                    await event.respond("You can now use /add or /send_pm commands with these collected IDs.")
                
                except Exception as e:
                    logger.error(f"Error in chat_collect_details: {str(e)}")
                    await event.respond(f"Error collecting chat users: {str(e)}")
            
            except Exception as e:
                logger.error(f"Error in chat_collect: {str(e)}")
                await event.respond(f"General error in chat_collect command: {str(e)}")
                await event.respond("Try using /my_groups to list your available groups first.")
                
        @self.client.on(events.NewMessage(pattern='/chat_send'))
        async def chat_send_handler(event):
            """Sends a message to users who participated in a chat."""
            try:
                text = event.text
                # Extract the command, target info, and message
                if ' ' not in text:
                    await event.respond("Please provide the group ID/username and message: /chat_send <group_id/username> <message>")
                    return
                    
                command_parts = text.split(' ', 2)  # Split into 3 parts max: command, target, message
                
                if len(command_parts) < 3:
                    await event.respond("Please provide the group ID/username and message: /chat_send <group_id/username> <message>")
                    return
                
                target_info = command_parts[1].strip()
                message = command_parts[2].strip()
                
                await event.respond(f"Target: {target_info}, Message length: {len(message)} chars")
                
                # Check if message is empty
                if not message:
                    await event.respond("Please provide a message to send.")
                    return
                
                # Find the target chat
                try:
                    target_chat = None
                    
                    # Try to find in current dialog list first
                    async for dialog in self.client.iter_dialogs():
                        if (target_info.isdigit() and (str(dialog.id) == target_info or str(abs(dialog.id)) == target_info)) or \
                           (not target_info.isdigit() and dialog.title.lower() == target_info.lower()) or \
                           (hasattr(dialog.entity, 'username') and dialog.entity.username and dialog.entity.username.lower() == target_info.lower().strip('@')):
                            target_chat = dialog.entity
                            await event.respond(f"Found chat: {dialog.title} (ID: {dialog.id})")
                            break
                    
                    # If not found in dialogs, try direct approach
                    if not target_chat:
                        target_chat = await self.client.get_entity(target_info)
                        await event.respond(f"Found chat by ID/username: {getattr(target_chat, 'title', target_info)}")
                    
                    if not target_chat:
                        await event.respond("Could not find the specified chat. Make sure you are a member of this group.")
                        return
                    
                    # First collect the user IDs
                    await event.respond("Collecting user IDs from recent messages...")
                    messages = await self.client.get_messages(target_chat, limit=100)
                    
                    # Collect unique user IDs from messages
                    user_ids = set()
                    for message in messages:
                        if message.sender_id and message.sender_id > 0:  # Skip null or channel IDs
                            user_ids.add(message.sender_id)
                    
                    # Exclude yourself
                    my_id_obj = await self.client.get_me()
                    my_id = my_id_obj.id
                    if my_id in user_ids:
                        user_ids.remove(my_id)
                    
                    if not user_ids:
                        await event.respond("No valid user IDs found in recent messages.")
                        return
                    
                    # Send messages to collected users
                    await event.respond(f"Starting to send message to {len(user_ids)} users...")
                    
                    success_count = 0
                    for user_id in user_ids:
                        try:
                            user = await self.client.get_entity(user_id)
                            await self.client.send_message(user, message)
                            success_count += 1
                            await asyncio.sleep(1)  # Delay to avoid hitting limits
                        except FloodWaitError as e:
                            wait_time = e.seconds
                            await event.respond(f"Hit rate limit. Waiting for {wait_time} seconds...")
                            await asyncio.sleep(wait_time)
                            # Try again after waiting
                            try:
                                user = await self.client.get_entity(user_id)
                                await self.client.send_message(user, message)
                                success_count += 1
                            except Exception as e2:
                                logger.error(f"Failed to send message to {user_id} after waiting: {str(e2)}")
                        except Exception as e:
                            logger.error(f"Failed to send message to {user_id}: {str(e)}")
                    
                    await event.respond(f"Message sent successfully to {success_count} out of {len(user_ids)} users.")
                
                except Exception as e:
                    await event.respond(f"Error sending messages to chat users: {str(e)}")
            
            except Exception as e:
                await event.respond(f"Error in chat_send: {str(e)}")

        @self.client.on(events.NewMessage())
        async def join_and_collect_handler(event):
            message_text = event.raw_text.strip()
            
            # Check for message that contains t.me link followed by collect IDs request
            if 't.me/' in message_text:
                try:
                    # Extract group username from t.me link
                    parts = message_text.split('t.me/')
                    if len(parts) > 1:
                        group_username = parts[1].strip()
                        await event.respond(f"Attempting to join and collect from group: {group_username}")
                        
                        try:
                            # Attempt to join the group first
                            await self.client.get_entity(group_username)
                            await self.client(JoinChannelRequest(group_username))
                            await event.respond(f"Successfully joined {group_username}")
                            
                            # Now collect IDs
                            chat = await self.client.get_entity(group_username)
                            
                            # Get participants
                            participants = await self.client.get_participants(chat)
                            
                            # Process participants
                            user_data["collected_ids"] = []
                            
                            # Debug info about participants
                            if participants and len(participants) > 0:
                                first_participant = participants[0]
                                await event.respond(f"Debug: First participant type: {type(first_participant).__name__}")
                            
                            for participant in participants:
                                # Handle ChannelParticipant objects
                                if hasattr(participant, 'user_id'):
                                    user_data["collected_ids"].append(participant.user_id)
                                    continue
                                    
                                # Handle other participant types
                                if not participant.bot:  # Skip bots
                                    user_data["collected_ids"].append(participant.id)
                            
                            # Save and report results
                            await save_data()
                            await event.respond(f"Successfully collected {len(user_data['collected_ids'])} user IDs from the group.")
                            
                        except Exception as e:
                            await event.respond(f"Error joining or collecting from group: {str(e)}")
                            await event.respond("Tip: Make sure the group is public and the username is correct.")
                except Exception as e:
                    logger.error(f"Error processing t.me link: {e}")

        @self.client.on(events.NewMessage(pattern='/join'))
        async def join_group_handler(event):
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the group username: /join <group_username>")
                return
            
            group_name = args[1].strip()
            # Remove @ symbol if present
            if group_name.startswith('@'):
                group_name = group_name[1:] 
                
            await event.respond(f"Attempting to join group: {group_name}")
            
            try:
                # Try to join the group
                await self.client(JoinChannelRequest(group_name))
                await event.respond(f"Successfully joined {group_name}")
            except Exception as e:
                await event.respond(f"Error joining group: {str(e)}")
                await event.respond("Check that the group is public and the username is correct.")
                
        @self.client.on(events.NewMessage(pattern='/join_collect'))
        async def join_and_collect_command(event):
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the group username: /join_collect <group_username>")
                return
            
            group_name = args[1].strip()
            # Remove @ symbol if present
            if group_name.startswith('@'):
                group_name = group_name[1:]
                
            await event.respond(f"Attempting to join and collect from group: {group_name}")
            
            try:
                # Try to join the group
                await self.client(JoinChannelRequest(group_name))
                await event.respond(f"Successfully joined {group_name}")
                
                # Now collect IDs
                chat = await self.client.get_entity(group_name)
                
                # Get participants
                participants = await self.client.get_participants(chat)
                
                # Process participants
                user_data["collected_ids"] = []
                
                # Debug info
                if participants and len(participants) > 0:
                    first_participant = participants[0]
                    await event.respond(f"Debug: First participant type: {type(first_participant).__name__}")
                
                for participant in participants:
                    # Handle ChannelParticipant objects
                    if hasattr(participant, 'user_id'):
                        user_data["collected_ids"].append(participant.user_id)
                        continue
                        
                    # Handle other participant types
                    if not participant.bot:  # Skip bots
                        user_data["collected_ids"].append(participant.id)
                
                # Save and report results
                await save_data()
                await event.respond(f"Successfully collected {len(user_data['collected_ids'])} user IDs from the group.")
                
            except Exception as e:
                await event.respond(f"Error joining or collecting from group: {str(e)}")
                await event.respond("Make sure the group is public and the username is correct. You may need to try a few times.")

        @self.client.on(events.NewMessage(pattern='/my_groups'))
        async def list_my_groups(event):
            await event.respond("Fetching your groups... This may take a moment.")
            
            group_count = 0
            async for dialog in self.client.iter_dialogs():
                if dialog.is_group or dialog.is_channel:
                    group_count += 1
                    group_type = "Group" if dialog.is_group else "Channel"
                    group_id = dialog.id
                    entity_id = f"-100{abs(group_id)}" if group_id < 0 and not str(group_id).startswith("-100") else group_id
                    group_name = dialog.title
                    username = f"@{dialog.entity.username}" if hasattr(dialog.entity, 'username') and dialog.entity.username else "No username"
                    
                    msg = f"**{group_type}**: {group_name}\n**ID**: `{entity_id}`\n**Username**: {username}\n"
                    msg += f"To collect IDs use: `/collect_ids {entity_id}`\n\n"
                    
                    await event.respond(msg)
                    
                    # Limit to first 20 groups to avoid spam
                    if group_count >= 20:
                        await event.respond("Showing first 20 groups only. Please be more specific if your target group is not listed.")
                        break
            
            if group_count == 0:
                await event.respond("You don't appear to be a member of any groups or channels.")
            else:
                await event.respond(f"Found {group_count} groups/channels. Use the group IDs shown above with the /collect_ids command.")

        @self.client.on(events.NewMessage(pattern='/id'))
        async def get_group_id_handler(event):
            """Get the ID of a group from its username"""
            args = event.text.split(' ', 1)
            
            if len(args) < 2:
                await event.respond("Please provide the group username: /id <group_username>")
                return
            
            group_name = args[1].strip()
            # Remove @ symbol if present
            if group_name.startswith('@'):
                group_name = group_name[1:]
                
            await event.respond(f"Looking for group: {group_name}")
            
            try:
                # Try to find in current dialog list first (most reliable method)
                found = False
                async for dialog in self.client.iter_dialogs():
                    if (dialog.is_group or dialog.is_channel) and (
                        (hasattr(dialog.entity, 'username') and dialog.entity.username and 
                         dialog.entity.username.lower() == group_name.lower()) or
                        dialog.title.lower() == group_name.lower()
                    ):
                        group_id = dialog.id
                        # Format the ID properly for supergroups/channels
                        if group_id < 0 and not str(group_id).startswith("-100"):
                            formatted_id = f"-100{abs(group_id)}"
                        else:
                            formatted_id = str(group_id)
                            
                        group_type = "Group" if dialog.is_group else "Channel"
                        title = dialog.title
                        await event.respond(f"✅ Found {group_type}: {title}\n**ID**: `{formatted_id}`")
                        found = True
                        break
                
                # If not found in dialogs, try direct lookup
                if not found:
                    try:
                        entity = await self.client.get_entity(group_name)
                        if hasattr(entity, 'id'):
                            group_id = entity.id
                            # Format the ID properly for supergroups/channels
                            if group_id < 0 and not str(group_id).startswith("-100"):
                                formatted_id = f"-100{abs(group_id)}"
                            else:
                                formatted_id = str(group_id)
                                
                            title = getattr(entity, 'title', 'Unknown')
                            group_type = "Channel" if hasattr(entity, 'broadcast') and entity.broadcast else "Group"
                            await event.respond(f"✅ Found {group_type}: {title}\n**ID**: `{formatted_id}`")
                            found = True
                    except Exception as e:
                        await event.respond(f"Error looking up group directly: {str(e)}")
                
                if not found:
                    await event.respond(f"❌ Could not find group with username: {group_name}\n"
                                       f"Make sure:\n"
                                       f"1. You are a member of this group\n"
                                       f"2. The username is correct\n"
                                       f"3. The group has a username set")
                    
            except Exception as e:
                await event.respond(f"Error getting group ID: {str(e)}")

    def run(self):
        """Run the userbot"""
        print("UserBot is running. Press Ctrl+C to stop.")
        self.client.run_until_disconnected()

if __name__ == "__main__":
    userbot = TelegramUserBot()
    userbot.run() 
    