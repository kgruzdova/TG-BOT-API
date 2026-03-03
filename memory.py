# -*- coding: utf-8 -*-
"""
Модуль памяти диалогов.
Хранит историю сообщений пользователя и ассистента для каждого чата.
"""

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config import MAX_HISTORY_MESSAGES, MEMORY_PATH


@dataclass
class Message:
    """Сообщение в диалоге."""

    role: str  # "user" | "assistant"
    content: str

    def to_openai_format(self) -> dict[str, str]:
        """Формат для OpenAI API."""
        return {"role": self.role, "content": self.content}


@dataclass
class ChatState:
    """Состояние чата: режим и история сообщений."""

    mode: str = "assistant"
    messages: list[Message] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Сериализация в словарь."""
        return {
            "mode": self.mode,
            "messages": [asdict(m) for m in self.messages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChatState":
        """Десериализация из словаря."""
        messages = [
            Message(role=m["role"], content=m["content"])
            for m in data.get("messages", [])
        ]
        return cls(mode=data.get("mode", "assistant"), messages=messages)


class Memory:
    """
    Хранилище памяти диалогов.
    Сохраняет данные в JSON-файл.
    """

    def __init__(self, path: Path | None = None):
        self._path = path or MEMORY_PATH
        self._data: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        """Загрузка данных из файла."""
        if self._path.exists():
            try:
                with open(self._path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                self._data = {
                    k: ChatState.from_dict(v).to_dict()
                    for k, v in raw.items()
                }
            except (json.JSONDecodeError, KeyError):
                self._data = {}
        else:
            self._data = {}

    def _save(self) -> None:
        """Сохранение данных в файл."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)

    def _get_chat_key(self, user_id: int, chat_id: int) -> str:
        """Ключ для хранения данных чата."""
        return f"{user_id}:{chat_id}"

    def get_state(self, user_id: int, chat_id: int) -> ChatState:
        """Получить состояние чата."""
        key = self._get_chat_key(user_id, chat_id)
        if key not in self._data:
            return ChatState()
        return ChatState.from_dict(self._data[key])

    def set_state(self, user_id: int, chat_id: int, state: ChatState) -> None:
        """Установить состояние чата."""
        key = self._get_chat_key(user_id, chat_id)
        self._data[key] = state.to_dict()
        self._save()

    def add_message(
        self, user_id: int, chat_id: int, role: str, content: str
    ) -> None:
        """Добавить сообщение в историю."""
        state = self.get_state(user_id, chat_id)
        state.messages.append(Message(role=role, content=content))

        # Ограничить размер истории
        if len(state.messages) > MAX_HISTORY_MESSAGES:
            state.messages = state.messages[-MAX_HISTORY_MESSAGES:]

        self.set_state(user_id, chat_id, state)

    def set_mode(self, user_id: int, chat_id: int, mode: str) -> None:
        """Установить режим для чата."""
        state = self.get_state(user_id, chat_id)
        state.mode = mode
        self.set_state(user_id, chat_id, state)

    def clear(self, user_id: int, chat_id: int) -> None:
        """Очистить историю диалога."""
        state = self.get_state(user_id, chat_id)
        state.messages.clear()
        self.set_state(user_id, chat_id, state)

    def get_messages_for_openai(
        self, user_id: int, chat_id: int
    ) -> list[dict[str, str]]:
        """Получить историю в формате OpenAI API."""
        state = self.get_state(user_id, chat_id)
        return [m.to_openai_format() for m in state.messages]
