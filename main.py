import discord
from discord.ext import commands
import os
from dotenv import load_dotenv
import json
from datetime import datetime
import boto3
import requests
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

LAST_MESSAGE_FILE = OBSIDIAN_VAULT / "last_message_id.txt"

# S3 configuration
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

def get_last_message_id():
    try:
        with LAST_MESSAGE_FILE.open('r') as f:
            return int(f.read().strip())
    except FileNotFoundError:
        return 0

def save_last_message_id(message_id):
    with LAST_MESSAGE_FILE.open('w') as f:
        f.write(str(message_id))

def get_category_path(channel_name):
    channel_name = channel_name.lower()
    if "remember" in channel_name:
        return REMEMBER_PATH
    elif "thoughts" in channel_name:
        return THOUGHTS_PATH
    elif "meditations" in channel_name:
        return MEDITATIONS_PATH
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

# async def save_message_to_file(message, category_path):
#     today = datetime.now().strftime("%b %d, %Y")
#     file_path = category_path / f"{today}.md"
    
#     file_path.parent.mkdir(parents=True, exist_ok=True)
    
#     with file_path.open('a', encoding='utf-8') as f:
#         f.write(f"{message.content}\n")
        
#         if message.attachments:
#             for attachment in message.attachments:
#                 async with aiohttp.ClientSession() as session:
#                     try:
#                         async with session.get(attachment.url) as response:
#                             if response.status == 200:
#                                 content = await response.read()
#                                 s3_key = f'attachments/{message.id}/{attachment.filename}'
#                                 s3_url = upload_to_s3(s3_key, content)
#                                 if s3_url:
#                                     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
#                                     if attachment.filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
#                                         f.write(f"![Image {timestamp}]({s3_url})\n")
#                                     else:
#                                         f.write(f"- [{attachment.filename}]({s3_url}) {timestamp}\n")
#                                     logging.info(f"Attachment {attachment.filename} uploaded and linked")
#                                 else:
#                                     f.write(f"- {attachment.filename} (Upload to S3 failed)\n")
#                                     logging.warning(f"Failed to upload {attachment.filename} to S3")
#                             else:
#                                 f.write(f"- {attachment.filename} (Download failed)\n")
#                                 logging.warning(f"Failed to download {attachment.filename}: Status {response.status}")
#                     except Exception as e:
#                         f.write(f"- {attachment.filename} (Error processing attachment)\n")
#                         logging.error(f"Error processing attachment {attachment.filename}: {str(e)}")


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
    print("Processing historical messages...")
    last_message_id = get_last_message_id()
    
    for guild in bot.guilds:
        for channel in guild.text_channels:
            category_path = get_category_path(channel.name)
            async for message in channel.history(limit=None, after=discord.Object(id=last_message_id)):
                await save_message_to_file(message, category_path)
                last_message_id = max(last_message_id, message.id)
    
    save_last_message_id(last_message_id)
    print("Finished processing historical messages.")

@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    await process_historical_messages()

# @bot.event
# async def on_message(message):
#     if message.author == bot.user:
#         return

#     category_path = get_category_path(message.channel.name)
#     await save_message_to_file(message, category_path)
#     save_last_message_id(message.id)
#     print(f"Saved message ID: {message.id} to {category_path}")

#     await bot.process_commands(message)

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    category_path = get_category_path(message.channel.name)
    await save_message_to_file(message, category_path)
    save_last_message_id(message.id)
    print(f"Saved message ID: {message.id} to {category_path}")

    # Remove this line if you're not using command processing
    # await bot.process_commands(message)

async def main():
    check_paths()
    await bot.start(os.getenv('DISCORD_TOKEN'))

if __name__ == "__main__":
    asyncio.run(main())

    