import asyncio
import os
from contextlib import suppress
from collections import defaultdict, deque

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.types import Message
from aiogram.client.default import DefaultBotProperties

from ollama import AsyncClient

from config import MODEL_NAME, TOKEN

STREAM_EDIT_INTERVAL = 0.35
CHUNK_MIN_SIZE = 120
MAX_CONTEXT = 50

chat_histories = defaultdict(lambda: deque(maxlen=MAX_CONTEXT))


async def stream_ollama(user_id: int, prompt: str):

    client = AsyncClient()

    history = list(chat_histories[user_id])
    history.append({"role": "user", "content": prompt})

    agen = await client.chat(model=MODEL_NAME, messages=history, stream=True)
    async for part in agen:
        if "message" in part and part["message"].get("content"):
            yield part["message"]["content"]


async def handle_text(message: Message, bot: Bot):
    user_text = message.text.strip()
    user_id = message.from_user.id

    initial = await message.answer("⏳", disable_web_page_preview=True)

    buffer = ""
    last_edit_ts = 0.0

    async for token in stream_ollama(user_id, user_text):
        buffer += token
        if len(buffer) >= CHUNK_MIN_SIZE and (asyncio.get_event_loop().time() - last_edit_ts) > STREAM_EDIT_INTERVAL:
            with suppress(Exception):
                await bot.edit_message_text(
                    chat_id=initial.chat.id,
                    message_id=initial.message_id,
                    text=buffer,
                    parse_mode=ParseMode.MARKDOWN,
                    disable_web_page_preview=True,
                )
            last_edit_ts = asyncio.get_event_loop().time()

    with suppress(Exception):
        await bot.edit_message_text(
            chat_id=initial.chat.id,
            message_id=initial.message_id,
            text=buffer.strip() or "(empty)",
            parse_mode=ParseMode.MARKDOWN,
            disable_web_page_preview=True,
        )

    chat_histories[user_id].append({"role": "user", "content": user_text})
    chat_histories[user_id].append({"role": "assistant", "content": buffer.strip()})


async def main():
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
    dp = Dispatcher()

    @dp.message(F.text)
    async def on_text(message: Message):
        try:
            await handle_text(message, bot)
        except Exception as e:
            with suppress(Exception):
                await message.answer(
                    f"⚠️ Ошибка при генерации ответа:\n{e}",
                    parse_mode=ParseMode.MARKDOWN,
                )

    print("Bot started. Press Ctrl+C to stop.")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
