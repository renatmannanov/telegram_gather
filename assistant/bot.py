"""
Assistant Bot - handles Telegram bot commands via Bot API
"""
import asyncio
import logging
from typing import Optional

import aiohttp

from .collector import MessageCollector
from .summarizer import Summarizer
from .storage import SummaryStorage

logger = logging.getLogger(__name__)


class AssistantBot:
    """Telegram Bot for assistant commands"""

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        collector: MessageCollector,
        summarizer: Summarizer,
        storage: SummaryStorage,
        fragment_collector=None
    ):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.collector = collector
        self.summarizer = summarizer
        self.storage = storage
        self.fragment_collector = fragment_collector
        self._last_update_id = 0
        self._running = False
        self._bulk_task = None

    async def start(self):
        """Start polling for commands"""
        self._running = True

        # Register bot commands in Telegram menu
        await self._register_commands()

        logger.info("Assistant bot started, waiting for commands...")

        while self._running:
            try:
                await self._poll_updates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(5)

    async def stop(self):
        """Stop the bot"""
        self._running = False

    async def _poll_updates(self):
        """Poll Telegram Bot API for updates"""
        url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 30,
            "allowed_updates": ["message"]
        }

        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=35)) as resp:
                if resp.status != 200:
                    logger.error(f"Failed to get updates: {resp.status}")
                    await asyncio.sleep(5)
                    return

                data = await resp.json()

        for update in data.get("result", []):
            self._last_update_id = update["update_id"]
            await self._handle_update(update)

    async def _handle_update(self, update: dict):
        """Handle incoming update"""
        message = update.get("message", {})
        text = message.get("text", "")
        from_chat_id = str(message.get("chat", {}).get("id"))

        # Only respond to configured user
        if from_chat_id != self.chat_id:
            return

        # Route commands
        if text.startswith("/summary"):
            await self._cmd_summary()
        elif text.startswith("/chat "):
            await self._cmd_chat(text)
        elif text.startswith("/chats"):
            await self._cmd_list_chats()
        elif text.startswith("/collect_status"):
            await self._cmd_collect_status(text)
        elif text.startswith("/collect_stop"):
            await self._cmd_collect_stop()
        elif text.startswith("/collect"):
            await self._cmd_collect(text)
        elif text.startswith("/help"):
            await self._cmd_help()
        elif text.startswith("/reset"):
            await self._cmd_reset(text)

    async def _cmd_summary(self):
        """Handle /summary command - summary of all unread messages"""
        if not self.collector:
            await self._send("❌ Summary не настроен (нет assistant_config.yaml)")
            return
        # Send initial status message (will be edited)
        status_msg_id = await self._send("⏳ Собираю сообщения...", return_message_id=True)

        try:
            messages = await self.collector.collect_all_unread()

            if not messages:
                await self._edit(status_msg_id, "✅ Нет новых сообщений")
                return

            total_msgs = sum(len(msgs) for _, msgs in messages.values())
            await self._edit(status_msg_id, f"🤖 Генерирую summary ({total_msgs} сообщ.)...")

            summary = await self.summarizer.generate_full(messages)

            # Edit with final summary
            await self._edit(status_msg_id, summary.aggregate, parse_mode="HTML")

            # Save to file
            filepath = await self.storage.save(summary)
            logger.info(f"Summary saved to {filepath}")

        except Exception as e:
            logger.error(f"Error in /summary: {e}", exc_info=True)
            await self._edit(status_msg_id, f"❌ Ошибка: {e}")

    async def _cmd_chat(self, text: str):
        """Handle /chat [name] [period] command"""
        if not self.collector:
            await self._send("❌ Summary не настроен (нет assistant_config.yaml)")
            return
        parts = text.split()

        if len(parts) < 2:
            await self._send(
                "Использование: /chat [название] [период]\n"
                "Пример: /chat Work 2d\n\n"
                "Периоды: 12h, 1d, 2d, 1w"
            )
            return

        name = parts[1]
        period = parts[2] if len(parts) > 2 else "1d"

        # Find chat config
        chat_config = self.collector.config.get_chat(name)
        if not chat_config:
            names = self.collector.config.get_chat_names()
            await self._send(
                f"❌ Чат '{name}' не найден.\n\n"
                f"Доступные чаты:\n" + "\n".join(f"  • {n}" for n in names)
            )
            return

        status_msg_id = await self._send(
            f"⏳ Собираю сообщения из {chat_config.display_name} за {period}...",
            return_message_id=True
        )

        try:
            messages = await self.collector.get_for_period(chat_config, period)

            if not messages:
                await self._edit(status_msg_id, f"✅ Нет сообщений в {chat_config.display_name} за {period}")
                return

            await self._edit(status_msg_id, f"🤖 Генерирую summary ({len(messages)} сообщ.)...")
            summary = await self.summarizer.summarize_chat(chat_config, messages)

            # Edit with final summary
            response = (
                f"<b>{summary.chat_name}</b> ({summary.message_count} сообщ.)\n\n"
                f"{summary.summary}"
            )
            await self._edit(status_msg_id, response, parse_mode="HTML")

        except Exception as e:
            logger.error(f"Error in /chat: {e}", exc_info=True)
            await self._edit(status_msg_id, f"❌ Ошибка: {e}")

    async def _cmd_list_chats(self):
        """Handle /chats command - list monitored chats"""
        if not self.collector:
            await self._send("❌ Summary не настроен (нет assistant_config.yaml)")
            return
        chats = self.collector.config.chats
        if not chats:
            await self._send("Нет настроенных чатов. Отредактируйте assistant_config.yaml")
            return

        lines = ["<b>Отслеживаемые чаты:</b>\n"]
        icons = {"high": "🔴", "medium": "🟡", "low": "🟢"}

        for c in chats:
            icon = icons.get(c.priority, "⚪")
            identifier = c.identifier or f"ID: {c.chat_id}"
            lines.append(f"{icon} <b>{c.display_name}</b> ({identifier})")

        await self._send("\n".join(lines), parse_mode="HTML")

    async def _cmd_help(self):
        """Handle /help command"""
        await self._send(
            "<b>Personal Assistant Commands</b>\n\n"
            "/summary - сводка непрочитанных сообщений\n"
            "/chat [имя] [период] - сводка конкретного чата\n"
            "/chats - список отслеживаемых чатов\n"
            "/collect [источник] - bulk сбор фрагментов\n"
            "/collect_status - статус сбора\n"
            "/collect_stop - остановить сбор\n"
            "/reset [имя] - сбросить состояние\n"
            "/help - эта справка\n\n"
            "<i>Примеры периодов: 12h, 1d, 2d, 1w</i>",
            parse_mode="HTML"
        )

    async def _cmd_reset(self, text: str):
        """Handle /reset command - reset state"""
        if not self.collector:
            await self._send("❌ Summary не настроен (нет assistant_config.yaml)")
            return
        # Extract chat name (everything after "/reset ")
        chat_name = text[7:].strip() if len(text) > 7 else None
        chat_name = chat_name if chat_name else None  # Empty string -> None

        self.collector.reset_state(chat_name)

        if chat_name:
            await self._send(f"✅ Состояние сброшено для: {chat_name}")
        else:
            await self._send("✅ Состояние сброшено для всех чатов")

    async def _cmd_collect(self, text: str):
        """Handle /collect [source] command - bulk collect fragments"""
        if not self.fragment_collector:
            await self._send("❌ Fragment collection не настроен (нет DATABASE_URL)")
            return

        if self._bulk_task and not self._bulk_task.done():
            await self._send("⚠️ Bulk collection уже запущен. /collect_stop чтобы остановить")
            return

        # Parse source argument
        arg = text[len("/collect"):].strip()

        try:
            if arg:
                entity, source_key = await self.fragment_collector.resolve_source(arg)
            else:
                await self._send(
                    "Использование: /collect [источник]\n"
                    "Примеры:\n"
                    "  /collect iwacado\n"
                    "  /collect -1002163129581\n"
                    "  /collect me"
                )
                return
        except ValueError as e:
            await self._send(f"❌ {e}")
            return

        status_msg_id = await self._send(
            f"⏳ Начинаю сбор из {arg} (source_key={source_key})...",
            return_message_id=True
        )

        async def progress(count, inserted):
            await self._edit(status_msg_id, f"⏳ {arg}: собрано {count}, вставлено {inserted}...")

        async def run_bulk():
            try:
                stats = await self.fragment_collector.bulk_collect(
                    entity, source_key=source_key, progress_callback=progress
                )
                await self._edit(
                    status_msg_id,
                    f"✅ {arg}: готово! Обработано {stats['count']}, вставлено {stats['inserted']}"
                )
            except Exception as e:
                logger.error(f"Bulk collect error: {e}", exc_info=True)
                await self._edit(status_msg_id, f"❌ Ошибка: {e}")

        self._bulk_task = asyncio.create_task(run_bulk())

    async def _cmd_collect_status(self, text: str):
        """Handle /collect_status command - show gather_state"""
        if not self.fragment_collector:
            await self._send("❌ Fragment collection не настроен")
            return

        rows = await self.fragment_collector.db.get_all_status()

        if not rows:
            await self._send("Нет данных о сборе. Ещё ничего не собиралось.")
            return

        lines = ["<b>📊 Статус сбора:</b>\n"]
        for r in rows:
            dt = r['last_collected_at']
            dt_str = dt.strftime("%d.%m %H:%M") if dt else "—"
            lines.append(f"<b>{r['source']}</b> — last_id: {r['last_msg_id']}, {dt_str}")

        await self._send("\n".join(lines), parse_mode="HTML")

    async def _cmd_collect_stop(self):
        """Handle /collect_stop command"""
        if not self.fragment_collector:
            await self._send("❌ Fragment collection не настроен")
            return

        if not self._bulk_task or self._bulk_task.done():
            await self._send("Нет активного bulk collection")
            return

        self.fragment_collector._bulk_stop = True
        await self._send("⏹ Останавливаю bulk collection...")

    async def _send(
        self,
        text: str,
        parse_mode: Optional[str] = None,
        return_message_id: bool = False,
        disable_preview: bool = True
    ) -> Optional[int]:
        """Send message via Telegram Bot API"""
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text[:4096],
            "disable_web_page_preview": disable_preview
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"Failed to send message: {resp.status} - {error}")
                        return None
                    if return_message_id:
                        data = await resp.json()
                        return data.get("result", {}).get("message_id")
        except Exception as e:
            logger.error(f"Error sending message: {e}")
        return None

    async def _edit(
        self,
        message_id: Optional[int],
        text: str,
        parse_mode: Optional[str] = None,
        disable_preview: bool = True
    ):
        """Edit message via Telegram Bot API"""
        if not message_id:
            # Fallback to sending new message if no message_id
            await self._send(text, parse_mode, disable_preview=disable_preview)
            return

        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload = {
            "chat_id": self.chat_id,
            "message_id": message_id,
            "text": text[:4096],
            "disable_web_page_preview": disable_preview
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"Failed to edit message: {resp.status} - {error}")
        except Exception as e:
            logger.error(f"Error editing message: {e}")

    async def _register_commands(self):
        """Register bot commands in Telegram menu"""
        url = f"https://api.telegram.org/bot{self.bot_token}/setMyCommands"
        commands = [
            {"command": "summary", "description": "Сводка непрочитанных сообщений"},
            {"command": "chat", "description": "Сводка конкретного чата"},
            {"command": "chats", "description": "Список отслеживаемых чатов"},
            {"command": "collect", "description": "Bulk сбор фрагментов"},
            {"command": "collect_status", "description": "Статус сбора фрагментов"},
            {"command": "collect_stop", "description": "Остановить сбор"},
            {"command": "reset", "description": "Сбросить состояние"},
            {"command": "help", "description": "Справка по командам"},
        ]

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    url,
                    json={"commands": commands},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        logger.info("Bot commands registered successfully")
                    else:
                        error = await resp.text()
                        logger.warning(f"Failed to register commands: {error}")
        except Exception as e:
            logger.warning(f"Error registering commands: {e}")
