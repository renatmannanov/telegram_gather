# Исследование возможностей работы с контактами через Telegram MTProto API (Telethon)

## Введение

Данный документ содержит полное исследование возможностей работы с контактами в Telegram при использовании библиотеки Telethon для Python. Telethon - это асинхронная библиотека для работы с MTProto API Telegram, позволяющая работать как через пользовательский аккаунт (userbot), так и через бот-аккаунт.

**Версия библиотеки:** Telethon 1.42.0 (актуальная на ноябрь 2025)

---

## 0. Контакты vs Диалоги: важное различие

Прежде чем работать с контактами, важно понимать разницу между **контактами** и **диалогами** в Telegram.

### Что такое контакты

**Контакты** — это пользователи, которых вы **явно добавили** в свой список контактов (по номеру телефона или username). Это аналог телефонной книги.

### Что такое диалоги

**Диалоги** — это все чаты, где была переписка: личные сообщения (DM), группы, каналы. Пользователь попадает в диалоги автоматически при первом сообщении.

### Сравнительная таблица

| Характеристика | Контакты | Диалоги (DM) |
|----------------|----------|--------------|
| **Как попадают** | Явное добавление вручную | Автоматически при первом сообщении |
| **Типичное количество** | Десятки-сотни | Сотни-тысячи |
| **Содержит** | Только пользователей | Пользователей, группы, каналы, ботов |
| **API метод** | `GetContactsRequest` / `get_contacts()` | `GetDialogsRequest` / `get_dialogs()` |

### Что работает только с контактами

- `GetContactsRequest` — получить список контактов
- `GetStatusesRequest` — статусы онлайн **только для контактов**
- `DeleteContactsRequest` — удаление из контактов
- `ImportContactsRequest` — добавление в контакты
- Взаимные контакты (`mutual_contact`)
- Близкие друзья (Close Friends)
- Дни рождения контактов
- Примечания к контактам (`UpdateContactNoteRequest`)

### Что работает с любым пользователем

- `GetFullUserRequest` — получить полную информацию
- `ResolveUsernameRequest` — найти по username
- `GetCommonChatsRequest` — общие чаты
- `BlockRequest` / `UnblockRequest` — блокировка
- Скачивание фото профиля
- **Top Peers** — частые собеседники (не обязательно контакты!)

### Получение всех диалогов (DM)

```python
async def get_all_dm_users(client):
    """
    Получить всех пользователей из личных переписок.
    Это НЕ контакты, а все с кем была переписка.
    """
    dm_users = []

    async for dialog in client.iter_dialogs():
        if dialog.is_user:  # Только личные чаты (не группы/каналы)
            user = dialog.entity
            dm_users.append({
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'is_contact': user.contact,  # Является ли контактом
                'last_message_date': dialog.date
            })

    return dm_users

# Пример использования
async def main():
    dialogs = await get_all_dm_users(client)

    contacts_in_dm = [d for d in dialogs if d['is_contact']]
    non_contacts_in_dm = [d for d in dialogs if not d['is_contact']]

    print(f"Диалогов с контактами: {len(contacts_in_dm)}")
    print(f"Диалогов с НЕ-контактами: {len(non_contacts_in_dm)}")
```

### Практический вывод

- Если нужны **только добавленные контакты** → используйте `get_contacts()`
- Если нужны **все люди, с кем общались** → используйте `get_dialogs()`
- Top Peers показывает частых собеседников из диалогов, независимо от того, добавлены ли они в контакты

---

## 1. Чтение контактов

### 1.1 Получение полного списка контактов

Для получения списка всех контактов используется метод `GetContactsRequest`:

```python
from telethon import TelegramClient
from telethon.tl.functions.contacts import GetContactsRequest

async def get_all_contacts(client):
    # Метод 1: Высокоуровневый API
    contacts = await client.get_contacts()

    # Метод 2: Низкоуровневый API (raw)
    result = await client(GetContactsRequest(hash=0))

    for user in result.users:
        print(f"{user.first_name} {user.last_name}: {user.phone}")

    return result
```

