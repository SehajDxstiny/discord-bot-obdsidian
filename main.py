import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
from datetime import datetime
import boto3
from botocore.exceptions import NoCredentialsError
from pathlib import Path
import asyncio
import aiohttp
import logging
from datetime import datetime


logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True  
intents.guilds = True
intents.messages = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Obsidian paths
OBSIDIAN_VAULT = Path(os.getenv('OBSIDIAN_VAULT', '~/Documents/Obsidian')).expanduser().resolve()
REMEMBER_PATH = Path(os.getenv('REMEMBER_PATH', OBSIDIAN_VAULT / 'remember days')).expanduser().resolve()
THOUGHTS_PATH = Path(os.getenv('THOUGHTS_PATH', OBSIDIAN_VAULT / 'thoughts/days')).expanduser().resolve()
MEDITATIONS_PATH = Path(os.getenv('MEDITATIONS_PATH', OBSIDIAN_VAULT / 'meditations/days')).expanduser().resolve()
LEARNINGS_PATH = Path(os.getenv('LEARNINGS_PATH', OBSIDIAN_VAULT / 'learnings/work')).expanduser().resolve()
GENERAL_PATH = Path(os.getenv('GENERAL_PATH', OBSIDIAN_VAULT / 'general')).expanduser().resolve()


LAST_MESSAGE_FILE = OBSIDIAN_VAULT / "last_message_id.txt"

HISTORICAL_CHANNEL_IDS = [
    1286285881090642015,  
    1286329619657658580,
    1286329650229936219, 
    1286329685214498929
]

s3 = boto3.client('s3',
    aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
    region_name=os.getenv('AWS_REGION')
)
BUCKET_NAME = os.getenv('S3_BUCKET_NAME')

def check_paths():
    for path in [OBSIDIAN_VAULT, REMEMBER_PATH, THOUGHTS_PATH, MEDITATIONS_PATH]:
        if not path.exists():
            print(f"Creating directory: {path}")
            path.mkdir(parents=True, exist_ok=True)

# Dictionary to hold last message IDs for each channel
channel_last_message_ids = {}

def save_last_message_id_for_channel(channel_id, message_id):
    # Read existing entries
    entries = {}
    if LAST_MESSAGE_FILE.exists():
        with open(LAST_MESSAGE_FILE, 'r') as f:
            for line in f.readlines():
                line = line.strip()
                if ':' in line:
                    ch_id, msg_id = line.split(':')
                    entries[int(ch_id)] = int(msg_id)
    
    # Update with new message ID only if it's more recent
    if channel_id not in entries or int(message_id) > entries[channel_id]:
        entries[channel_id] = int(message_id)
    
    # Write all entries back to file
    with open(LAST_MESSAGE_FILE, 'w') as f:
        for ch_id, msg_id in entries.items():
            f.write(f"{ch_id}:{msg_id}\n")
    
    logging.info(f"Channel {channel_id}: Saved last message ID - {message_id}")

def get_last_message_id_for_channel(channel_id):
    try:
        with open(LAST_MESSAGE_FILE, 'r') as f:
            latest_message_id = 0
            for line in f.readlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split(':')
                if len(parts) != 2:
                    continue
                saved_channel_id, saved_message_id = parts
                if int(saved_channel_id) == channel_id:
                    message_id = int(saved_message_id)
                    if message_id > latest_message_id:
                        latest_message_id = message_id
            return latest_message_id
    except FileNotFoundError:
        logging.error(f"File not found: {LAST_MESSAGE_FILE}")
        return 0
    except ValueError as ve:
        logging.error(f"ValueError: {ve}")
        return 0

def get_category_path(channel_name):
    channel_name = channel_name.lower()
    if "remember" in channel_name:
        return REMEMBER_PATH
    elif "thoughts" in channel_name:
        return THOUGHTS_PATH
    elif "meditations" in channel_name:
        return MEDITATIONS_PATH
    elif "general" in channel_name:
        return GENERAL_PATH
    else:
        return OBSIDIAN_VAULT / 'Uncategorized'

def upload_to_s3(file_name, file_data):
    try:
        s3.put_object(Bucket=BUCKET_NAME, Key=file_name, Body=file_data)
        logging.info(f"Successfully uploaded {file_name} to S3")
        return f"https://{BUCKET_NAME}.s3.amazonaws.com/{file_name}"
    except Exception as e:
        logging.error(f"Error uploading {file_name} to S3: {str(e)}")
    return None

async def save_message_to_file(message, category_path):
    today = datetime.now().strftime("%b %d, %Y")
    file_path = category_path / f"{today}.md"
    
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with file_path.open('a', encoding='utf-8') as f:
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        f.write(f"{message.content}\n")
        
        if message.attachments:
            for attachment in message.attachments:
                async with aiohttp.ClientSession() as session:
                    try:
                        async with session.get(attachment.url) as response:
                            if response.status == 200:
                                content = await response.read()
                                s3_key = f'attachments/{message.id}/{attachment.filename}'
                                s3_url = upload_to_s3(s3_key, content)
                                if s3_url:
                                    if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                                        f.write(f"![Image]({s3_url})\n")
                                    else:
                                        f.write(f"- [{attachment.filename}]({s3_url})\n")
                                    logging.info(f"Attachment {attachment.filename} uploaded and linked")
                                else:
                                    f.write(f"- {attachment.filename} (Upload to S3 failed)\n")
                                    logging.warning(f"Failed to upload {attachment.filename} to S3")
                            else:
                                f.write(f"- {attachment.filename} (Download failed)\n")
                                logging.warning(f"Failed to download {attachment.filename}: Status {response.status}")
                    except Exception as e:
                        f.write(f"- {attachment.filename} (Error processing attachment)\n")
                        logging.error(f"Error processing attachment {attachment.filename}: {str(e)}")
        
        f.write("\n---\n\n")


async def process_historical_messages():
    logging.info("Starting to process historical messages for specified channels...")
    
    for guild in bot.guilds:
        for channel in guild.text_channels:
            # Only process if the channel is in the historical processing list
            if channel.id not in HISTORICAL_CHANNEL_IDS:
                continue
            
            logging.info(f"Processing historical messages for channel: {channel.name} (ID: {channel.id})")
            
            category_path = get_category_path(channel.name)
            last_message_id = get_last_message_id_for_channel(channel.id)
            
            logging.info(f"Last processed message ID for channel {channel.name}: {last_message_id}")
            
            message_count = 0
            try:
                async for message in channel.history(limit=None, after=discord.Object(id=last_message_id)):
                    await save_message_to_file(message, category_path)
                    save_last_message_id_for_channel(channel.id, message.id)
                    message_count += 1
                    
                    if message_count % 100 == 0:  # Log progress every 100 messages
                        logging.info(f"Processed {message_count} messages in {channel.name}")
                
                logging.info(f"Finished processing {message_count} messages in {channel.name}")
                
            except Exception as e:
                logging.error(f"Error processing channel {channel.name}: {str(e)}")
    
    logging.info("Finished processing historical messages for specified channels.")

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await process_historical_messages()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # Process all new messages from any channel in SPECIFIED_CHANNEL_IDS
    if message.channel.id in HISTORICAL_CHANNEL_IDS:
        category_path = get_category_path(message.channel.name)
        await save_message_to_file(message, category_path)
        save_last_message_id_for_channel(message.channel.id, message.id)
        logging.info(f"Saved new message ID: {message.id} in Channel: {message.channel.id}")


async def main():
    check_paths()
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())

    