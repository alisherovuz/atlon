"""Entry point: runs the Telegram bot and the web admin panel together.

Both live in one process and share a database connection and the same Bot
instance, so approving a payment in the browser can message the applicant
on Telegram immediately.

Railway runs this as a web service; the panel binds to $PORT and is
reachable at the service's public domain.
"""

import asyncio
import logging

import uvicorn
from telegram import Update

import config
import db
from bot import build_application
from webapp import create_app

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("atlon-bot.main")


async def run() -> None:
    for problem in config.validate():
        logger.warning("CONFIG: %s", problem)

    if not config.BOT_TOKEN:
        raise SystemExit(
            "BOT_TOKEN is required. Set it in your environment / Railway variables."
        )

    db.init_db()

    application = build_application()
    web = create_app(application.bot)

    server = uvicorn.Server(
        uvicorn.Config(
            web,
            host="0.0.0.0",
            port=config.PORT,
            log_level="info",
            access_log=False,
        )
    )

    # `async with` handles initialize()/shutdown() around the whole run.
    async with application:
        await application.start()
        await application.updater.start_polling(allowed_updates=Update.ALL_TYPES)
        logger.info("Bot polling; admin panel on port %s", config.PORT)
        try:
            await server.serve()
        finally:
            # Stop the updater first so no update arrives mid-shutdown.
            if application.updater.running:
                await application.updater.stop()
            await application.stop()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
