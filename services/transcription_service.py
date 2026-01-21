"""
Transcription Service - OpenAI Whisper API integration
Handles voice message transcription with optional GPT post-processing
"""
import logging
import asyncio
from openai import OpenAI, APIError, APIConnectionError, RateLimitError, APITimeoutError

from config import config

logger = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """Custom exception for transcription errors"""
    pass


# Initialize OpenAI client (lazy - only if key exists)
_client = None


def get_openai_client() -> OpenAI:
    """Get or create OpenAI client"""
    global _client
    if _client is None:
        api_key = config.get("openai_api_key")
        if not api_key:
            raise ValueError("OPENAI_API_KEY not configured. Add it to .env file.")
        _client = OpenAI(api_key=api_key, timeout=60.0)
    return _client


def is_transcription_available() -> bool:
    """Check if transcription service is available (API key configured)"""
    return bool(config.get("openai_api_key"))


def _transcribe_audio_sync(file_path: str, language: str) -> str:
    """Synchronous transcription - runs in thread pool"""
    client = get_openai_client()

    with open(file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            language=language
        )

    return transcript.text.strip()


async def transcribe_audio(file_path: str, language: str = None) -> str:
    """
    Transcribe audio file using OpenAI Whisper API

    Args:
        file_path: Path to audio file (.ogg, .mp3, .wav, .m4a)
        language: Language code (ru, en, etc.) - helps accuracy.
                  If None, uses config default.

    Returns:
        Transcribed text

    Raises:
        ValueError: If API key not configured
        TranscriptionError: On API errors
    """
    if language is None:
        language = config.get("transcription_language", "ru")

    logger.info(f"Transcribing audio file: {file_path}")

    try:
        # Run sync OpenAI call in thread pool to not block event loop
        text = await asyncio.to_thread(_transcribe_audio_sync, file_path, language)
        logger.info(f"Transcription complete: {len(text)} chars")
        return text

    except RateLimitError as e:
        logger.error(f"OpenAI rate limit exceeded: {e}")
        raise TranscriptionError("Превышен лимит запросов к API. Попробуйте позже.") from e

    except APITimeoutError as e:
        logger.error(f"OpenAI API timeout: {e}")
        raise TranscriptionError("Таймаут при обращении к API. Попробуйте позже.") from e

    except APIConnectionError as e:
        logger.error(f"OpenAI connection error: {e}")
        raise TranscriptionError("Ошибка соединения с API. Проверьте интернет.") from e

    except APIError as e:
        logger.error(f"OpenAI API error: {e}")
        raise TranscriptionError(f"Ошибка API: {e.message}") from e


def _improve_transcription_sync(raw_text: str) -> str:
    """Synchronous GPT call - runs in thread pool"""
    client = get_openai_client()

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{
            "role": "system",
            "content": """You are a text editor. Clean up voice transcription:
- Remove filler words (um, uh, like, you know, э-э, ну, типа)
- Fix punctuation and capitalization
- Remove false starts and repetitions
- Split into paragraphs (blank line) only when topic clearly changes
- Keep the EXACT meaning - do not add or remove ANY information
- Keep the same language as input
- NEVER add phrases like "продолжение следует", "to be continued", or any commentary
- NEVER add anything that wasn't in the original speech
- Output ONLY the cleaned transcription text, nothing else"""
        }, {
            "role": "user",
            "content": raw_text
        }],
        temperature=0.3,
        max_tokens=len(raw_text) * 2
    )

    return response.choices[0].message.content.strip()


async def improve_transcription(raw_text: str) -> str:
    """
    Improve transcription using GPT-4o-mini
    - Removes filler words (um, uh, etc.)
    - Fixes punctuation
    - Preserves original meaning

    Args:
        raw_text: Raw transcription from Whisper

    Returns:
        Cleaned up text, or original text on error
    """
    if not raw_text or len(raw_text) < 10:
        return raw_text

    try:
        # Run sync OpenAI call in thread pool to not block event loop
        improved = await asyncio.to_thread(_improve_transcription_sync, raw_text)
        logger.info(f"Text improved: {len(raw_text)} -> {len(improved)} chars")
        return improved

    except RateLimitError as e:
        logger.warning(f"Rate limit during improvement, returning raw text: {e}")
        return raw_text

    except (APITimeoutError, APIConnectionError) as e:
        logger.warning(f"Connection issue during improvement, returning raw text: {e}")
        return raw_text

    except APIError as e:
        logger.warning(f"API error during improvement, returning raw text: {e}")
        return raw_text
