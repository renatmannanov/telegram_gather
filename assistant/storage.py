"""
Summary Storage - saves summaries to markdown files
"""
import logging
from pathlib import Path
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .summarizer import FullSummary

logger = logging.getLogger(__name__)


class SummaryStorage:
    """Stores summary history as markdown files"""

    def __init__(self, data_dir: str = "./data"):
        self.dir = Path(data_dir) / "summaries"
        self.dir.mkdir(parents=True, exist_ok=True)

    async def save(self, summary: "FullSummary") -> Path:
        """Save summary to markdown file"""
        date_str = summary.generated_at.strftime("%Y-%m-%d")
        time_str = summary.generated_at.strftime("%H-%M")

        filename = f"{date_str}_{time_str}.md"
        filepath = self.dir / filename

        content = self._to_markdown(summary)
        filepath.write_text(content, encoding="utf-8")

        logger.info(f"Summary saved to {filepath}")
        return filepath

    def _to_markdown(self, summary: "FullSummary") -> str:
        """Convert summary to markdown format"""
        lines = [
            f"# Summary {summary.generated_at.strftime('%Y-%m-%d %H:%M')}",
            "",
            "## Overview",
            "",
            self._html_to_md(summary.aggregate),
            "",
            "---",
            "",
            "## Per-Chat Details",
            ""
        ]

        for s in summary.chats:
            lines.extend([
                f"### {s.chat_name}",
                f"- **Priority:** {s.priority}",
                f"- **Messages:** {s.message_count}",
                "",
                s.summary,
                ""
            ])

            if s.actions:
                lines.append("**Actions:**")
                for action in s.actions:
                    lines.append(f"- {action}")
                lines.append("")

        return "\n".join(lines)

    def _html_to_md(self, text: str) -> str:
        """Convert HTML formatting to markdown"""
        return (
            text
            .replace("<b>", "**")
            .replace("</b>", "**")
            .replace("<i>", "_")
            .replace("</i>", "_")
            .replace("&lt;", "<")
            .replace("&gt;", ">")
        )

    def cleanup(self, keep_days: int = 30):
        """Remove summaries older than keep_days"""
        cutoff = datetime.now().timestamp() - (keep_days * 86400)
        removed = 0

        for filepath in self.dir.glob("*.md"):
            if filepath.stat().st_mtime < cutoff:
                filepath.unlink()
                removed += 1

        if removed:
            logger.info(f"Cleaned up {removed} old summary files")

    def get_recent(self, limit: int = 10) -> list:
        """Get paths to recent summary files"""
        files = sorted(self.dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)
        return files[:limit]
