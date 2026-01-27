"""
Assistant configuration - YAML loader and dataclasses
"""
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
import yaml


@dataclass
class ChatConfig:
    """Configuration for a single monitored chat"""
    display_name: str
    goal: str  # What user wants from this chat
    priority: str = "medium"  # high | medium | low
    identifier: Optional[str] = None  # @username or chat title
    chat_id: Optional[int] = None  # numeric ID
    max_messages: int = 30


@dataclass
class UserContext:
    """User's personal context"""
    name: str
    language: str = "ru"


@dataclass
class AssistantConfig:
    """Main assistant configuration"""
    user: UserContext
    chats: List[ChatConfig]
    data_dir: str = "./data"

    @classmethod
    def load(cls, path: str = "assistant_config.yaml") -> "AssistantConfig":
        """Load configuration from YAML file"""
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f)

        user = UserContext(
            name=data["user"]["name"],
            language=data["user"].get("language", "ru")
        )

        chats = []
        for c in data.get("chats", []):
            chat = ChatConfig(
                display_name=c["display_name"],
                goal=c.get("goal", ""),
                priority=c.get("priority", "medium"),
                identifier=c.get("identifier"),
                chat_id=c.get("chat_id"),
                max_messages=c.get("max_messages", 30)
            )
            chats.append(chat)

        return cls(
            user=user,
            chats=chats,
            data_dir=data.get("data_dir", "./data")
        )

    def get_chat(self, name: str) -> Optional[ChatConfig]:
        """Find chat config by display_name (case-insensitive)"""
        name_lower = name.lower()
        for c in self.chats:
            if c.display_name.lower() == name_lower:
                return c
        return None

    def get_chat_names(self) -> List[str]:
        """Get list of all chat display names"""
        return [c.display_name for c in self.chats]
