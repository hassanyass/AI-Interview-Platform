from abc import ABC, abstractmethod
from typing import TypeVar, Type, Any, Dict, List
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class LLMProvider(ABC):
    @abstractmethod
    async def generate_structured(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]],
        response_model: Type[T]
    ) -> T:
        """
        Generate a structured response constrained by the provided Pydantic model.
        """
        pass

    @abstractmethod
    async def generate_text(
        self,
        system_prompt: str,
        messages: List[Dict[str, str]]
    ) -> str:
        """
        Generate a plain text response.
        """
        pass
