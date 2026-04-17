"""
analyze_community.py - Community activity analytics across WNDR forum topics.

Usage:
    python analyze_community.py --input data/exports/wndr --output data/exports/wndr/analytics.md
    python analyze_community.py --input data/exports/wndr --json
"""

import argparse
import json
import sys
import io
from collections import defaultdict
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Пост считается содержательным если >= SUBSTANTIAL_CHARS символов
SUBSTANTIAL_CHARS = 150

# Топики где root-пост = реальный контент (оффер, запрос, коммит и т.д.)
CONTENT_TOPICS = {"intro", "offerings", "requests", "sales", "commits", "harvest", "daily", "together"}
CHAT_TOPICS = {"boltalka", "announcements"}

TOPIC_LABELS = {
    "intro":         "Кто мы? #intro",
    "offerings":     "Community offerings",
    "requests":      "Запросы",
    "sales":         "Продажная",
    "commits":       "Коммиты",
    "harvest":       "Харвест",
    "daily":         "Daily следы",
    "boltalka":      "Болталка",
    "announcements": "Анонсы",
    "together":      "Наши 3 месяца вместе",
}


def load_topic(filepath: Path) -> dict:
    data = json.loads(filepath.read_text(encoding="utf-8"))
    messages = []
    for thread in data.get("threads", []):
        root = thread.get("root")
        if root:
            root["_is_root"] = True
            messages.append(root)
        for reply in thread.get("replies", []):
            reply["_is_root"] = False
            messages.append(reply)
    data["_messages_flat"] = messages
    return data


def parse_date(s: str) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:
        return None