**Параметры:**
- `hash` - хеш для кэширования (используйте 0 для получения полного списка)

**Возвращает:**
- `contacts.Contacts` - объект, содержащий:
  - `contacts` - список объектов `Contact` (user_id, mutual)
  - `users` - список объектов `User` с полной информацией

### 1.2 Получение детальной информации о контакте

```python
from telethon.tl.functions.users import GetFullUserRequest

async def get_contact_details(client, user_id):
    full = await client(GetFullUserRequest(user_id))

    user = full.users[0]  # Базовая информация о пользователе
    full_user = full.full_user  # Расширенная информация

    return {
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'username': user.username,
        'phone': user.phone,
        'bio': full_user.about,
        'common_chats_count': full_user.common_chats_count,
        'is_blocked': full_user.blocked,
        'photo': user.photo
    }
```

### 1.3 Поиск контактов

```python
from telethon.tl.functions.contacts import SearchRequest

async def search_contacts(client, query, limit=100):
    result = await client(SearchRequest(
        q=query,
        limit=limit
    ))

    # result.my_results - контакты из вашего списка
    # result.results - глобальные результаты поиска
    # result.users - информация о пользователях
    # result.chats - информация о чатах

    return result
```

**Ограничение:** Глобальный поиск может возвращать только первые 3 результата для публичных каналов.

### 1.4 Получение взаимных контактов

**Взаимный контакт (Mutual Contact)** — это когда оба пользователя добавили друг друга в контакты:
- Вы добавили Васю + Вася добавил вас = **взаимный контакт** (`mutual = True`)
- Вы добавили Васю, но он вас нет = **односторонний контакт** (`mutual = False`)

При получении списка контактов каждый объект `Contact` содержит поле `mutual`:

```python
async def get_mutual_contacts(client):
    result = await client(GetContactsRequest(hash=0))

    mutual_contacts = []
    for contact in result.contacts:
        if contact.mutual:
            # Найти пользователя по user_id
            user = next((u for u in result.users if u.id == contact.user_id), None)
            if user:
                mutual_contacts.append(user)

    return mutual_contacts
```

Также можно проверить флаги у объекта `User`:
- `user.contact` - является ли пользователь вашим контактом
- `user.mutual_contact` - является ли контакт взаимным

---

## 2. Управление контактами

### 2.1 Добавление контактов

#### По номеру телефона (ImportContactsRequest)

```python
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
import random

async def add_contact_by_phone(client, phone, first_name, last_name=""):
    contact = InputPhoneContact(
        client_id=random.randrange(-2**63, 2**63),
        phone=phone,
        first_name=first_name,
        last_name=last_name
    )

    result = await client(ImportContactsRequest(contacts=[contact]))

    # result.imported - успешно импортированные контакты
    # result.popular_invites - популярные приглашения
    # result.retry_contacts - контакты для повторной попытки
    # result.users - информация о пользователях

    return result
```

**Важно:** Новые аккаунты с пустым списком контактов могут импортировать максимум 5 контактов.

#### По username (AddContactRequest)

```python
from telethon.tl.functions.contacts import AddContactRequest

async def add_contact_by_username(client, username, first_name, last_name="", phone=""):
    result = await client(AddContactRequest(
        id=username,
        first_name=first_name,
        last_name=last_name,
        phone=phone,
        add_phone_privacy_exception=True  # Добавить исключение приватности
    ))

    return result
```

### 2.2 Редактирование информации о контакте

Для изменения имени контакта используйте тот же `AddContactRequest`:

```python
async def edit_contact(client, user_id, new_first_name, new_last_name=""):
    result = await client(AddContactRequest(
        id=user_id,
        first_name=new_first_name,
        last_name=new_last_name,
        phone="",
        add_phone_privacy_exception=False
    ))

    return result
```

