"""
Standalone persistent economy system (UnbelievaBoat-style).
SQLite storage with WAL journaling and serialized writes for multi-user safety.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import time
from typing import Any

import discord
from discord import app_commands

import db

DAILY_REWARD = 500
DAILY_COOLDOWN_SECONDS = 86400
LEADERBOARD_LIMIT = 10
ROB_COOLDOWN_SECONDS = 5 * 3600
WORK_CRIME_SLUT_COOLDOWN_MIN = 2 * 3600
WORK_CRIME_SLUT_COOLDOWN_MAX = 5 * 3600
ROB_SUCCESS_CHANCE = 0.50
ROB_STEAL_PERCENT_MIN = 0.15
ROB_STEAL_PERCENT_MAX = 0.40

# Persistent storage paths - Render mounted disk
BASE_DATA_PATH = "/mnt/disk/data"
ECONOMY_DATA_PATH = f"{BASE_DATA_PATH}/economy"

# Ensure economy data directory exists
os.makedirs(ECONOMY_DATA_PATH, exist_ok=True)

DEFAULT_DB_PATH = os.path.join(ECONOMY_DATA_PATH, "economy.db")

_USER_SELECT = (
    "SELECT user_id, balance, bank_balance, last_daily_timestamp, inventory "
    "FROM economy_users WHERE user_id = $1"
)


def _row_get(row: Any, key: str, default: Any = None) -> Any:
    """Safe column read for sqlite3.Row (or missing keys on partial rows)."""
    if row is None:
        return default
    try:
        if hasattr(row, "keys") and key not in row.keys():
            return default
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default

WORK_STORIES = [
    ("You helped fix a broken generator at a construction site and earned **${amt:,}** 💰", True),
    ("You delivered emergency supplies across the city and got paid **${amt:,}** 🚚", True),
    ("You worked a double shift at the auto shop and pocketed **${amt:,}** 🔧", True),
    ("You towed broken-down cars all afternoon and made **${amt:,}** 🛻", True),
    ("You painted road markings overnight and earned **${amt:,}** 🛣️", True),
]

CRIME_STORIES = [
    ("You tried stealing parking meter cash boxes but got caught and fined **${amt:,}** 🚨", False),
    ("You hacked an ATM but only got away with **${amt:,}** before alarms triggered 💳", True),
    ("You got busted running a street scam and lost **${amt:,}** 👮", False),
    ("You flipped stolen electronics for **${amt:,}** 📦", True),
    ("You tried to swipe a delivery van and paid **${amt:,}** in bail 💸", False),
]

SLUT_STORIES = [
    ("You worked a late-night event and earned **${amt:,}** 💃", True),
    ("You entertained at a private party and got tipped **${amt:,}** 🎤", True),
    ("You hosted a VIP lounge night and walked away with **${amt:,}** ✨", True),
    ("You ran a sold-out rooftop show and made **${amt:,}** 🌃", True),
    ("You DJ'd a downtown club and collected **${amt:,}** 🎧", True),
]

ROB_SUCCESS_STORIES = [
    "You successfully stole **${amt:,}** from {target}'s wallet 🏴‍☠️",
    "You pickpocketed **${amt:,}** from {target} and dipped 🕵️",
    "You swiped **${amt:,}** from {target} before anyone noticed 💨",
]

ROB_FAIL_STORIES = [
    "You attempted to rob {target} but got chased off and lost **${amt:,}** 🚓",
    "You tried robbing {target} but security tackled you — fine: **${amt:,}** 🚨",
    "You got caught mid-robbery on {target} and dropped **${amt:,}** 💥",
]


def _normalize_inventory(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        raw.setdefault("items", [])
        raw.setdefault("cooldowns", {})
        return raw
    if isinstance(raw, list):
        return {"items": raw, "cooldowns": {}}
    return {"items": [], "cooldowns": {}}


def _format_eta(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _parse_amount(amount: int) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Enter a valid amount above 0."
    return True, ""


def _resolve_amount(value: str, available: int) -> tuple[bool, int, str]:
    if value.strip().lower() == "all":
        if available <= 0:
            return False, 0, "You don't have anything to move."
        return True, available, ""
    try:
        amount = int(value.replace(",", "").strip())
    except ValueError:
        return False, 0, "Use a number or `all`."
    valid, err = _parse_amount(amount)
    if not valid:
        return False, 0, err
    if amount > available:
        return False, 0, "You don't have enough for that."
    return True, amount, ""


class EconomyStore:
    """PostgreSQL-backed economy storage. Every mutation commits before returning."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()

    async def _run(self, fn, *args, **kwargs):
        async with self._lock:
            result = fn(*args, **kwargs)
            if asyncio.iscoroutine(result):
                return await result
            return result

    async def _ensure_user(self, conn: Any, user_id: int) -> None:
        await conn.execute(
            "INSERT INTO economy_users (user_id, balance, bank_balance, inventory) "
            "VALUES ($1, $2, $3, $4) ON CONFLICT (user_id) DO NOTHING",
            user_id,
            0,
            0,
            {"items": [], "cooldowns": {}},
        )

    async def _fetch_user_row(self, conn: Any, user_id: int) -> Any:
        await self._ensure_user(conn, user_id)
        return await conn.fetchrow(_USER_SELECT, user_id)

    async def _user_dict_from_conn(self, conn: Any, user_id: int) -> dict[str, Any]:
        row = await self._fetch_user_row(conn, user_id)
        if row is None:
            return self._default_user_dict(user_id)
        return self._row_to_dict(row, user_id)

    async def _save_inventory_sync(self, conn: Any, user_id: int, inventory: dict) -> None:
        await conn.execute(
            "UPDATE economy_users SET inventory = $1 WHERE user_id = $2",
            inventory,
            user_id,
        )

    async def _get_user_sync(self, user_id: int) -> dict[str, Any]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            row = await self._fetch_user_row(conn, user_id)
            if row is None:
                return self._default_user_dict(user_id)
            return self._row_to_dict(row, user_id)

    async def _get_rank_sync(self, user_id: int) -> int:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            await self._ensure_user(conn, user_id)
            row = await conn.fetchrow(
                """
                SELECT 1 + COUNT(*) AS rank
                FROM economy_users
                WHERE (balance + bank_balance) > (
                    SELECT (balance + bank_balance) FROM economy_users WHERE user_id = $1
                )
                """,
                user_id,
            )
            return int(_row_get(row, "rank", 1)) if row else 1

    async def _claim_daily_sync(self, user_id: int) -> tuple[bool, str, dict[str, Any]]:
        now = time.time()
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance, last_daily_timestamp FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)

                last_daily = _row_get(row, "last_daily_timestamp")
                if last_daily is not None and (now - float(last_daily)) < DAILY_COOLDOWN_SECONDS:
                    remaining = int(DAILY_COOLDOWN_SECONDS - (now - float(last_daily)))
                    user = await self._user_dict_from_conn(conn, user_id)
                    return False, f"Daily already claimed. Come back in **{_format_eta(remaining)}**.", user

                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1, last_daily_timestamp = $2 WHERE user_id = $3",
                    DAILY_REWARD,
                    now,
                    user_id,
                )
                return True, f"Collected **{DAILY_REWARD:,}** from your daily.", await self._user_dict_from_conn(conn, user_id)

    async def _deposit_sync(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)
                if int(_row_get(row, "balance", 0)) < amount:
                    profile = await self._user_dict_from_conn(conn, user_id)
                    return False, "Not enough in your wallet.", profile

                await conn.execute(
                    "UPDATE economy_users SET balance = balance - $1, bank_balance = bank_balance + $1 WHERE user_id = $2",
                    amount,
                    user_id,
                )
                return True, f"Deposited **{amount:,}** into your bank.", await self._user_dict_from_conn(conn, user_id)

    async def _withdraw_sync(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT bank_balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)
                if int(_row_get(row, "bank_balance", 0)) < amount:
                    profile = await self._user_dict_from_conn(conn, user_id)
                    return False, "Not enough in your bank.", profile

                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1, bank_balance = bank_balance - $1 WHERE user_id = $2",
                    amount,
                    user_id,
                )
                return True, f"Withdrew **{amount:,}** to your wallet.", await self._user_dict_from_conn(conn, user_id)

    async def _transfer_sync(
        self, sender_id: int, receiver_id: int, amount: int
    ) -> tuple[bool, str]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                first_id, second_id = sorted([sender_id, receiver_id])
                await self._ensure_user(conn, first_id)
                await self._ensure_user(conn, second_id)
                sender = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    sender_id,
                )
                if sender is None or int(_row_get(sender, "balance", 0)) < amount:
                    return False, "Not enough cash in your wallet."

                await conn.execute(
                    "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                    amount,
                    sender_id,
                )
                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                    amount,
                    receiver_id,
                )
                return True, "Done."

    async def _admin_adjust_sync(
        self, user_id: int, amount: int, add: bool
    ) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load user.", self._default_user_dict(user_id)
                balance = int(_row_get(row, "balance", 0))
                if add:
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                        amount,
                        user_id,
                    )
                    msg = f"Added **{amount:,}** to <@{user_id}>'s wallet."
                else:
                    new_balance = max(0, balance - amount)
                    removed = balance - new_balance
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        new_balance,
                        user_id,
                    )
                    msg = f"Removed **{removed:,}** from <@{user_id}>'s wallet."
                return True, msg, await self._user_dict_from_conn(conn, user_id)

    async def _activity_sync(
        self,
        user_id: int,
        cooldown_key: str,
        cooldown_seconds: int,
        stories: list,
        amount_range: tuple[int, int],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance, inventory FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", None

                user = self._row_to_dict(row, user_id)
                remaining = self._cooldown_remaining(user["inventory"], cooldown_key)
                if remaining > 0:
                    return False, f"Cooldown — try again in **{_format_eta(remaining)}**.", None

                template, is_gain = random.choice(stories)
                amt = random.randint(amount_range[0], amount_range[1])
                balance = int(_row_get(row, "balance", 0))

                if is_gain:
                    balance += amt
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        balance,
                        user_id,
                    )
                else:
                    loss = min(amt, balance)
                    balance -= loss
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        balance,
                        user_id,
                    )
                    amt = loss

                self._set_cooldown(user["inventory"], cooldown_key, cooldown_seconds)
                await self._save_inventory_sync(conn, user_id, user["inventory"])
                story = template.format(amt=amt)
                return True, story, await self._user_dict_from_conn(conn, user_id)

    async def _rob_sync(
        self, robber_id: int, victim_id: int
    ) -> tuple[bool, str, dict[str, Any] | None]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                first_id, second_id = sorted([robber_id, victim_id])
                await self._ensure_user(conn, first_id)
                await self._ensure_user(conn, second_id)

                robber_row = await conn.fetchrow(
                    "SELECT balance, inventory FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    robber_id,
                )
                victim_row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    victim_id,
                )

                if robber_row is None:
                    return False, "Could not load your profile. Try again.", None

                robber = self._row_to_dict(robber_row, robber_id)
                remaining = self._cooldown_remaining(robber["inventory"], "rob")
                if remaining > 0:
                    return False, f"Rob cooldown — try again in **{_format_eta(remaining)}**.", None

                victim_balance = int(_row_get(victim_row, "balance", 0))
                robber_balance = int(_row_get(robber_row, "balance", 0))

                if victim_balance <= 0:
                    return False, "That user has nothing in their wallet to steal.", None

                success = random.random() < ROB_SUCCESS_CHANCE
                if success:
                    pct = random.uniform(ROB_STEAL_PERCENT_MIN, ROB_STEAL_PERCENT_MAX)
                    stolen = max(1, int(victim_balance * pct))
                    stolen = min(stolen, victim_balance)
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                        stolen,
                        victim_id,
                    )
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                        stolen,
                        robber_id,
                    )
                    story = random.choice(ROB_SUCCESS_STORIES).format(
                        amt=stolen, target=f"<@{victim_id}>"
                    )
                else:
                    loss_cap = max(500, int(robber_balance * 0.15))
                    loss = min(random.randint(1000, 25000), robber_balance, loss_cap)
                    if loss <= 0:
                        story = random.choice(ROB_FAIL_STORIES).format(
                            amt=0, target=f"<@{victim_id}>"
                        )
                    else:
                        await conn.execute(
                            "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                            loss,
                            robber_id,
                        )
                        story = random.choice(ROB_FAIL_STORIES).format(
                            amt=loss, target=f"<@{victim_id}>"
                        )

                self._set_cooldown(robber["inventory"], "rob", ROB_COOLDOWN_SECONDS)
                await self._save_inventory_sync(conn, robber_id, robber["inventory"])
                return True, story, await self._user_dict_from_conn(conn, robber_id)

    async def _leaderboard_sync(self, limit: int) -> list[dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, balance, bank_balance,
                       (balance + bank_balance) AS net_worth
                FROM economy_users
                WHERE (balance + bank_balance) > 0
                ORDER BY net_worth DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "user_id": _row_get(row, "user_id"),
                    "balance": _row_get(row, "balance", 0),
                    "bank_balance": _row_get(row, "bank_balance", 0),
                    "net_worth": _row_get(row, "net_worth", 0),
                }
                for row in rows
            ]
        return {
            "user_id": user_id,
            "balance": 0,
            "bank_balance": 0,
            "last_daily_timestamp": None,
            "inventory": _normalize_inventory([]),
        }

    def _row_to_dict(self, row: Any | None, user_id: int | None = None) -> dict[str, Any]:
        if row is None:
            return self._default_user_dict(user_id or 0)

        uid = _row_get(row, "user_id", user_id)
        if uid is None:
            uid = user_id or 0

        inventory_value = _row_get(row, "inventory", {"items": [], "cooldowns": {}})
        if isinstance(inventory_value, str):
            try:
                parsed = json.loads(inventory_value)
            except json.JSONDecodeError:
                parsed = []
        else:
            parsed = inventory_value

        return {
            "user_id": int(uid),
            "balance": int(_row_get(row, "balance", 0) or 0),
            "bank_balance": int(_row_get(row, "bank_balance", 0) or 0),
            "last_daily_timestamp": _row_get(row, "last_daily_timestamp"),
            "inventory": _normalize_inventory(parsed),
        }

    async def _cooldown_remaining(self, inventory: dict, key: str) -> int:
        cooldowns = inventory.get("cooldowns", {})
        ends_at = cooldowns.get(key)
        if ends_at is None:
            return 0
        return max(0, int(float(ends_at) - time.time()))

    def _set_cooldown(self, inventory: dict, key: str, duration: int) -> None:
        inventory.setdefault("cooldowns", {})[key] = time.time() + duration

    async def _get_user_sync(self, user_id: int) -> dict[str, Any]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            row = await self._fetch_user_row(conn, user_id)
            if row is None:
                return self._default_user_dict(user_id)
            return self._row_to_dict(row, user_id)

    async def _get_rank_sync(self, user_id: int) -> int:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            await self._ensure_user(conn, user_id)
            row = await conn.fetchrow(
                """
                SELECT 1 + COUNT(*) AS rank
                FROM economy_users
                WHERE (balance + bank_balance) > (
                    SELECT (balance + bank_balance) FROM economy_users WHERE user_id = $1
                )
                """,
                user_id,
            )
            return int(_row_get(row, "rank", 1)) if row else 1

    async def _claim_daily_sync(self, user_id: int) -> tuple[bool, str, dict[str, Any]]:
        now = time.time()
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance, last_daily_timestamp FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)

                last_daily = _row_get(row, "last_daily_timestamp")
                if last_daily is not None and (now - float(last_daily)) < DAILY_COOLDOWN_SECONDS:
                    remaining = int(DAILY_COOLDOWN_SECONDS - (now - float(last_daily)))
                    user = await self._user_dict_from_conn(conn, user_id)
                    return False, f"Daily already claimed. Come back in **{_format_eta(remaining)}**.", user

                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1, last_daily_timestamp = $2 WHERE user_id = $3",
                    DAILY_REWARD,
                    now,
                    user_id,
                )
                return True, f"Collected **{DAILY_REWARD:,}** from your daily.", await self._user_dict_from_conn(conn, user_id)

    async def _deposit_sync(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)
                if int(_row_get(row, "balance", 0)) < amount:
                    profile = await self._user_dict_from_conn(conn, user_id)
                    return False, "Not enough in your wallet.", profile

                await conn.execute(
                    "UPDATE economy_users SET balance = balance - $1, bank_balance = bank_balance + $1 WHERE user_id = $2",
                    amount,
                    user_id,
                )
                return True, f"Deposited **{amount:,}** into your bank.", await self._user_dict_from_conn(conn, user_id)

    async def _withdraw_sync(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT bank_balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", self._default_user_dict(user_id)
                if int(_row_get(row, "bank_balance", 0)) < amount:
                    profile = await self._user_dict_from_conn(conn, user_id)
                    return False, "Not enough in your bank.", profile

                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1, bank_balance = bank_balance - $1 WHERE user_id = $2",
                    amount,
                    user_id,
                )
                return True, f"Withdrew **{amount:,}** to your wallet.", await self._user_dict_from_conn(conn, user_id)

    async def _transfer_sync(
        self, sender_id: int, receiver_id: int, amount: int
    ) -> tuple[bool, str]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, sender_id)
                await self._ensure_user(conn, receiver_id)
                sender = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    sender_id,
                )
                if sender is None or int(_row_get(sender, "balance", 0)) < amount:
                    return False, "Not enough cash in your wallet."

                await conn.execute(
                    "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                    amount,
                    sender_id,
                )
                await conn.execute(
                    "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                    amount,
                    receiver_id,
                )
                return True, "Done."

    async def _admin_adjust_sync(
        self, user_id: int, amount: int, add: bool
    ) -> tuple[bool, str, dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load user.", self._default_user_dict(user_id)
                balance = int(_row_get(row, "balance", 0))
                if add:
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                        amount,
                        user_id,
                    )
                    msg = f"Added **{amount:,}** to <@{user_id}>'s wallet."
                else:
                    new_balance = max(0, balance - amount)
                    removed = balance - new_balance
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        new_balance,
                        user_id,
                    )
                    msg = f"Removed **{removed:,}** from <@{user_id}>'s wallet."
                return True, msg, await self._user_dict_from_conn(conn, user_id)

    async def _activity_sync(
        self,
        user_id: int,
        cooldown_key: str,
        cooldown_seconds: int,
        stories: list,
        amount_range: tuple[int, int],
    ) -> tuple[bool, str, dict[str, Any] | None]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, user_id)
                row = await conn.fetchrow(
                    "SELECT balance, inventory FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                if row is None:
                    return False, "Could not load your profile. Try again.", None

                user = self._row_to_dict(row, user_id)
                remaining = self._cooldown_remaining(user["inventory"], cooldown_key)
                if remaining > 0:
                    return False, f"Cooldown — try again in **{_format_eta(remaining)}**.", None

                template, is_gain = random.choice(stories)
                amt = random.randint(amount_range[0], amount_range[1])
                balance = int(_row_get(row, "balance", 0))

                if is_gain:
                    balance += amt
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        balance,
                        user_id,
                    )
                else:
                    loss = min(amt, balance)
                    balance -= loss
                    await conn.execute(
                        "UPDATE economy_users SET balance = $1 WHERE user_id = $2",
                        balance,
                        user_id,
                    )
                    amt = loss

                self._set_cooldown(user["inventory"], cooldown_key, cooldown_seconds)
                await self._save_inventory_sync(conn, user_id, user["inventory"])
                story = template.format(amt=amt)
                return True, story, await self._user_dict_from_conn(conn, user_id)

    async def _rob_sync(
        self, robber_id: int, victim_id: int
    ) -> tuple[bool, str, dict[str, Any] | None]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            async with conn.transaction():
                await self._ensure_user(conn, robber_id)
                await self._ensure_user(conn, victim_id)

                robber_row = await conn.fetchrow(
                    "SELECT balance, inventory FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    robber_id,
                )
                victim_row = await conn.fetchrow(
                    "SELECT balance FROM economy_users WHERE user_id = $1 FOR UPDATE",
                    victim_id,
                )

                if robber_row is None:
                    return False, "Could not load your profile. Try again.", None

                robber = self._row_to_dict(robber_row, robber_id)
                remaining = self._cooldown_remaining(robber["inventory"], "rob")
                if remaining > 0:
                    return False, f"Rob cooldown — try again in **{_format_eta(remaining)}**.", None

                victim_balance = int(_row_get(victim_row, "balance", 0))
                robber_balance = int(_row_get(robber_row, "balance", 0))

                if victim_balance <= 0:
                    return False, "That user has nothing in their wallet to steal.", None

                success = random.random() < ROB_SUCCESS_CHANCE
                if success:
                    pct = random.uniform(ROB_STEAL_PERCENT_MIN, ROB_STEAL_PERCENT_MAX)
                    stolen = max(1, int(victim_balance * pct))
                    stolen = min(stolen, victim_balance)
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                        stolen,
                        victim_id,
                    )
                    await conn.execute(
                        "UPDATE economy_users SET balance = balance + $1 WHERE user_id = $2",
                        stolen,
                        robber_id,
                    )
                    story = random.choice(ROB_SUCCESS_STORIES).format(
                        amt=stolen, target=f"<@{victim_id}>"
                    )
                else:
                    loss_cap = max(500, int(robber_balance * 0.15))
                    loss = min(random.randint(1000, 25000), robber_balance, loss_cap)
                    if loss <= 0:
                        story = random.choice(ROB_FAIL_STORIES).format(
                            amt=0, target=f"<@{victim_id}>"
                        )
                    else:
                        await conn.execute(
                            "UPDATE economy_users SET balance = balance - $1 WHERE user_id = $2",
                            loss,
                            robber_id,
                        )
                        story = random.choice(ROB_FAIL_STORIES).format(
                            amt=loss, target=f"<@{victim_id}>"
                        )

                self._set_cooldown(robber["inventory"], "rob", ROB_COOLDOWN_SECONDS)
                await self._save_inventory_sync(conn, robber_id, robber["inventory"])
                return True, story, await self._user_dict_from_conn(conn, robber_id)

    async def _leaderboard_sync(self, limit: int) -> list[dict[str, Any]]:
        pool = await db.db._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT user_id, balance, bank_balance,
                       (balance + bank_balance) AS net_worth
                FROM economy_users
                WHERE (balance + bank_balance) > 0
                ORDER BY net_worth DESC
                LIMIT $1
                """,
                limit,
            )
            return [
                {
                    "user_id": _row_get(row, "user_id"),
                    "balance": _row_get(row, "balance", 0),
                    "bank_balance": _row_get(row, "bank_balance", 0),
                    "net_worth": _row_get(row, "net_worth", 0),
                }
                for row in rows
            ]

    async def get_user(self, user_id: int) -> dict[str, Any]:
        return await self._run(self._get_user_sync, user_id)

    async def get_rank(self, user_id: int) -> int:
        return await self._run(self._get_rank_sync, user_id)

    async def claim_daily(self, user_id: int) -> tuple[bool, str, dict[str, Any]]:
        return await self._run(self._claim_daily_sync, user_id)

    async def deposit(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        return await self._run(self._deposit_sync, user_id, amount)

    async def withdraw(self, user_id: int, amount: int) -> tuple[bool, str, dict[str, Any]]:
        return await self._run(self._withdraw_sync, user_id, amount)

    async def transfer(
        self, sender_id: int, receiver_id: int, amount: int
    ) -> tuple[bool, str]:
        return await self._run(self._transfer_sync, sender_id, receiver_id, amount)

    async def admin_adjust(
        self, user_id: int, amount: int, add: bool
    ) -> tuple[bool, str, dict[str, Any]]:
        return await self._run(self._admin_adjust_sync, user_id, amount, add)

    async def work(self, user_id: int) -> tuple[bool, str, dict[str, Any] | None]:
        cd = random.randint(WORK_CRIME_SLUT_COOLDOWN_MIN, WORK_CRIME_SLUT_COOLDOWN_MAX)
        return await self._run(
            self._activity_sync, user_id, "work", cd, WORK_STORIES, (2000, 15000)
        )

    async def crime(self, user_id: int) -> tuple[bool, str, dict[str, Any] | None]:
        cd = random.randint(WORK_CRIME_SLUT_COOLDOWN_MIN, WORK_CRIME_SLUT_COOLDOWN_MAX)
        return await self._run(
            self._activity_sync, user_id, "crime", cd, CRIME_STORIES, (5000, 120000)
        )

    async def slut(self, user_id: int) -> tuple[bool, str, dict[str, Any] | None]:
        cd = random.randint(WORK_CRIME_SLUT_COOLDOWN_MIN, WORK_CRIME_SLUT_COOLDOWN_MAX)
        return await self._run(
            self._activity_sync, user_id, "slut", cd, SLUT_STORIES, (3000, 18000)
        )

    async def rob(
        self, robber_id: int, victim_id: int
    ) -> tuple[bool, str, dict[str, Any] | None]:
        return await self._run(self._rob_sync, robber_id, victim_id)

    async def leaderboard(self, limit: int = LEADERBOARD_LIMIT) -> list[dict[str, Any]]:
        return await self._run(self._leaderboard_sync, limit)


def _money_embed(user: dict, rank: int | None, embed_color: int) -> discord.Embed:
    net = user["balance"] + user["bank_balance"]
    desc = (
        f"💵 **Wallet:** `{user['balance']:,}`\n"
        f"🏦 **Bank:** `{user['bank_balance']:,}`\n"
        f"💎 **Net worth:** `{net:,}`"
    )
    if rank is not None:
        desc += f"\n📊 **Rank:** `#{rank}`"
    return discord.Embed(
        title="💰 Balance",
        description=desc,
        color=embed_color,
    )


def _result_embed(title: str, story: str, user: dict | None, embed_color: int) -> discord.Embed:
    desc = story
    if user is not None:
        desc += (
            f"\n\n💵 Wallet: `{user['balance']:,}` · "
            f"🏦 Bank: `{user['bank_balance']:,}`"
        )
    return discord.Embed(title=title, description=desc, color=embed_color)


def setup(bot: discord.ext.commands.Bot, embed_color: int) -> EconomyStore:
    """Register economy slash commands on the bot."""
    store = EconomyStore()

    async def _member_name(guild: discord.Guild | None, user_id: int) -> str:
        if guild is None:
            return f"User {user_id}"
        member = guild.get_member(user_id)
        return member.display_name if member else f"User {user_id}"

    @bot.tree.command(name="money", description="Check your wallet, bank, and net worth")
    async def money(interaction: discord.Interaction):
        user = await store.get_user(interaction.user.id)
        rank = await store.get_rank(interaction.user.id)
        await interaction.response.send_message(
            embed=_money_embed(user, rank, embed_color)
        )

    @bot.tree.command(name="daily", description="Claim your daily cash")
    async def daily(interaction: discord.Interaction):
        ok, message, user = await store.claim_daily(interaction.user.id)
        title = "📅 Daily" if ok else "⏳ Daily"
        await interaction.response.send_message(
            embed=_result_embed(title, message, user if ok else None, embed_color)
        )

    @bot.tree.command(name="deposit", description="Deposit cash into your bank")
    @app_commands.describe(amount="Amount or `all`")
    async def deposit(interaction: discord.Interaction, amount: str):
        user = await store.get_user(interaction.user.id)
        ok_amt, value, err = _resolve_amount(amount, user["balance"])
        if not ok_amt:
            await interaction.response.send_message(err)
            return
        ok, message, user = await store.deposit(interaction.user.id, value)
        if not ok:
            await interaction.response.send_message(message)
            return
        await interaction.response.send_message(
            embed=_result_embed("🏦 Deposit", message, user, embed_color)
        )

    @bot.tree.command(name="withdraw", description="Withdraw cash from your bank")
    @app_commands.describe(amount="Amount or `all`")
    async def withdraw(interaction: discord.Interaction, amount: str):
        user = await store.get_user(interaction.user.id)
        ok_amt, value, err = _resolve_amount(amount, user["bank_balance"])
        if not ok_amt:
            await interaction.response.send_message(err)
            return
        ok, message, user = await store.withdraw(interaction.user.id, value)
        if not ok:
            await interaction.response.send_message(message)
            return
        await interaction.response.send_message(
            embed=_result_embed("🏧 Withdraw", message, user, embed_color)
        )

    @bot.tree.command(name="give-money", description="Send wallet cash to someone")
    @app_commands.describe(user="Who to pay", amount="How much")
    async def give_money(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 999_999_999],
    ):
        if user.bot:
            await interaction.response.send_message("Can't pay bots.")
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("Can't pay yourself.")
            return

        ok, message = await store.transfer(interaction.user.id, user.id, amount)
        if not ok:
            await interaction.response.send_message(message)
            return

        sender = await store.get_user(interaction.user.id)
        await interaction.response.send_message(
            embed=discord.Embed(
                title="💸 Payment",
                description=(
                    f"{interaction.user.mention} → {user.mention}\n"
                    f"Sent **`{amount:,}`**\n\n"
                    f"💵 Your wallet: `{sender['balance']:,}`"
                ),
                color=embed_color,
            )
        )

    @bot.tree.command(name="leaderboard", description="Richest players on the server")
    async def leaderboard(interaction: discord.Interaction):
        rows = await store.leaderboard()
        if not rows:
            await interaction.response.send_message(
                "Nobody's on the board yet. Run `/daily` or `/work` first."
            )
            return

        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        lines = []
        for i, row in enumerate(rows):
            medal = medals[i] if i < len(medals) else f"**{i + 1}.**"
            name = await _member_name(interaction.guild, row["user_id"])
            lines.append(f"{medal} **{name}** — `{int(row['net_worth']):,}`")

        await interaction.response.send_message(
            embed=discord.Embed(
                title="📊 Leaderboard",
                description="\n".join(lines),
                color=embed_color,
            )
        )

    @bot.tree.command(name="work", description="Work a job for cash")
    async def work(interaction: discord.Interaction):
        ok, story, user = await store.work(interaction.user.id)
        if not ok:
            await interaction.response.send_message(
                embed=_result_embed("⏳ Work", story, None, embed_color)
            )
            return
        await interaction.response.send_message(
            embed=_result_embed("🛠 Work", story, user, embed_color)
        )

    @bot.tree.command(name="crime", description="Take a risky shot at fast cash")
    async def crime(interaction: discord.Interaction):
        ok, story, user = await store.crime(interaction.user.id)
        if not ok:
            await interaction.response.send_message(
                embed=_result_embed("⏳ Crime", story, None, embed_color)
            )
            return
        await interaction.response.send_message(
            embed=_result_embed("🏴 Crime", story, user, embed_color)
        )

    @bot.tree.command(name="slut", description="Hustle for tips at events")
    async def slut(interaction: discord.Interaction):
        ok, story, user = await store.slut(interaction.user.id)
        if not ok:
            await interaction.response.send_message(
                embed=_result_embed("⏳ Hustle", story, None, embed_color)
            )
            return
        await interaction.response.send_message(
            embed=_result_embed("🔥 Hustle", story, user, embed_color)
        )

    @bot.tree.command(name="rob", description="Attempt to rob another user's wallet")
    @app_commands.describe(user="Who to rob")
    async def rob(interaction: discord.Interaction, user: discord.Member):
        if user.bot:
            await interaction.response.send_message("Can't rob bots.")
            return
        if user.id == interaction.user.id:
            await interaction.response.send_message("Can't rob yourself.")
            return

        ok, story, profile = await store.rob(interaction.user.id, user.id)
        if not ok:
            await interaction.response.send_message(
                embed=_result_embed("⏳ Rob", story, None, embed_color)
            )
            return
        await interaction.response.send_message(
            embed=_result_embed("🕵️ Rob", story, profile, embed_color)
        )

    @bot.tree.command(name="add-money", description="Add cash to a user's wallet (Admin)")
    @app_commands.describe(user="Target", amount="Amount to add")
    @app_commands.default_permissions(administrator=True)
    async def add_money(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 999_999_999],
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only.")
            return
        ok, message, profile = await store.admin_adjust(user.id, amount, add=True)
        await interaction.response.send_message(
            embed=_result_embed("👑 Admin", message, profile, embed_color)
        )

    @bot.tree.command(name="remove-money", description="Remove cash from a user's wallet (Admin)")
    @app_commands.describe(user="Target", amount="Amount to remove")
    @app_commands.default_permissions(administrator=True)
    async def remove_money(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 999_999_999],
    ):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Admin only.")
            return
        ok, message, profile = await store.admin_adjust(user.id, amount, add=False)
        await interaction.response.send_message(
            embed=_result_embed("👑 Admin", message, profile, embed_color)
        )

    return store
