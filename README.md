# Discord Obsidian Sync

A bot that synchronizes Discord messages with an Obsidian vault, categorizing and organizing content for easy reference and knowledge management.

## Features

- Categorizes messages into Remember, Thoughts, and Meditations (you can customise this)
- Organizes entries by date
- Uploads attachments to S3 and links them in notes
- Supports historical message processing
- Integrates with Amazon S3 for cloud storage

## Setup

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure the `.env` file with necessary credentials
4. Run the bot: `python bot.py`

## Configuration

Set the following environment variables:

- `OBSIDIAN_VAULT`: Path to Obsidian vault
- `REMEMBER_PATH`: Path for "remember" notes
- `THOUGHTS_PATH`: Path for "thoughts" notes
- `MEDITATIONS_PATH`: Path for "meditations" notes
- `DISCORD_TOKEN`: Your Discord bot token
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `AWS_REGION`: AWS region
- `S3_BUCKET_NAME`: S3 bucket for file storage

## Usage

Once configured and running, the bot will automatically process new messages in the specified Discord channels and categorize them in your Obsidian vault. It will also process historical messages upon startup.

## Contributing

Contributions are welcome. Please open an issue or submit a pull request with any improvements or bug fixes.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