def month_key(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


def week_key(dt: datetime) -> str:
    return dt.strftime("%Y-W%V")


def analyze(topics: dict[str, dict]) -> dict:
    # user_id -> aggregated stats
    users: dict[int, dict] = {}

    # topic_name -> per-topic stats
    topic_stats: dict[str, dict] = {}

    # topic_name -> user_id -> substantial post count (для топов по топикам)
    topic_substantial: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))

    # Все посты с реакциями для топ-реакций
    all_posts_with_reactions = []

    for topic_name, data in topics.items():
        msgs = data["_messages_flat"]
        is_content = topic_name in CONTENT_TOPICS
        is_chat = topic_name in CHAT_TOPICS

        topic_users = set()
        topic_msg_count = 0
        topic_substantial_count = 0

        for msg in msgs:
            uid = msg.get("user_id")
            if not uid:
                continue

            dt = parse_date(msg.get("date"))
            char_count = msg.get("char_count") or len(msg.get("text", ""))
            is_substantial = char_count >= SUBSTANTIAL_CHARS
            reactions = msg.get("reactions", [])
            total_reactions = sum(r["count"] for r in reactions)

            topic_users.add(uid)
            topic_msg_count += 1
            if is_substantial:
                topic_substantial_count += 1

            if uid not in users:
                users[uid] = {
                    "name": msg.get("sender_name", "Unknown"),
                    "username": msg.get("username"),
                    "topics": set(),
                    "msg_count": 0,
                    "content_count": 0,
                    "chat_count": 0,
                    "substantial_count": 0,
                    "total_reactions_received": 0,
                    "dates": [],
                    "msgs_by_month": defaultdict(int),
                }

            u = users[uid]
            u["topics"].add(topic_name)
            u["msg_count"] += 1
            u["total_reactions_received"] += total_reactions
            if dt:
                u["dates"].append(dt)
                u["msgs_by_month"][month_key(dt)] += 1
            if is_content:
                u["content_count"] += 1
            if is_chat:
                u["chat_count"] += 1
            if is_substantial:
                u["substantial_count"] += 1
                if is_content:
                    topic_substantial[topic_name][uid] += 1

            # Собираем посты с реакциями для топа
            if total_reactions > 0:
                all_posts_with_reactions.append({
                    "topic": topic_name,
                    "topic_label": TOPIC_LABELS.get(topic_name, topic_name),
                    "user_id": uid,
                    "sender_name": msg.get("sender_name", "Unknown"),
                    "username": msg.get("username"),
                    "text_preview": msg.get("text", "")[:120],
                    "char_count": char_count,
                    "total_reactions": total_reactions,
                    "reactions": reactions,
                    "date": msg.get("date", "")[:10],
                })

        topic_stats[topic_name] = {
            "label": TOPIC_LABELS.get(topic_name, topic_name),
            "total_messages": topic_msg_count,
            "substantial_messages": topic_substantial_count,
            "unique_writers": len(topic_users),
            "is_content": is_content,
        }

    # Финальные вычисления по юзерам
    for uid, u in users.items():
        u["topic_count"] = len(u["topics"])
        total = u["msg_count"]
        chat_ratio = u["chat_count"] / total if total else 0
        content_ratio = u["content_count"] / total if total else 0

        if u["content_count"] == 0:
            u["tier"] = "only_chat"
        elif chat_ratio >= 0.8:
            u["tier"] = "mostly_chat"
        elif content_ratio >= 0.7:
            u["tier"] = "content_focused"
        else:
            u["tier"] = "balanced"

    # Топы
    top_overall = sorted(users.values(), key=lambda u: u["msg_count"], reverse=True)[:20]
    top_substantial = sorted(users.values(), key=lambda u: u["substantial_count"], reverse=True)[:20]
    only_chatters = sorted(
        [u for u in users.values() if u["tier"] == "only_chat"],
        key=lambda u: u["msg_count"], reverse=True
    )

    # Топ по каждому контент-топику (по substantial постам)
    tops_by_topic: dict[str, list] = {}
    for topic_name, user_counts in topic_substantial.items():
        ranked = sorted(user_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        tops_by_topic[topic_name] = [
            {
                "user_id": uid,
                "name": users[uid]["name"] if uid in users else "Unknown",
                "username": users[uid].get("username") if uid in users else None,
                "substantial_posts": count,
                "total_msgs": users[uid]["msg_count"] if uid in users else 0,
            }
            for uid, count in ranked
        ]

    # Топ постов по реакциям
    top_reactions = sorted(all_posts_with_reactions, key=lambda p: p["total_reactions"], reverse=True)[:20]

    # Временная динамика
    all_dates = []
    for u in users.values():
        all_dates.extend(u["dates"])
    all_dates.sort()

    msgs_per_week: dict[str, int] = defaultdict(int)
    msgs_per_month: dict[str, int] = defaultdict(int)
    for dt in all_dates:
        msgs_per_week[week_key(dt)] += 1
        msgs_per_month[month_key(dt)] += 1

    # Матрица топ-10 участников × месяцы
    top10_ids = [list(users.keys())[list(users.values()).index(u)] for u in top_overall[:10]]
    all_months = sorted(msgs_per_month.keys())
    activity_matrix = []
    for uid in top10_ids:
        u = users[uid]
        row = {"name": u["name"], "username": u.get("username"), "total": u["msg_count"]}
        for m in all_months:
            row[m] = u["msgs_by_month"].get(m, 0)
        activity_matrix.append(row)

    first_msg = all_dates[0] if all_dates else None
    last_msg = all_dates[-1] if all_dates else None

    return {
        "total_unique_writers": len(users),
        "total_messages": sum(u["msg_count"] for u in users.values()),
        "active_period_days": (last_msg - first_msg).days if first_msg and last_msg else 0,
        "first_message": first_msg.isoformat() if first_msg else None,
        "last_message": last_msg.isoformat() if last_msg else None,
        "tier_counts": {
            tier: sum(1 for u in users.values() if u["tier"] == tier)
            for tier in ["only_chat", "mostly_chat", "balanced", "content_focused"]
        },
        "topic_stats": topic_stats,
        "top_overall": top_overall,
        "top_substantial": top_substantial,
        "only_chatters": only_chatters,
        "tops_by_topic": tops_by_topic,
        "top_reactions": top_reactions,
        "msgs_per_month": dict(sorted(msgs_per_month.items())),
        "msgs_per_week": dict(sorted(msgs_per_week.items())),
        "activity_matrix": activity_matrix,
        "all_months": all_months,
        "_users": users,
    }


def fmt_user(u: dict) -> str:
    uname = f"@{u['username']}" if u.get("username") else "—"
    return f"{u['name']} ({uname})"


def render_markdown(result: dict) -> str:
    lines = []
    a = lines.append

    a("# WNDR Community Analytics\n")
    a(f"_Дата анализа: {datetime.now().strftime('%Y-%m-%d')}_\n")

    # Общая картина
    a("## Общая картина\n")
    a("| Метрика | Значение |")
    a("|---------|----------|")
    a(f"| Уникальных авторов | **{result['total_unique_writers']}** |")
    a(f"| Всего сообщений | **{result['total_messages']}** |")
    a(f"| Период | {result['first_message'][:10] if result['first_message'] else '?'} → {result['last_message'][:10] if result['last_message'] else '?'} ({result['active_period_days']} дней) |")
    a(f"| Порог «содержательный пост» | >= {SUBSTANTIAL_CHARS} символов |")
    a("")

    # Активность по топикам
    a("## Активность по топикам\n")
    a("| Топик | Сообщений | Содержательных | Уникальных авторов | Тип |")
    a("|-------|-----------|----------------|-------------------|-----|")
    for name, ts in sorted(result["topic_stats"].items(), key=lambda x: x[1]["total_messages"], reverse=True):
        kind = "контент" if ts["is_content"] else "чат"
        subst = ts["substantial_messages"]
        pct = f"{subst*100//ts['total_messages']}%" if ts["total_messages"] else "—"
        a(f"| {ts['label']} | {ts['total_messages']} | {subst} ({pct}) | {ts['unique_writers']} | {kind} |")
    a("")

    # Типы участников
    a("## Типы участников\n")
    tc = result["tier_counts"]
    total_w = result["total_unique_writers"]
    a("| Тип | Кол-во | % |")
    a("|-----|--------|---|")
    a(f"| Только болтают (0 контент-постов) | {tc['only_chat']} | {tc['only_chat']*100//total_w if total_w else 0}% |")
    a(f"| В основном болтают (>80% в чате) | {tc['mostly_chat']} | {tc['mostly_chat']*100//total_w if total_w else 0}% |")
    a(f"| Балансируют | {tc['balanced']} | {tc['balanced']*100//total_w if total_w else 0}% |")
    a(f"| Контент-ориентированные (>70% контент) | {tc['content_focused']} | {tc['content_focused']*100//total_w if total_w else 0}% |")
    a("")

    # Топ-20 по содержательным постам
    a("## Топ-20 по содержательным постам (>= 150 символов)\n")
    a("| # | Участник | Содержат. | Всего | Топиков | Реакций получено |")
    a("|---|----------|-----------|-------|---------|-----------------|")
    for i, u in enumerate(result["top_substantial"], 1):
        a(f"| {i} | {fmt_user(u)} | {u['substantial_count']} | {u['msg_count']} | {u['topic_count']} | {u['total_reactions_received']} |")
    a("")

    # Топ-20 по общей активности
    a("## Топ-20 по общей активности\n")
    a("| # | Участник | Сообщений | Содержат. | Топиков | Тип |")
    a("|---|----------|-----------|-----------|---------|-----|")
    for i, u in enumerate(result["top_overall"], 1):
        a(f"| {i} | {fmt_user(u)} | {u['msg_count']} | {u['substantial_count']} | {u['topic_count']} | {u['tier']} |")
    a("")

    # Топы по контент-топикам
    a("## Топы по контент-топикам\n")
    a(f"_Считаются только содержательные посты (>= {SUBSTANTIAL_CHARS} символов)_\n")
    for topic_name, top in sorted(result["tops_by_topic"].items()):
        label = TOPIC_LABELS.get(topic_name, topic_name)
        a(f"### {label}\n")
        if not top:
            a("_Нет данных_\n")
            continue
        a("| # | Участник | Содержат. постов | Всего сообщений |")
        a("|---|----------|-----------------|----------------|")
        for i, u in enumerate(top, 1):
            uname = f"@{u['username']}" if u.get("username") else "—"
            a(f"| {i} | {u['name']} ({uname}) | {u['substantial_posts']} | {u['total_msgs']} |")
        a("")

    # Только болтают
    a("## Только болтают — ни разу не постили в контент-топиках\n")
    if result["only_chatters"]:
        a("| Участник | Сообщений |")
        a("|----------|-----------|")
        for u in result["only_chatters"][:30]:
            a(f"| {fmt_user(u)} | {u['msg_count']} |")
        if len(result["only_chatters"]) > 30:
            a(f"\n_...и ещё {len(result['only_chatters']) - 30} человек_")
    else:
        a("_Нет таких — все хоть раз постили в контент-топиках_")
    a("")

    # Топ постов по реакциям
    a("## Топ-20 постов по реакциям\n")
    if result["top_reactions"]:
        a("| # | Автор | Топик | Дата | Реакций | Эмодзи | Начало текста |")
        a("|---|-------|-------|------|---------|--------|---------------|")
        for i, p in enumerate(result["top_reactions"], 1):
            uname = f"@{p['username']}" if p.get("username") else p["sender_name"]
            emoji_str = " ".join(f"{r['emoji']}×{r['count']}" for r in p["reactions"])
            preview = p["text_preview"].replace("\n", " ")[:80]
            a(f"| {i} | {uname} | {p['topic_label']} | {p['date']} | {p['total_reactions']} | {emoji_str} | {preview} |")
    else:
        a("_Реакций в данных нет_")
    a("")

    # Матрица активности топ-10 по месяцам
    a("## Активность топ-10 участников по месяцам\n")
    months = result["all_months"]
    header = "| Участник | Всего | " + " | ".join(m[5:] for m in months) + " |"
    sep = "|----------|-------|" + "|".join("------" for _ in months) + "|"
    a(header)
    a(sep)
    for row in result["activity_matrix"]:
        name = row["name"][:20]
        cells = " | ".join(str(row.get(m, 0)) for m in months)
        a(f"| {name} | {row['total']} | {cells} |")
    a("")

    # Активность по месяцам (общая)
    a("## Общая активность по месяцам\n")
    a("| Месяц | Сообщений |")
    a("|-------|-----------|")
    for month, count in result["msgs_per_month"].items():
        bar = "█" * (count // 30)
        a(f"| {month} | {count} {bar} |")
    a("")

    # Активность по неделям
    a("## Активность по неделям\n")
    a("| Неделя | Сообщений |")
    a("|--------|-----------|")
    for week, count in result["msgs_per_week"].items():
        bar = "█" * (count // 10)
        a(f"| {week} | {count} {bar} |")
    a("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="WNDR community analytics")
    parser.add_argument("--input", "-i", default="data/exports/wndr", help="Directory with wndr_topic_*.json")
    parser.add_argument("--output", "-o", help="Save markdown report to file")
    parser.add_argument("--json", action="store_true", help="Dump raw JSON to stdout")
    args = parser.parse_args()

    input_dir = Path(args.input)
    topic_files = list(input_dir.glob("wndr_topic_*.json"))
    if not topic_files:
        print(f"ERROR: No wndr_topic_*.json files in {input_dir}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading {len(topic_files)} topic files...", file=sys.stderr)
    topics = {}
    for f in topic_files:
        name = f.stem.replace("wndr_topic_", "")
        data = load_topic(f)
        print(f"  {name}: {len(data['_messages_flat'])} messages", file=sys.stderr)
        topics[name] = data

    print("Analyzing...", file=sys.stderr)
    result = analyze(topics)

    if args.json:
        serializable = {k: v for k, v in result.items() if k != "_users"}
        print(json.dumps(serializable, ensure_ascii=False, indent=2, default=str))

    report = render_markdown(result)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"Report saved to {args.output}", file=sys.stderr)
    else:
        print(report)

    print(f"\n=== SUMMARY ===", file=sys.stderr)
    print(f"Unique writers:    {result['total_unique_writers']}", file=sys.stderr)
    print(f"Total messages:    {result['total_messages']}", file=sys.stderr)
    print(f"Only chatters:     {result['tier_counts']['only_chat']}", file=sys.stderr)
    print(f"Content active:    {result['tier_counts']['content_focused'] + result['tier_counts']['balanced']}", file=sys.stderr)
    top1 = result["top_reactions"][0] if result["top_reactions"] else None
    if top1:
        print(f"Most reacted post: {top1['total_reactions']} reactions by {top1['sender_name']} in {top1['topic_label']}", file=sys.stderr)


if __name__ == "__main__":
    main()
