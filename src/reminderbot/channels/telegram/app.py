"""Build the python-telegram-bot Application and run it in polling mode."""

from telegram import Update
from telegram.ext import Application, CallbackQueryHandler, MessageHandler, filters

from reminderbot.channels.router import Router
from reminderbot.channels.telegram.handlers import make_handlers


def build_application(token: str, router: Router) -> Application:
    app = Application.builder().token(token).build()
    on_update, on_error = make_handlers(router)

    # Private chats only (decision from planning). All text, commands included,
    # goes to the router, which understands commands itself; that keeps the logic
    # identical for future channels such as WhatsApp.
    app.add_handler(MessageHandler(filters.ChatType.PRIVATE & filters.TEXT, on_update))
    app.add_handler(CallbackQueryHandler(on_update))
    app.add_error_handler(on_error)
    return app


def run_polling(app: Application) -> None:
    # Blocks until Ctrl+C. Polling is for local development; webhook mode comes in M8.
    app.run_polling(allowed_updates=[Update.MESSAGE, Update.CALLBACK_QUERY])
