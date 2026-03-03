# -*- coding: utf-8 -*-
"""
Telegram-бот с поддержкой OpenAI и памяти диалогов.
aiogram v3, Python 3.10+
"""

import asyncio
import base64
import json
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from aiogram.enums import ParseMode
from openai import AsyncOpenAI

from config import (
    BOT_TOKEN,
    IMAGE_MODEL,
    MAX_HISTORY_MESSAGES,
    OPENAI_API_KEY,
    OPENAI_MODEL,
    PROMPTS_PATH,
    SORA_MODEL,
)
from memory import Memory
from utils import calc_chat_cost_usd, calc_image_cost_usd, calc_video_cost_usd, usd_to_rub

# === Logging ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# === Config ===
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
memory = Memory()
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# === FSM ===
class VideoStates(StatesGroup):
    awaiting_prompt = State()


class ImageStates(StatesGroup):
    awaiting_prompt = State()


# === Prompts loader ===
def load_prompts() -> dict:
    """Загрузить промпты из prompts.json."""
    if not PROMPTS_PATH.exists():
        raise FileNotFoundError(f"Файл {PROMPTS_PATH} не найден.")
    with open(PROMPTS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def get_system_prompt(mode: str) -> str:
    """Получить системный промпт по режиму."""
    data = load_prompts()
    default = data.get("default_prompt", "assistant")
    prompts = data.get("prompts", {})
    mode_data = prompts.get(mode, prompts.get(default, {}))
    return mode_data.get("system_prompt", "Ты полезный помощник.")


def get_modes_keyboard() -> InlineKeyboardMarkup:
    """Сформировать клавиатуру выбора режима."""
    data = load_prompts()
    prompts = data.get("prompts", {})
    buttons = [
        [InlineKeyboardButton(text=p["name"], callback_data=f"mode:{key}")]
        for key, p in prompts.items()
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


# === Handlers ===

@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Команда /start."""
    logger.info("Пользователь %s запустил бота", message.from_user.id if message.from_user else "?")
    await message.answer(
        "👋 Привет! Я бот с поддержкой OpenAI.\n\n"
        "Команды:\n"
        "/mode — выбрать режим работы\n"
        "/reset — очистить историю диалога\n"
        "/video — сгенерировать видео (Sora 2)\n"
        "/image — сгенерировать изображение (GPT Image)\n"
        "/cancel — отменить текущее действие\n\n"
        "Просто напиши сообщение — я отвечу."
    )


@dp.message(Command("mode"))
async def cmd_mode(message: Message) -> None:
    """Команда /mode — выбор режима."""
    logger.debug("Пользователь %s запросил смену режима", message.from_user.id if message.from_user else "?")
    keyboard = get_modes_keyboard()
    await message.answer("Выбери режим:", reply_markup=keyboard)


@dp.callback_query(F.data.startswith("mode:"))
async def callback_mode(callback: CallbackQuery) -> None:
    """Обработка выбора режима через inline-кнопку."""
    mode = callback.data.removeprefix("mode:")
    user_id = callback.from_user.id if callback.from_user else 0
    chat_id = callback.message.chat.id if callback.message else 0

    memory.set_mode(user_id, chat_id, mode)
    logger.info("Пользователь %s выбрал режим: %s", user_id, mode)

    data = load_prompts()
    prompts = data.get("prompts", {})
    name = prompts.get(mode, {}).get("name", mode)

    await callback.answer()
    await callback.message.edit_text(f"✅ Режим: **{name}**", parse_mode=ParseMode.MARKDOWN)


@dp.message(Command("reset"))
async def cmd_reset(message: Message) -> None:
    """Команда /reset — очистить память диалога."""
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    memory.clear(user_id, chat_id)
    logger.info("Пользователь %s очистил историю чата %s", user_id, chat_id)
    await message.answer("🗑 Память диалога очищена.")


# === Video: вход в режим генерации ===
@dp.message(Command("video"))
async def cmd_video(message: Message, state: FSMContext) -> None:
    """Команда /video — войти в режим генерации видео Sora 2."""
    await state.set_state(VideoStates.awaiting_prompt)
    logger.info("Пользователь %s вошёл в режим генерации видео", message.from_user.id if message.from_user else "?")
    await message.answer(
        "🎬 Режим генерации видео (Sora 2).\n\n"
        "Опиши, что должно происходить в видео. Например:\n"
        "_«Кот идёт по солнечной улице»_\n\n"
        "Отправь промпт или /cancel для отмены."
    )


# === Image: вход в режим генерации ===
@dp.message(Command("image"))
async def cmd_image(message: Message, state: FSMContext) -> None:
    """Команда /image — войти в режим генерации изображений."""
    await state.set_state(ImageStates.awaiting_prompt)
    logger.info("Пользователь %s вошёл в режим генерации изображений", message.from_user.id if message.from_user else "?")
    await message.answer(
        f"🖼 Режим генерации изображений ({IMAGE_MODEL}).\n\n"
        "Опиши, что должно быть на картинке. Например:\n"
        "_«Кот в космическом костюме на Марсе»_\n\n"
        "Отправь промпт или /cancel для отмены."
    )


@dp.message(Command("cancel"))
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    """Отменить текущее действие (выйти из FSM)."""
    current = await state.get_state()
    if current:
        await state.clear()
        logger.info("Пользователь %s отменил действие (был в состоянии %s)", message.from_user.id if message.from_user else "?", current)
        await message.answer("❌ Действие отменено.")
    else:
        await message.answer("Нечего отменять.")


# === Video: обработка промпта и генерация ===
@dp.message(VideoStates.awaiting_prompt, F.text)
async def handle_video_prompt(message: Message, state: FSMContext) -> None:
    """Обработка промпта для генерации видео."""
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Промпт не может быть пустым. Введи описание видео.")
        return

    await state.clear()
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id

    status_msg = await message.answer("🎬 Создаю видео... Это может занять 1–2 минуты.")
    logger.info("Пользователь %s запросил видео: %s", user_id, prompt[:50])

    try:
        video_job = await openai_client.videos.create(
            prompt=prompt,
            model=SORA_MODEL,
            seconds="4",
        )
        video_id = video_job.id
        logger.info("Видео-задача создана: %s, статус: %s", video_id, video_job.status)

        while video_job.status in ("queued", "in_progress"):
            await asyncio.sleep(5)
            video_job = await openai_client.videos.retrieve(video_id)
            logger.debug("Видео %s: статус %s, прогресс %s%%", video_id, video_job.status, getattr(video_job, "progress", "?"))

        if video_job.status == "failed":
            err = getattr(video_job, "error", None)
            err_msg = err.message if err and hasattr(err, "message") else str(video_job)
            logger.error("Видео %s не создано: %s", video_id, err_msg)
            await status_msg.edit_text(f"❌ Ошибка генерации: {err_msg}")
            return

        content = await openai_client.videos.download_content(video_id)
        video_bytes = content.read()

        seconds = int(getattr(video_job, "seconds", 4) or 4)
        cost_usd = calc_video_cost_usd(SORA_MODEL, seconds)
        cost_rub = await usd_to_rub(cost_usd)

        video_file = BufferedInputFile(file=video_bytes, filename="video.mp4")
        await status_msg.delete()
        await message.answer_video(
            video=video_file,
            caption=f"🎬 Готово!\n📊 Длительность: {seconds} сек | ~{cost_rub:.2f} ₽",
        )
        logger.info("Видео %s отправлено. Стоимость: %.4f USD (~%.2f RUB)", video_id, cost_usd, cost_rub)

    except Exception as e:
        logger.exception("Ошибка генерации видео: %s", e)
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


# === Image: обработка промпта и генерация ===
@dp.message(ImageStates.awaiting_prompt, F.text)
async def handle_image_prompt(message: Message, state: FSMContext) -> None:
    """Обработка промпта для генерации изображения."""
    prompt = (message.text or "").strip()
    if not prompt:
        await message.answer("Промпт не может быть пустым. Введи описание изображения.")
        return

    await state.clear()
    user_id = message.from_user.id if message.from_user else 0

    status_msg = await message.answer("🖼 Создаю изображение...")
    logger.info("Пользователь %s запросил изображение: %s", user_id, prompt[:50])

    try:
        response = await openai_client.images.generate(
            model=IMAGE_MODEL,
            prompt=prompt,
            size="1024x1024",
            quality="medium",
            n=1,
        )

        if not response.data:
            raise ValueError("Нет данных в ответе API")

        img_data = response.data[0]
        b64 = getattr(img_data, "b64_json", None)
        if not b64:
            raise ValueError("Ответ не содержит b64_json")

        image_bytes = base64.b64decode(b64)
        cost_usd = calc_image_cost_usd(IMAGE_MODEL, n=1, quality="medium")
        cost_rub = await usd_to_rub(cost_usd)

        image_file = BufferedInputFile(file=image_bytes, filename="image.png")
        await status_msg.delete()
        await message.answer_photo(
            photo=image_file,
            caption=f"🖼 Готово!\n📊 ~{cost_rub:.4f} ₽",
        )
        logger.info("Изображение отправлено. Стоимость: %.4f USD (~%.2f RUB)", cost_usd, cost_rub)

    except Exception as e:
        logger.exception("Ошибка генерации изображения: %s", e)
        await status_msg.edit_text(f"❌ Ошибка: {str(e)}")


# === Chat: текстовые сообщения ===
@dp.message(F.text)
async def handle_message(message: Message) -> None:
    """Обработка текстовых сообщений (чат с GPT)."""
    user_id = message.from_user.id if message.from_user else 0
    chat_id = message.chat.id
    text = message.text or ""

    if not text.strip():
        return

    logger.info("Сообщение от %s (chat %s): %s", user_id, chat_id, text[:80])

    status_msg = await message.answer("⏳ Думаю...")

    try:
        state = memory.get_state(user_id, chat_id)
        if not state.messages:
            data = load_prompts()
            default_mode = data.get("default_prompt", "assistant")
            memory.set_mode(user_id, chat_id, default_mode)
            state = memory.get_state(user_id, chat_id)
        mode = state.mode
        system_prompt = get_system_prompt(mode)
        history = memory.get_messages_for_openai(user_id, chat_id)

        messages = [{"role": "system", "content": system_prompt}]
        messages.extend(history)
        messages.append({"role": "user", "content": text})

        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
        )
        reply = response.choices[0].message.content or "Пустой ответ."

        # Токены и стоимость
        usage = getattr(response, "usage", None)
        prompt_tokens = usage.prompt_tokens if usage else 0
        completion_tokens = usage.completion_tokens if usage else 0
        cost_usd = calc_chat_cost_usd(OPENAI_MODEL, prompt_tokens, completion_tokens)
        cost_rub = await usd_to_rub(cost_usd)

        logger.debug("Ответ: %d in / %d out токенов, %.6f USD", prompt_tokens, completion_tokens, cost_usd)

        memory.add_message(user_id, chat_id, "user", text)
        memory.add_message(user_id, chat_id, "assistant", reply)

        cost_footer = f"\n\n📊 Токены: вход {prompt_tokens} / выход {completion_tokens} | ~{cost_rub:.4f} ₽"

        if len(reply) + len(cost_footer) > 4096:
            await status_msg.edit_text(reply[:4096])
            for i in range(4096, len(reply), 4096):
                await message.answer(reply[i : i + 4096])
            await message.answer(cost_footer)
        else:
            await status_msg.edit_text(reply + cost_footer)

    except Exception as e:
        logger.exception("Ошибка OpenAI: %s", e)
        await status_msg.edit_text(
            f"❌ Ошибка: {str(e)}\n\nПроверь BOT_TOKEN, OPENAI_API_KEY и модель."
        )


async def main() -> None:
    """Запуск бота."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан. Создай файл .env")
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY не задан. Создай файл .env")
    if not PROMPTS_PATH.exists():
        raise FileNotFoundError(f"Файл {PROMPTS_PATH} не найден.")

    modes_count = len(load_prompts().get("prompts", {}))
    print("🤖 Бот запускается...")
    print(f"📄 Загружено режимов: {modes_count}")
    print(f"🔴 Максимум сообщений в истории: {MAX_HISTORY_MESSAGES}")
    print(f"🤖 Модель OpenAI: {OPENAI_MODEL}")
    print(f"🤖 Модель для видео: {SORA_MODEL}")
    print(f"🖼  Модель для изображений: {IMAGE_MODEL}")
    logger.info("Бот запущен, polling started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