### 2.3 Удаление контактов

```python
from telethon.tl.functions.contacts import DeleteContactsRequest, DeleteByPhonesRequest

# Удаление по ID пользователя
async def delete_contacts(client, user_ids):
    result = await client(DeleteContactsRequest(id=user_ids))
    return result

# Удаление по номеру телефона
async def delete_contacts_by_phone(client, phones):
    result = await client(DeleteByPhonesRequest(phones=phones))
    return result
```

### 2.4 Блокировка и разблокировка пользователей

```python
from telethon.tl.functions.contacts import BlockRequest, UnblockRequest, GetBlockedRequest

# Заблокировать пользователя
async def block_user(client, user_id):
    result = await client(BlockRequest(id=user_id))
    return result

# Разблокировать пользователя
async def unblock_user(client, user_id):
    result = await client(UnblockRequest(id=user_id))
    return result

# Получить список заблокированных
async def get_blocked_users(client, offset=0, limit=100):
    result = await client(GetBlockedRequest(
        offset=offset,
        limit=limit,
        my_stories_from=False  # Только заблокированные для сторис
    ))
    return result
```

### 2.5 Принятие контактного запроса

```python
from telethon.tl.functions.contacts import AcceptContactRequest

async def accept_contact(client, user_id):
    result = await client(AcceptContactRequest(id=user_id))
    return result
```

---

## 3. Доступная информация о контактах

### 3.1 Базовая информация (объект User)

```python
user.id              # Уникальный ID пользователя
user.first_name      # Имя
user.last_name       # Фамилия
user.username        # Username (без @)
user.phone           # Номер телефона (если доступен)
user.photo           # Фото профиля
user.status          # Статус онлайн
user.bot             # Является ли ботом
user.verified        # Верифицированный аккаунт
user.restricted      # Ограниченный аккаунт
user.premium         # Telegram Premium
user.contact         # Является вашим контактом
user.mutual_contact  # Взаимный контакт
user.lang_code       # Код языка
```

### 3.2 Расширенная информация (UserFull)

```python
from telethon.tl.functions.users import GetFullUserRequest

async def get_full_user_info(client, user_id):
    full = await client(GetFullUserRequest(user_id))
    full_user = full.full_user

    return {
        'about': full_user.about,                    # Био/описание
        'common_chats_count': full_user.common_chats_count,  # Количество общих чатов
        'blocked': full_user.blocked,                # Заблокирован ли вами
        'phone_calls_available': full_user.phone_calls_available,  # Доступны ли звонки
        'phone_calls_private': full_user.phone_calls_private,     # Приватные звонки
        'can_pin_message': full_user.can_pin_message,  # Можно ли закреплять сообщения
        'voice_messages_forbidden': full_user.voice_messages_forbidden,  # Запрещены голосовые
        'profile_photo': full_user.profile_photo,    # Полное фото профиля
        'notify_settings': full_user.notify_settings,  # Настройки уведомлений
        'bot_info': full_user.bot_info,              # Информация о боте (если бот)
        'pinned_msg_id': full_user.pinned_msg_id,    # ID закрепленного сообщения
        'folder_id': full_user.folder_id,            # ID папки
    }
```

### 3.3 Онлайн-статус и последний визит

```python
from telethon.tl.functions.contacts import GetStatusesRequest
from telethon.tl.types import (
    UserStatusOnline,
    UserStatusOffline,
    UserStatusRecently,
    UserStatusLastWeek,
    UserStatusLastMonth,
    UserStatusEmpty
)

async def get_contacts_statuses(client):
    statuses = await client(GetStatusesRequest())

    for contact_status in statuses:
        user_id = contact_status.user_id
        status = contact_status.status

        if isinstance(status, UserStatusOnline):
            print(f"User {user_id}: Online (expires: {status.expires})")
        elif isinstance(status, UserStatusOffline):
            print(f"User {user_id}: Offline (was online: {status.was_online})")
        elif isinstance(status, UserStatusRecently):
            print(f"User {user_id}: Recently (1 min - 3 days ago)")
        elif isinstance(status, UserStatusLastWeek):
            print(f"User {user_id}: Last week (3-7 days ago)")
        elif isinstance(status, UserStatusLastMonth):
            print(f"User {user_id}: Last month (7 days - 1 month ago)")
        else:
            print(f"User {user_id}: Unknown/Hidden status")
```

