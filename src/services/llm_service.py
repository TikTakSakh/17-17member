"""LLM service for GPT-4o-mini integration (bar 17/17)."""
from __future__ import annotations

import logging

from beartype import beartype
from openai import AsyncOpenAI

logger = logging.getLogger(__name__)

SYSTEM_PROMPT_TEMPLATE = """Ты — приветливый AI-помощник бара «17/17». 
Представляй себя как молодого парня-бармена, который отлично разбирается в меню, напитках и услугах бара.

Стиль общения:
- Говори дружелюбно, но поддерживай формальное общение (на «вы»)
- Будь позитивным, энергичным и вежливым — как молодой общительный бармен
- Используй эмодзи умеренно, для создания приятной атмосферы 🍸
- Отвечай лаконично и по делу, но с теплотой

Правила:
- Отвечай только на вопросы, связанные с баром, его меню, услугами и мероприятиями
- Если вопрос не касается бара, вежливо перенаправь разговор на тему бара
- Если не знаешь ответа, предложи связаться с баром напрямую
- При вопросах о ценах и меню опирайся строго на базу знаний ниже

Информация о баре:
{knowledge_base}
"""


@beartype
class LLMService:
    """Service for generating responses using GPT-4o-mini (bar 17/17)."""

    def __init__(self, api_key: str, base_url: str | None = None, knowledge_base: str = "") -> None:
        """Initialize the LLM service.
        
        Args:
            api_key: OpenAI API key.
            base_url: Optional base URL for API (e.g. for OpenRouter).
            knowledge_base: Knowledge base content to include in system prompt.
        """
        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._knowledge_base = knowledge_base
        self._model = "gpt-4o-mini"
        self._custom_system_prompt: str | None = None

    def update_knowledge_base(self, knowledge_base: str) -> None:
        """Update the knowledge base content.
        
        Args:
            knowledge_base: New knowledge base content.
        """
        self._knowledge_base = knowledge_base
        logger.info("Knowledge base updated, length: %d chars", len(knowledge_base))

    def set_custom_system_prompt(self, prompt: str) -> None:
        """Set a custom system prompt (admin override)."""
        self._custom_system_prompt = prompt
        logger.info("Custom system prompt set, length: %d chars", len(prompt))

    def reset_system_prompt(self) -> None:
        """Reset to default system prompt."""
        self._custom_system_prompt = None
        logger.info("System prompt reset to default")

    def get_current_system_prompt_preview(self) -> str:
        """Return first 200 chars of the current system prompt for admin preview."""
        prompt = self._get_system_prompt()
        return prompt[:200] + ("..." if len(prompt) > 200 else "")

    def _get_system_prompt(self) -> str:
        """Get the system prompt with current knowledge base."""
        kb = self._knowledge_base or "Информация о баре пока не загружена."
        if self._custom_system_prompt:
            return self._custom_system_prompt + f"\n\nИнформация о баре:\n{kb}"
        return SYSTEM_PROMPT_TEMPLATE.format(knowledge_base=kb)

    async def generate_response(
        self,
        user_message: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        """Generate a response to the user's message.
        
        Args:
            user_message: The user's message text.
            history: Optional conversation history in OpenAI format.
            
        Returns:
            Generated response text.
        """
        messages: list[dict[str, str]] = [
            {"role": "system", "content": self._get_system_prompt()}
        ]
        
        if history:
            messages.extend(history)
        
        messages.append({"role": "user", "content": user_message})
        
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=0.7,
                max_tokens=1000,
            )
            
            content = response.choices[0].message.content
            if content is None:
                return "Извините, не удалось сгенерировать ответ. Попробуйте ещё раз."
            return content
            
        except Exception as e:
            logger.error("Error generating LLM response: %s", e)
            return "Извините, произошла ошибка при обработке вашего запроса. Пожалуйста, попробуйте позже."
