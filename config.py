import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

@dataclass
class Config:
    BOT_TOKEN: str
    PUBLIC_CHANNEL: str
    PRIVATE_CHANNEL_ID: int
    INVITE_TARGET: int
    ADMIN_IDS: list[int]

def _parse_admin_ids(raw: str) -> list[int]:
    ids = []
    for part in (raw or "").replace(" ", "").split(","):
        if not part:
            continue
        if part.lstrip("-").isdigit():
            # admin id odatda musbat bo‘ladi. Siz bergan 503... to‘g‘ri.
            ids.append(int(part))
    return ids

def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    pub = os.getenv("PUBLIC_CHANNEL", "").strip()
    priv = os.getenv("PRIVATE_CHANNEL_ID", "").strip()
    target = os.getenv("INVITE_TARGET", "5").strip()
    admin_raw = os.getenv("ADMIN_IDS", "").strip()

    if not token:
        raise RuntimeError("BOT_TOKEN .env da yo‘q")
    if not pub.startswith("@"):
        raise RuntimeError("PUBLIC_CHANNEL '@username' ko‘rinishida bo‘lishi kerak")
    if not priv:
        raise RuntimeError("PRIVATE_CHANNEL_ID .env da yo‘q (masalan -100...)")
    admins = _parse_admin_ids(admin_raw)
    if not admins:
        raise RuntimeError("ADMIN_IDS .env da yo‘q (masalan ADMIN_IDS=5037587016)")

    return Config(
        BOT_TOKEN=token,
        PUBLIC_CHANNEL=pub,
        PRIVATE_CHANNEL_ID=int(priv),
        INVITE_TARGET=int(target),
        ADMIN_IDS=admins,
    )