# -*- coding: utf-8 -*-
"""
Утилиты: курс валют ЦБ РФ, расчёт стоимости запросов.
"""

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Цена за 1M токенов в USD (input, output)
# Источник: https://openai.com/api/pricing/
MODEL_PRICING: dict[str, tuple[float, float]] = {
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini-2024-07-18": (0.15, 0.60),
    "gpt-5-mini-2025-08-07": (0.15, 0.60),
    "gpt-3.5-turbo": (0.50, 1.50),
}
DEFAULT_PRICING = (0.15, 0.60)  # fallback

# Sora 2: $0.10/сек при 720p
SORA2_PRICE_PER_SECOND = 0.10
SORA2_PRO_PRICE_PER_SECOND = 0.30

# gpt-image-1-mini: за изображение 1024x1024
IMAGE_PRICE_LOW = 0.005
IMAGE_PRICE_MEDIUM = 0.011
IMAGE_PRICE_HIGH = 0.036

CBR_JSON_URL = "https://www.cbr-xml-daily.ru/daily_json.js"
_usd_rate_cache: float | None = None


async def get_usd_rub_rate() -> float:
    """Получить курс USD/RUB от ЦБ РФ (кэшируется в рамках сессии)."""
    global _usd_rate_cache
    if _usd_rate_cache is not None:
        return _usd_rate_cache
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(CBR_JSON_URL)
            r.raise_for_status()
            data: dict[str, Any] = r.json()
        valute = data.get("Valute", {})
        usd = valute.get("USD", {})
        if isinstance(usd, dict):
            nominal = usd.get("Nominal", 1)
            value = float(usd.get("Value", 0))
            _usd_rate_cache = value / nominal
        else:
            _usd_rate_cache = 100.0
        logger.debug("Курс USD/RUB: %s", _usd_rate_cache)
        return _usd_rate_cache
    except Exception as e:
        logger.warning("Не удалось получить курс ЦБ: %s. Используем 100 руб.", e)
        _usd_rate_cache = 100.0
        return _usd_rate_cache


def get_model_pricing(model: str) -> tuple[float, float]:
    """Вернуть (input $/1M, output $/1M) для модели."""
    for key, val in MODEL_PRICING.items():
        if key in model or model in key:
            return val
    return DEFAULT_PRICING


def calc_chat_cost_usd(
    model: str, prompt_tokens: int, completion_tokens: int
) -> float:
    """Рассчитать стоимость чат-запроса в USD."""
    inp, out = get_model_pricing(model)
    cost = (prompt_tokens / 1_000_000 * inp) + (completion_tokens / 1_000_000 * out)
    return round(cost, 8)


def calc_video_cost_usd(model: str, seconds: int) -> float:
    """Рассчитать стоимость видео в USD (Sora 2)."""
    if "pro" in model.lower():
        return round(seconds * SORA2_PRO_PRICE_PER_SECOND, 4)
    return round(seconds * SORA2_PRICE_PER_SECOND, 4)


def calc_image_cost_usd(model: str, n: int = 1, quality: str = "medium") -> float:
    """Рассчитать стоимость генерации изображений в USD (gpt-image-1-mini)."""
    prices = {"low": IMAGE_PRICE_LOW, "medium": IMAGE_PRICE_MEDIUM, "high": IMAGE_PRICE_HIGH}
    price = prices.get(quality, IMAGE_PRICE_MEDIUM)
    return round(n * price, 4)


async def usd_to_rub(usd: float) -> float:
    """Перевести USD в рубли по курсу ЦБ."""
    rate = await get_usd_rub_rate()
    return round(usd * rate, 4)