**Типы статусов:**
- `UserStatusOnline` - сейчас онлайн (содержит `expires` - когда истечет)
- `UserStatusOffline` - оффлайн (содержит `was_online` - когда был)
- `UserStatusRecently` - был недавно (1 мин - 3 дня)
- `UserStatusLastWeek` - был на этой неделе (3-7 дней)
- `UserStatusLastMonth` - был в этом месяце (7 дней - 1 месяц)
- `UserStatusEmpty` - статус неизвестен

### 3.4 Фотографии профиля

```python
# Скачать текущее фото профиля
async def download_current_photo(client, user_id):
    path = await client.download_profile_photo(
        user_id,
        file='profile_photo',
        download_big=True  # Скачать в большом разрешении
    )
    return path

# Получить все фото профиля
from telethon.tl.functions.photos import GetUserPhotosRequest

async def get_all_profile_photos(client, user_id, limit=100):
    photos = await client(GetUserPhotosRequest(
        user_id=user_id,
        offset=0,
        max_id=0,
        limit=limit
    ))

    # Скачать все фото
    for i, photo in enumerate(photos.photos):
        await client.download_media(photo, f'photo_{i}')

    return photos
```

### 3.5 Общие чаты

```python
from telethon.tl.functions.messages import GetCommonChatsRequest

async def get_common_chats(client, user_id, limit=100):
    result = await client(GetCommonChatsRequest(
        user_id=user_id,
        max_id=0,
        limit=limit
    ))

    for chat in result.chats:
        print(f"Common chat: {chat.title}")

    return result.chats
```

---

## 4. Импорт и экспорт контактов

### 4.1 Массовый импорт контактов

```python
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact
import random

async def bulk_import_contacts(client, contacts_data):
    """
    contacts_data: список словарей с ключами phone, first_name, last_name
    """
    input_contacts = []
    for i, contact in enumerate(contacts_data):
        input_contacts.append(InputPhoneContact(
            client_id=i,  # Уникальный идентификатор для сопоставления
            phone=contact['phone'],
            first_name=contact['first_name'],
            last_name=contact.get('last_name', '')
        ))

    result = await client(ImportContactsRequest(contacts=input_contacts))

    print(f"Imported: {len(result.imported)}")
    print(f"Popular invites: {len(result.popular_invites)}")
    print(f"Retry contacts: {len(result.retry_contacts)}")

    return result
```

### 4.2 Экспорт списка контактов

```python
import json
import csv

async def export_contacts_to_json(client, filename='contacts.json'):
    result = await client(GetContactsRequest(hash=0))

    contacts_data = []
    for user in result.users:
        contacts_data.append({
            'id': user.id,
            'first_name': user.first_name,
            'last_name': user.last_name,
            'username': user.username,
            'phone': user.phone
        })

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(contacts_data, f, ensure_ascii=False, indent=2)

    return contacts_data

async def export_contacts_to_csv(client, filename='contacts.csv'):
    result = await client(GetContactsRequest(hash=0))

    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(['ID', 'First Name', 'Last Name', 'Username', 'Phone'])

        for user in result.users:
            writer.writerow([
                user.id,
                user.first_name,
                user.last_name,
                user.username,
                user.phone
            ])
```

### 4.3 Takeout-сессия для экспорта с пониженными лимитами

