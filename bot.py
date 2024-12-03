import discord
from discord.ext import commands, tasks
import json
import os
import datetime
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Environment variables
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
ARCHIVE_CATEGORY_ID = os.getenv("ARCHIVE_CATEGORY_ID")
ADMIN_ROLE_ID = os.getenv("ADMIN_ROLE_ID")

# Setup logging
logging.basicConfig(
    filename="bot.log",
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# File to store archived channels data
ARCHIVE_DATA_FILE = "archive_data.json"

# Load archived channels data
def load_archive_data():
    if os.path.exists(ARCHIVE_DATA_FILE):
        with open(ARCHIVE_DATA_FILE, "r") as file:
            return json.load(file)
    return {}

# Save archived channels data
def save_archive_data(data):
    with open(ARCHIVE_DATA_FILE, "w") as file:
        json.dump(data, file, indent=4)

archive_data = load_archive_data()

# Command to start archiving a channel
@bot.command(name="archive")
async def archive_channel(ctx, channel_id: int):
    try:
        # Check for required role (optional)

        channel = bot.get_channel(channel_id)
        category = discord.utils.get(ctx.guild.categories, id=int(ARCHIVE_CATEGORY_ID))

        if not channel:
            await ctx.send("Source channel not found.")
            return

        if not category:
            await ctx.send("Archive category not found.")
            return

        # Check if the channel is already being archived
        if str(channel_id) in archive_data:
            await ctx.send("This channel is already being archived.")
            return

        # Create the archive channel in the specified category if it doesn't exist
        archive_channel_name = "channel-archives"
        archive_channel = discord.utils.get(category.channels, name=archive_channel_name)
        if not archive_channel:
            archive_channel = await category.create_text_channel(name=archive_channel_name)
            logging.info(f"Created archive channel #{archive_channel.name} in category {category.name}.")

        # Create a thread in the archive channel for this archive
        archive_thread = await archive_channel.create_thread(name=f"Archive: {channel.name}")
        logging.info(f"Created archive thread '{archive_thread.name}' for channel #{channel.name}.")

        # Save archive data
        archive_data[str(channel_id)] = {
            "archive_channel_id": archive_channel.id,
            "archive_thread_id": archive_thread.id,
            "last_message_id": None
        }
        save_archive_data(archive_data)

        await ctx.send(f"Started archiving #{channel.name} into thread '{archive_thread.name}'.")
        logging.info(f"Started archiving #{channel.name} (ID: {channel_id}).")
        await update_archive(channel_id)
    except Exception as e:
        logging.error(f"Error in archive_channel: {e}")
        await ctx.send("An error occurred while trying to start archiving. Check logs for details.")

# Update the HTML archive for a channel
async def update_archive(channel_id):
    try:
        channel_data = archive_data.get(str(channel_id))
        if not channel_data:
            return

        source_channel = bot.get_channel(channel_id)
        archive_thread = bot.get_channel(channel_data["archive_thread_id"])
        if not source_channel or not archive_thread:
            return

        # HTML file path
        local_backup_dir = "local_backup"
        os.makedirs(local_backup_dir, exist_ok=True)
        html_filename = f"{local_backup_dir}/archive-{source_channel.name}.html"

        # Get messages from the source channel
        messages = []
        last_message_id = channel_data.get("last_message_id")
        async for message in source_channel.history(after=discord.Object(id=last_message_id) if last_message_id else None, oldest_first=True):
            messages.append(message)

        if messages:
            # Update last message ID
            channel_data["last_message_id"] = messages[-1].id
            save_archive_data(archive_data)

            # Write messages to HTML file
            with open(html_filename, "a", encoding="utf-8") as file:  # Use append mode for continuous updates
                for message in messages:
                    timestamp = message.created_at.strftime('%Y-%m-%d %H:%M:%S')
                    file.write(f"<p><strong>{message.author}</strong> [{timestamp}]: {message.content}</p>")

                    # Process attachments
                    for attachment in message.attachments:
                        file.write(f"<p>Attachment: <a href='{attachment.url}'>{attachment.filename}</a></p>")

            # Upload or update the HTML file in the thread
            if not channel_data.get("initial_upload"):
                # First upload
                await archive_thread.send(file=discord.File(html_filename))
                channel_data["initial_upload"] = True
                save_archive_data(archive_data)
                logging.info(f"Uploaded initial archive for channel #{source_channel.name}.")
            else:
                # Update the thread with a new file upload
                await archive_thread.send(content="Archive updated:", file=discord.File(html_filename))
                logging.info(f"Updated archive for channel #{source_channel.name}.")
    except Exception as e:
        logging.error(f"Error in update_archive for channel ID {channel_id}: {e}")

# Task to monitor and update archives in real-time
@tasks.loop(seconds=60) 
async def monitor_archives():
    for channel_id in archive_data.keys():
        await update_archive(int(channel_id))

# Start monitoring archives when the bot is ready
@bot.event
async def on_ready():
    logging.info("Bot is ready.")
    monitor_archives.start()

# Run bot
try:
    bot.run(DISCORD_TOKEN)
except Exception as e:
    logging.critical(f"Critical error: {e}")
