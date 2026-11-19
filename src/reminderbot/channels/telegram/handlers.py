"""python-telegram-bot handlers. They only translate and forward to the Router."""

from telegram import Update
from telegram.ext import ContextTypes

from reminderbot.channels.router import Router
from reminderbot.channels.telegram.adapter import TelegramChannel, event_from_update
from reminderbot.logging_setup import get_logger
from reminderbot.strings import t

log = get_logger(__name__)


def make_handlers(router: Router):
    """Build the handler functions. We use a closure so they can reach `router`."""

    async def on_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.callback_query is not None:
            # Telegram shows a loading spinner on the button until we answer.
            await update.callback_query.answer()
        event = event_from_update(update)
        if event is None:
            return
        await router.handle(event, TelegramChannel(context.bot))

    async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        log.error("handler_failed", exc_info=context.error)
        if isinstance(update, Update) and update.effective_chat is not None:
            try:
                await context.bot.send_message(update.effective_chat.id, t("error.generic"))
            except Exception:  # noqa: BLE001 - never let the error handler itself crash
                log.error("error_message_failed", exc_info=True)

    return on_update, on_error