```python
from telethon import errors

async def export_with_takeout(client):
    try:
        async with client.takeout(contacts=True) as takeout:
            # Запросы через takeout имеют пониженные flood-лимиты
            result = await takeout(GetContactsRequest(hash=0))
            return result
    except errors.TakeoutInitDelayError as e:
        print(f"Need to wait {e.seconds} seconds before takeout")
        raise
```

### 4.4 Синхронизация контактов телефона

```python
async def sync_phone_contacts(client, phone_contacts):
    """
    Синхронизация контактов с телефонной книгой.
    phone_contacts: список словарей с phone, first_name, last_name
    """
    # 1. Получить текущие контакты
    current = await client(GetContactsRequest(hash=0))
    current_phones = {u.phone for u in current.users if u.phone}

    # 2. Найти новые контакты для импорта
    new_contacts = [c for c in phone_contacts if c['phone'] not in current_phones]

    if new_contacts:
        result = await bulk_import_contacts(client, new_contacts)
        return result

    return None
```

### 4.5 Экспорт/импорт токенов контактов

```python
from telethon.tl.functions.contacts import ExportContactTokenRequest, ImportContactTokenRequest

# Экспорт токена для обмена контактом
async def export_contact_token(client):
    result = await client(ExportContactTokenRequest())
    return result.url  # Ссылка для добавления в контакты

# Импорт контакта по токену
async def import_contact_token(client, token):
    result = await client(ImportContactTokenRequest(token=token))
    return result
```

---

## 5. Приватность и ограничения

### 5.1 Ограничения скорости (Rate Limits)

**Общие принципы:**
- Telegram применяет гибкие лимиты в зависимости от поведения аккаунта
- При превышении лимита возникает `FloodWaitError` с указанием времени ожидания
- Обычно ожидание составляет несколько секунд, но может достигать 30 минут

**Рекомендации:**
```python
from telethon import errors
import asyncio

async def safe_request(client, request):
    try:
        return await client(request)
    except errors.FloodWaitError as e:
        print(f"Flood wait: {e.seconds} seconds")
        await asyncio.sleep(e.seconds)
        return await client(request)
```

**Известные ограничения:**
- Новые аккаунты могут импортировать максимум ~5 контактов
- Слишком частый поиск по номерам телефонов может привести к бану этой функции
- Массовые операции (добавление/удаление) требуют задержек между запросами

### 5.2 Ограничения приватности

**Что пользователь может скрыть:**
- Номер телефона
- Статус онлайн/последний визит
- Фото профиля
- Био/описание
- Пересланные сообщения
- Голосовые сообщения

**Последствия для API:**
```python
# При скрытом статусе вместо точного времени получаем приблизительное
if isinstance(user.status, UserStatusRecently):
    # Пользователь был 1 мин - 3 дня назад
    if user.status.by_me:
        # Скрыто именно от нас из-за наших настроек приватности
        pass
```

**Взаимность приватности:**
- Если вы скрываете свой статус от пользователя, вы не увидите его точный статус
- Исключение: подписчики Telegram Premium могут видеть статус, даже скрывая свой

### 5.3 Что требует согласия пользователя

- **Добавление в контакты:** Не требует согласия, но пользователь увидит уведомление
- **Получение номера телефона:** Зависит от настроек приватности пользователя
- **Просмотр статуса:** Зависит от настроек приватности
- **Блокировка:** Не требует согласия
- **Просмотр фото:** Зависит от настроек приватности

---

## 6. Расширенные операции

### 6.1 Поиск пользователя по номеру телефона

```python
from telethon.tl.functions.contacts import ResolvePhoneRequest

async def find_user_by_phone(client, phone):
    """
    Найти пользователя по номеру телефона.
    Работает только если настройки приватности пользователя это позволяют.
    phone: номер в международном формате, например "+79001234567"
    """
    try:
        result = await client(ResolvePhoneRequest(phone=phone))
        if result.users:
            return result.users[0]
        return None
    except Exception as e:
        print(f"Cannot resolve phone: {e}")
        return None
```

