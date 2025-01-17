import os
from telegram.ext import Application, MessageHandler, filters
from mastodon import Mastodon
import logging
from dotenv import load_dotenv
import telegram
from typing import Optional
from dataclasses import dataclass

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

@dataclass
class Config:
    """Configuration class to hold all environment variables"""
    telegram_token: str
    mastodon_token: str
    mastodon_url: str
    polling_interval: float  # in seconds

    @classmethod
    def from_env(cls) -> 'Config':
        """Load configuration from environment variables"""
        load_dotenv()
        return cls(
            telegram_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            mastodon_token=os.getenv('MASTODON_ACCESS_TOKEN', ''),
            mastodon_url=os.getenv('MASTODON_INSTANCE_URL', ''),
            polling_interval=float(os.getenv('POLLING_INTERVAL', '3600'))  # default 1h
        )

class MediaHandler:
    """Handle media file operations"""
    @staticmethod
    async def download_photo(bot: telegram.Bot, photo: telegram.PhotoSize) -> str:
        """Download photo from Telegram"""
        photo_path = f"temp_{photo.file_id}.jpg"
        photo_file = await bot.get_file(photo.file_id)
        await photo_file.download_to_drive(photo_path)
        return photo_path

    @staticmethod
    def cleanup_media(file_path: str) -> None:
        """Clean up downloaded media files"""
        if os.path.exists(file_path):
            os.remove(file_path)

class MastodonHandler:
    """Handle Mastodon API operations"""
    def __init__(self, config: Config):
        self.mastodon = Mastodon(
            access_token=config.mastodon_token,
            api_base_url=config.mastodon_url
        )

    def post_text(self, text: str) -> None:
        """Post text content to Mastodon"""
        self.mastodon.status_post(text)
        logger.info("Successfully posted message to Mastodon: %.50s...", text)

    def post_media(self, media_path: str, caption: Optional[str] = None) -> None:
        """Post media content to Mastodon"""
        media_dict = self.mastodon.media_post(media_path)
        self.mastodon.status_post(
            status=caption or "",
            media_ids=[media_dict['id']]
        )
        logger.info("Successfully posted media to Mastodon")

class TelegramMastodonBot:
    """Main bot class to handle message forwarding"""
    def __init__(self, config: Config):
        self.config = config
        self.mastodon_handler = MastodonHandler(config)
        self.media_handler = MediaHandler()

    async def forward_to_mastodon(self, update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
        """Forward messages from Telegram channel to Mastodon"""
        try:
            message = update.channel_post
            
            if message and message.text:
                self.mastodon_handler.post_text(message.text)
                
            if message.photo:
                photo = message.photo[-1]  # Get the largest photo
                photo_path = await self.media_handler.download_photo(context.bot, photo)
                
                try:
                    self.mastodon_handler.post_media(photo_path, message.caption)
                finally:
                    self.media_handler.cleanup_media(photo_path)
                
        except (Mastodon.MastodonError, telegram.error.TelegramError) as e:
            logger.error("Error forwarding to Mastodon: %s", str(e))

    def run(self) -> None:
        """Start the bot"""
        application = Application.builder().token(self.config.telegram_token).build()

        # Add handler for channel posts
        application.add_handler(MessageHandler(
            filters.ChatType.CHANNEL & (filters.TEXT | filters.PHOTO),
            self.forward_to_mastodon
        ))

        # Start the bot with custom polling interval
        logger.info(f"Starting bot with polling interval of {self.config.polling_interval} seconds...")
        application.run_polling(poll_interval=self.config.polling_interval)
        logger.info("Bot started!")

def main():
    """Main entry point"""
    config = Config.from_env()
    bot = TelegramMastodonBot(config)
    bot.run()

if __name__ == '__main__':
    main()