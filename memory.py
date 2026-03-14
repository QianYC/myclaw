"""Memory interface for conversation history management."""

from abc import ABC, abstractmethod
from collections import deque
from openai.types.chat import ChatCompletionMessageParam

class Memory(ABC):
    """Abstract base class defining the memory interface."""

    @abstractmethod
    def add(self, message: ChatCompletionMessageParam) -> None:
        """Append a message to memory."""
        ...

    @abstractmethod
    def get_messages(self) -> list[ChatCompletionMessageParam]:
        """Return all messages as a list of ChatCompletionMessageParam."""
        ...

    @abstractmethod
    def clear(self) -> None:
        """Clear all stored messages."""
        ...


class SlidingWindowMemory(Memory):
    """Fixed-size sliding window memory.

    Keeps the most recent *max_size* messages, discarding the oldest
    when the window is full.
    """

    def __init__(self, max_size: int = 20) -> None:
        self._max_size = max_size
        self._messages: deque[ChatCompletionMessageParam] = deque(maxlen=max_size)

    def add(self, message: ChatCompletionMessageParam) -> None:
        self._messages.append(message)

    def get_messages(self) -> list[ChatCompletionMessageParam]:
        return list(self._messages)

    def clear(self) -> None:
        self._messages.clear()
