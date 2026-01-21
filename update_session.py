"""
Update Session Script for Telegram Gather
Helps re-authorize and update session for Railway deployment
"""
import asyncio
import base64
import zlib
import os
import sys

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from config import config


async def auth_with_qr(client: TelegramClient):
    """Authenticate using QR code"""
    import qrcode

    qr_login = await client.qr_login()

    print("\n" + "=" * 50)
    print("Scan this QR code with Telegram app:")
    print("Settings -> Devices -> Link Desktop Device")
    print("=" * 50 + "\n")

    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(qr_login.url)
    qr.make(fit=True)
    qr.print_ascii(invert=True)

    print("\n" + "=" * 50)

    try:
        await qr_login.wait(timeout=60)
        return True
    except asyncio.TimeoutError:
        print("QR code expired. Please restart and try again.")
        return False
    except SessionPasswordNeededError:
        password = input("Enter your 2FA password: ")
        await client.sign_in(password=password)
        return True


async def auth_with_code(client: TelegramClient):
    """Authenticate using phone code"""
    await client.send_code_request(config["phone"])

    try:
        code = input("Enter the code you received: ")
        await client.sign_in(config["phone"], code)
    except SessionPasswordNeededError:
        password = input("Enter your 2FA password: ")
        await client.sign_in(password=password)


async def main():
    print("=" * 60)
    print("  Telegram Gather - Session Update Tool")
    print("=" * 60)
    print()

    session_file = f"{config['session_name']}.session"

    # Check if old session exists
    if os.path.exists(session_file):
        print(f"Found existing session: {session_file}")
        choice = input("Delete old session and re-authorize? (y/n): ").strip().lower()
        if choice == 'y':
            os.remove(session_file)
            print("Old session deleted.\n")
        else:
            print("Keeping existing session.\n")

    # Create client
    client = TelegramClient(
        config["session_name"],
        config["api_id"],
        config["api_hash"]
    )

    await client.connect()

    if not await client.is_user_authorized():
        print("Authorization required...\n")

        print("Choose authentication method:")
        print("1. QR code (recommended)")
        print("2. Phone code")
        choice = input("Enter 1 or 2: ").strip()

        if choice == "2":
            await auth_with_code(client)
        else:
            success = await auth_with_qr(client)
            if not success:
                await client.disconnect()
                return

    # Get user info
    me = await client.get_me()
    print(f"\n✅ Logged in as: {me.first_name} (@{me.username})")

    await client.disconnect()

    # Generate compressed base64
    print("\n" + "=" * 60)
    print("  SESSION BASE64 FOR RAILWAY")
    print("=" * 60)

    with open(session_file, "rb") as f:
        session_bytes = f.read()

    # Compress to fit Railway's 32KB limit
    compressed = zlib.compress(session_bytes, level=9)
    session_base64 = base64.b64encode(compressed).decode()

    original_size = len(base64.b64encode(session_bytes).decode())
    compressed_size = len(session_base64)

    print(f"\nOriginal size: {original_size} chars")
    print(f"Compressed size: {compressed_size} chars")
    print(f"Compression ratio: {100 - (compressed_size * 100 // original_size)}%")

    if compressed_size > 32768:
        print("\n⚠️ WARNING: Still exceeds Railway's 32KB limit!")
        print("You may need to use Railway Volume storage instead.")
    else:
        print("\n✅ Fits within Railway's 32KB variable limit!")

    print("\nCopy this value and set it as TELEGRAM_SESSION_BASE64 on Railway:\n")
    print("-" * 60)
    print(session_base64)
    print("-" * 60)

    # Copy to clipboard if possible
    try:
        import subprocess
        # Windows
        if sys.platform == "win32":
            subprocess.run(["clip"], input=session_base64.encode(), check=True)
            print("\n✅ Copied to clipboard!")
        # macOS
        elif sys.platform == "darwin":
            subprocess.run(["pbcopy"], input=session_base64.encode(), check=True)
            print("\n✅ Copied to clipboard!")
        # Linux
        else:
            try:
                subprocess.run(["xclip", "-selection", "clipboard"], input=session_base64.encode(), check=True)
                print("\n✅ Copied to clipboard!")
            except FileNotFoundError:
                pass
    except Exception:
        print("\n(Could not copy to clipboard automatically)")

    print("\n" + "=" * 60)
    print("  NEXT STEPS")
    print("=" * 60)
    print("""
1. Go to Railway dashboard -> your project -> Variables
2. Update TELEGRAM_SESSION_BASE64 with the value above
3. Railway will automatically redeploy

Or use Railway CLI:
  railway variables set TELEGRAM_SESSION_BASE64="<paste value>"
""")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCancelled by user")
