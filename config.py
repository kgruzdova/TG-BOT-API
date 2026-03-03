# -*- coding: utf-8 -*-
"""
Конфигурация бота.
Переменные окружения загружаются из .env файла.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# === Bot ===
BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
"""Токен Telegram-бота (получить у @BotFather)."""

# === OpenAI ===
OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
"""Ключ API OpenAI (https://platform.openai.com/api-keys)."""

OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5-mini-2025-08-07")
"""Модель OpenAI (gpt-4o-mini, gpt-4o, gpt-3.5-turbo и т.д.)."""

SORA_MODEL: str = os.getenv("SORA_MODEL", "sora-2")
"""Модель для генерации видео (sora-2, sora-2-pro)."""

IMAGE_MODEL: str = os.getenv("IMAGE_MODEL", "gpt-image-1-mini")
"""Модель для генерации изображений (gpt-image-1-mini, gpt-image-1, gpt-image-1.5)."""

# === Memory ===
MAX_HISTORY_MESSAGES: int = int(os.getenv("MAX_HISTORY_MESSAGES", "10"))
"""Максимум сообщений в истории диалога на пользователя (user + assistant)."""

# === Paths ===
BASE_DIR: Path = Path(__file__).resolve().parent
PROMPTS_PATH: Path = BASE_DIR / "prompts.json"
MEMORY_PATH: Path = BASE_DIR / "memory.json"
"""Путь к файлу хранения памяти диалогов."""