**Ограничения:**
- Пользователь может запретить поиск по номеру телефона в настройках
- Слишком частые запросы могут привести к бану этой функции
- По умолчанию Telegram разрешает поиск только контактам

### 6.2 Разрешение username

```python
from telethon.tl.functions.contacts import ResolveUsernameRequest

async def resolve_username(client, username):
    """
    Получить информацию о пользователе/канале по username.
    username: без символа @
    """
    result = await client(ResolveUsernameRequest(
        username=username,
        referer=""  # Опционально: откуда получен username
    ))

    # result.peer - Peer объект
    # result.users - список пользователей
    # result.chats - список чатов/каналов

    return result
```

### 6.3 Получение пользователя по ID

```python
from telethon.tl.types import PeerUser, PeerChat, PeerChannel

async def get_user_by_id(client, user_id):
    """
    Получить пользователя по ID.
    ВАЖНО: Пользователь должен быть ранее "встречен" библиотекой.
    """
    try:
        # Метод 1: Если пользователь уже в кэше
        user = await client.get_entity(PeerUser(user_id))
        return user
    except ValueError:
        # Пользователь не найден в кэше
        # Нужно сначала "встретить" его через другие методы
        return None

async def ensure_user_known(client, user_id):
    """
    Варианты как "познакомить" библиотеку с пользователем:
    """
    # 1. Получить диалоги (если пользователь в них есть)
    dialogs = await client.get_dialogs()

    # 2. Получить участников группы (если пользователь там есть)
    # participants = await client.get_participants(group)

    # 3. Через общий чат
    # await client(GetCommonChatsRequest(...))
```

### 6.4 Получение ID контактов

```python
from telethon.tl.functions.contacts import GetContactIDsRequest

async def get_contact_ids(client):
    """
    Получить только ID контактов (без полной информации).
    Быстрее чем GetContactsRequest.
    """
    result = await client(GetContactIDsRequest(hash=0))
    return result  # Список ID
```

### 6.5 Top Peers (часто используемые контакты)

**Top Peers** — это **автоматический рейтинг** людей, с которыми вы чаще всего взаимодействуете. Telegram сам рассчитывает этот рейтинг на основе:
- Частоты переписки
- Звонков
- Пересылки сообщений

**Где видно в клиенте:** При нажатии "Переслать" или "Поделиться" первыми показываются именно Top Peers.

**Важно:** Top Peers — это люди из **диалогов**, не обязательно из контактов! Человек может быть в Top Peers, даже если вы его не добавляли в контакты.

**Визуальное отображение:** Никак специально не отмечаются — это внутренний рейтинг для сортировки.

```python
from telethon.tl.functions.contacts import GetTopPeersRequest, ToggleTopPeersRequest
from telethon.tl.types import TopPeerCategoryCorrespondents

async def get_top_peers(client, limit=20):
    """
    Получить список часто используемых собеседников.
    Включает людей из диалогов, не обязательно из контактов.
    """
    result = await client(GetTopPeersRequest(
        correspondents=True,  # Частые собеседники
        bots_pm=False,
        bots_inline=False,
        phone_calls=False,
        forward_users=False,
        forward_chats=False,
        groups=False,
        channels=False,
        offset=0,
        limit=limit,
        hash=0
    ))

    return result

async def toggle_top_peers(client, enabled):
    """
    Включить/выключить функцию top peers.
    """
    result = await client(ToggleTopPeersRequest(enabled=enabled))
    return result
```

### 6.6 Близкие друзья (Close Friends)

**Close Friends** — это **ручной список**, который вы сами создаёте. В отличие от Top Peers, это не автоматический рейтинг.

**Для чего используется:**
- Публикация Stories только для близких друзей
- Ограничение видимости определённого контента

**Где настроить в клиенте:** Settings → Privacy → Close Friends

**Визуальное отображение:** В списке контактов рядом с именем близкого друга появляется **зелёная звёздочка** ⭐ (в некоторых клиентах). При публикации Story можно выбрать "Close Friends Only".

