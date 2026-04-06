# CLAUDE.md — telegram-gather

## Стек
Telethon (userbot), OpenAI Whisper + GPT-4o-mini, Python 3.10+

## Команды
python main.py                                    # запуск бота
python fetch_chat.py "Chat Name" --period 1w      # экспорт чата

## Структура
main.py           — точка входа
config.py         — конфигурация
handlers/         — voice_handler.py
services/         — transcription_service.py
fetch_chat.py     — экспорт переписок для анализа

## Критические правила
- Сессионные файлы Telethon (*.session) — НЕ трогать без явного запроса пользователя
- Это userbot — работает от имени личного аккаунта, не бота-токена
- assistant_config.yaml — конфигурация ассистента, не удалять

## Планирование
task_tracker/     — планы и задачи (todo/, done/, backlog/)
