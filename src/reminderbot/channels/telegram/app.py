"""Build the python-telegram-bot Application and run it in polling mode."""

from collections.abc import Awaitable, Callable

from telegram import Bot, BotCommand, Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from reminderbot.channels.router import Router
from reminderbot.channels.telegram.handlers import make_handlers
from reminderbot.strings import t

# Shown in Telegram's "/" menu, in this order.
MENU_COMMANDS = ["list", "today", "week", "done", "edit", "delete", "remind", "timezone", "help"]


def build_application(
    token: str,
    router: Router,
    on_startup: Callable[[Application], Awaitable[None]] | None = None,
    on_shutdown: Callable[[Application], Awaitable[None]] | None = None,
) -> Application:
    builder = Application.builder().token(token)
    if on_startup is not None:
        builder = builder.post_init(on_startup)  # runs once, after connecting to Telegram
    if on_shutdown is not None:
        builder = builder.post_shutdown(on_shutdown)  # runs once when the bot stops
    app = builder.build()
    on_update, on_error = make_handlers(router)

    # Private chats only (decision from planning). All text, commands included,
    # goes to the router, which understands commands itself; that keeps the logic
    # identical for future channels such as WhatsApp.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT, on_update))
    app.add_handler(CallbackQueryHandler(on_update))
    app.add_error_handler(on_error)
    return app


async def register_commands(bot: Bot) -> None:
    """Fill Telegram's "/" menu so users can pick a command instead of typing it."""
    await bot.set_my_commands([BotCommand(name, t(f"menu.{name}")) for name in MENU_COMMANDS])


def run_polling(app: Application) -> None:
    # Blocks until Ctrl+C. Polling is for local development; webhook mode comes in M8.
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