**Важно:** Close Friends выбираются только из **контактов**, не из всех диалогов.

```python
from telethon.tl.functions.contacts import EditCloseFriendsRequest

async def set_close_friends(client, user_ids):
    """
    Установить список близких друзей.
    user_ids: список ID пользователей (должны быть в контактах)
    """
    result = await client(EditCloseFriendsRequest(id=user_ids))
    return result

async def get_close_friends(client):
    """
    Получить список близких друзей.
    Проверяем флаг close_friend у контактов.
    """
    contacts = await client.get_contacts()
    close_friends = [u for u in contacts if getattr(u, 'close_friend', False)]
    return close_friends
```

### 6.7 Сохраненные контакты

```python
from telethon.tl.functions.contacts import GetSavedRequest, ResetSavedRequest

async def get_saved_contacts(client):
    """
    Получить сохраненные контакты (без Telegram аккаунта).
    """
    result = await client(GetSavedRequest())
    return result

async def reset_saved_contacts(client):
    """
    Удалить все сохраненные контакты без Telegram аккаунта.
    """
    result = await client(ResetSavedRequest())
    return result
```

### 6.8 Дни рождения контактов

```python
from telethon.tl.functions.contacts import GetBirthdaysRequest

async def get_birthdays(client):
    """
    Получить информацию о днях рождения контактов.
    """
    result = await client(GetBirthdaysRequest())
    return result
```

### 6.9 Примечания к контактам (Contact Notes)

**Примечания** — это личные заметки, которые вы можете добавить к контакту. Это относительно новая функция Telegram (2024).

**Где хранятся:** На **серверах Telegram**, синхронизируются между всеми вашими устройствами.

**Где видно в клиенте:** Откройте профиль контакта → под именем/bio может быть поле "Note" или "Заметка".

**Важные особенности:**
- Примечания видите **только вы** — контакт их не видит
- Работает **только для контактов** — нельзя добавить примечание к человеку, который не в ваших контактах
- Доступно не во всех клиентах (функция постепенно внедряется)

```python
from telethon.tl.functions.contacts import UpdateContactNoteRequest

async def update_contact_note(client, user_id, note):
    """
    Добавить/обновить примечание к контакту.
    Пользователь должен быть в ваших контактах!
    Примечание видите только вы.

    Примеры использования:
    - "Познакомились на конференции, работает в Google"
    - "День рождения 15 марта, любит кофе"
    - "Клиент, проект X"
    """
    result = await client(UpdateContactNoteRequest(
        user_id=user_id,
        note=note
    ))
    return result

async def delete_contact_note(client, user_id):
    """
    Удалить примечание к контакту (установить пустую строку).
    """
    result = await client(UpdateContactNoteRequest(
        user_id=user_id,
        note=""
    ))
    return result
```

---

## 7. Полный список методов contacts.*

| Метод | Описание |
|-------|----------|
| `AcceptContactRequest` | Принять входящий запрос на добавление в контакты |
| `AddContactRequest` | Добавить контакт (по username или ID) |
| `BlockRequest` | Заблокировать пользователя |
| `BlockFromRepliesRequest` | Заблокировать пользователя из ответов |
| `DeleteByPhonesRequest` | Удалить контакты по номерам телефонов |
| `DeleteContactsRequest` | Удалить контакты по ID |
| `EditCloseFriendsRequest` | Управление списком близких друзей |
| `ExportContactTokenRequest` | Экспорт токена для обмена контактом |
| `GetBirthdaysRequest` | Получить дни рождения контактов |
| `GetBlockedRequest` | Получить список заблокированных |
| `GetContactIDsRequest` | Получить ID контактов |
| `GetContactsRequest` | Получить полный список контактов |
| `GetLocatedRequest` | Получить пользователей поблизости |
| `GetSavedRequest` | Получить сохраненные контакты |
| `GetStatusesRequest` | Получить статусы контактов |
| `GetTopPeersRequest` | Получить часто используемые контакты |
| `ImportContactsRequest` | Импортировать контакты по номерам телефонов |
| `ImportContactTokenRequest` | Импортировать контакт по токену |
| `ResetSavedRequest` | Сбросить сохраненные контакты |
| `ResetTopPeerRatingRequest` | Сбросить рейтинг top peer |
| `ResolvePhoneRequest` | Найти пользователя по номеру телефона |
| `ResolveUsernameRequest` | Найти пользователя по username |
| `SearchRequest` | Поиск контактов |
| `SetBlockedRequest` | Установить список заблокированных |
| `ToggleTopPeersRequest` | Включить/выключить top peers |
| `UnblockRequest` | Разблокировать пользователя |
| `UpdateContactNoteRequest` | Обновить примечание к контакту |

