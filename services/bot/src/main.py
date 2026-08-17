"""Telegram bot — kirish nuqtasi.

Bu yerda faqat log sozlamasi va supervisorni ishga tushirish qoladi.
Token bilan bog'liq butun mantiq `core/runner.py` da (`BotRunner`).
"""

import asyncio
import logging
import sys

from src.core.runner import BotRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
# aiogram'ning ichki loglari shovqin qilmasin
logging.getLogger("aiogram.event").setLevel(logging.WARNING)

logger = logging.getLogger("bot")


async def main() -> None:
    await BotRunner().run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("👋 Bot to'xtatildi")
        sys.exit(0)