---

## 8. Практические примеры

### 8.1 Полный экспорт контактов с детальной информацией

```python
import asyncio
from telethon import TelegramClient
from telethon.tl.functions.contacts import GetContactsRequest
from telethon.tl.functions.users import GetFullUserRequest
import json

async def full_contacts_export(client):
    result = await client(GetContactsRequest(hash=0))

    detailed_contacts = []

    for user in result.users:
        try:
            full = await client(GetFullUserRequest(user.id))

            contact_data = {
                'id': user.id,
                'first_name': user.first_name,
                'last_name': user.last_name,
                'username': user.username,
                'phone': user.phone,
                'bio': full.full_user.about,
                'common_chats': full.full_user.common_chats_count,
                'is_premium': getattr(user, 'premium', False),
                'is_verified': getattr(user, 'verified', False)
            }

            detailed_contacts.append(contact_data)

            # Задержка для избежания flood
            await asyncio.sleep(0.5)

        except Exception as e:
            print(f"Error getting full info for {user.id}: {e}")

    return detailed_contacts
```

### 8.2 Мониторинг статуса контактов

```python
from telethon import TelegramClient, events
from telethon.tl.types import UserStatusOnline, UserStatusOffline

async def monitor_status(client, target_user_id):
    @client.on(events.UserUpdate)
    async def handler(event):
        if event.user_id == target_user_id:
            if isinstance(event.status, UserStatusOnline):
                print(f"User {target_user_id} is now ONLINE")
            elif isinstance(event.status, UserStatusOffline):
                print(f"User {target_user_id} went OFFLINE at {event.status.was_online}")

    await client.run_until_disconnected()
```

### 8.3 Синхронизация контактов между аккаунтами

```python
async def sync_contacts_between_accounts(source_client, target_client):
    # Получить контакты из источника
    source_contacts = await source_client(GetContactsRequest(hash=0))

    # Подготовить для импорта
    contacts_to_import = []
    for i, user in enumerate(source_contacts.users):
        if user.phone:
            contacts_to_import.append(InputPhoneContact(
                client_id=i,
                phone=user.phone,
                first_name=user.first_name or "",
                last_name=user.last_name or ""
            ))

    # Импортировать в целевой аккаунт
    if contacts_to_import:
        result = await target_client(ImportContactsRequest(contacts=contacts_to_import))
        print(f"Imported {len(result.imported)} contacts")
```

---

## Источники

- [Telethon Documentation](https://docs.telethon.dev/)
- [Telethon API Reference](https://tl.telethon.dev/)
- [Telegram MTProto API - Contacts](https://core.telegram.org/api/contacts)
- [Telegram MTProto Methods](https://core.telegram.org/methods)
- [Telethon GitHub](https://github.com/LonamiWebs/Telethon)
- [Telegram Core - contacts.resolvePhone](https://core.telegram.org/method/contacts.resolvePhone)
- [Telegram Core - contacts.deleteContacts](https://core.telegram.org/method/contacts.deleteContacts)
- [Telegram Core - UserStatus](https://core.telegram.org/type/UserStatus)
