"""
Standalone persistent economy system (UnbelievaBoat-style).
SQLite storage with WAL journaling and serialized writes for multi-user safety.
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import time
from typing import Any

import discord
from discord import app_commands

DAILY_REWARD = 500
DAILY_COOLDOWN_SECONDS = 86400
LEADERBOARD_LIMIT = 10
DEFAULT_DB_PATH = os.path.join(
    os.getenv("DATA_DIR", "/mnt/disk"),
    "economy.db",
)


class EconomyStore:
    """SQLite-backed economy storage. Every mutation commits before returning."""

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._lock = asyncio.Lock()
        os.makedirs(os.path.dirname(db_path) or ".", exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
                    bank_balance INTEGER NOT NULL DEFAULT 0 CHECK (bank_balance >= 0),
                    last_daily_timestamp REAL,
                    inventory TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
            conn.commit()

    async def _run(self, fn, *args, **kwargs):
        async with self._lock:
            return await asyncio.to_thread(fn, *args, **kwargs)

    def _ensure_user_sync(self, conn: sqlite3.Connection, user_id: int) -> None:
        conn.execute(
            "INSERT OR IGNORE INTO users (user_id, balance, bank_balance, inventory) "
            "VALUES (?, 0, 0, '[]')",
            (user_id,),
        )

    def _row_to_dict(self, row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            return {
                "user_id": 0,
                "balance": 0,
                "bank_balance": 0,
                "last_daily_timestamp": None,
                "inventory": [],
            }
        inventory_raw = row["inventory"] or "[]"
        try:
            inventory = json.loads(inventory_raw)
        except json.JSONDecodeError:
            inventory = []
        return {
            "user_id": row["user_id"],
            "balance": int(row["balance"]),
            "bank_balance": int(row["bank_balance"]),
            "last_daily_timestamp": row["last_daily_timestamp"],
            "inventory": inventory,
        }

    def _get_user_sync(self, user_id: int) -> dict[str, Any]:
        with self._connect() as conn:
            self._ensure_user_sync(conn, user_id)
            row = conn.execute(
                "SELECT user_id, balance, bank_balance, last_daily_timestamp, inventory "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            conn.commit()
            return self._row_to_dict(row)

    def _claim_daily_sync(self, user_id: int) -> tuple[bool, str, dict[str, Any]]:
        now = time.time()
        with self._connect() as conn:
            self._ensure_user_sync(conn, user_id)
            row = conn.execute(
                "SELECT balance, bank_balance, last_daily_timestamp, inventory "
                "FROM users WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            last_daily = row["last_daily_timestamp"]
            if last_daily is not None and (now - float(last_daily)) < DAILY_COOLDOWN_SECONDS:
                remaining = int(DAILY_COOLDOWN_SECONDS - (now - float(last_daily)))
                conn.commit()
                user = self._row_to_dict(
                    conn.execute(
                        "SELECT user_id, balance, bank_balance, last_daily_timestamp, inventory "
                        "FROM users WHERE user_id = ?",
                        (user_id,),
                    ).fetchone()
                )
                return False, f"You have already claimed your daily. Try again in {remaining} seconds.", user

            conn.execute(
                "UPDATE users SET balance = balance + ?, last_daily_timestamp = ? WHERE user_id = ?",
                (DAILY_REWARD, now, user_id),
            )
            conn.commit()
            user = self._get_user_sync(user_id)
            return True, f"You received **{DAILY_REWARD:,}** coins!", user

    def _transfer_sync(
        self, sender_id: int, receiver_id: int, amount: int
    ) -> tuple[bool, str]:
        with self._connect() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                self._ensure_user_sync(conn, sender_id)
                self._ensure_user_sync(conn, receiver_id)

                sender = conn.execute(
                    "SELECT balance FROM users WHERE user_id = ?", (sender_id,)
                ).fetchone()
                if sender["balance"] < amount:
                    conn.rollback()
                    return False, "You do not have enough coins in your wallet."

                conn.execute(
                    "UPDATE users SET balance = balance - ? WHERE user_id = ?",
                    (amount, sender_id),
                )
                conn.execute(
                    "UPDATE users SET balance = balance + ? WHERE user_id = ?",
                    (amount, receiver_id),
                )
                conn.commit()
                return True, "Transfer completed."
            except Exception:
                conn.rollback()
                raise

    def _leaderboard_sync(self, limit: int) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, balance, bank_balance,
                       (balance + bank_balance) AS net_worth
                FROM users
                WHERE (balance + bank_balance) > 0
                ORDER BY net_worth DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
            conn.commit()
            return [dict(row) for row in rows]

    async def get_user(self, user_id: int) -> dict[str, Any]:
        return await self._run(self._get_user_sync, user_id)

    async def claim_daily(self, user_id: int) -> tuple[bool, str, dict[str, Any]]:
        return await self._run(self._claim_daily_sync, user_id)

    async def transfer(
        self, sender_id: int, receiver_id: int, amount: int
    ) -> tuple[bool, str]:
        return await self._run(self._transfer_sync, sender_id, receiver_id, amount)

    async def leaderboard(self, limit: int = LEADERBOARD_LIMIT) -> list[dict[str, Any]]:
        return await self._run(self._leaderboard_sync, limit)


def _parse_amount(amount: int) -> tuple[bool, str]:
    if amount <= 0:
        return False, "Amount must be a positive number."
    return True, ""


def setup(bot: discord.ext.commands.Bot, embed_color: int) -> EconomyStore:
    """Register economy slash commands on the bot. Returns the store instance."""
    store = EconomyStore()

    @bot.tree.command(name="balance", description="View your wallet and bank balance")
    async def balance(interaction: discord.Interaction):
        user = await store.get_user(interaction.user.id)
        net_worth = user["balance"] + user["bank_balance"]

        embed = discord.Embed(
            title="Greenville Roleplay Global | Balance",
            description=(
                f"> **Wallet:** `{user['balance']:,}`\n"
                f"> **Bank:** `{user['bank_balance']:,}`\n"
                f"> **Net Worth:** `{net_worth:,}`"
            ),
            color=embed_color,
        )
        embed.set_footer(text="Economy System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="daily", description="Claim your daily coin reward")
    async def daily(interaction: discord.Interaction):
        ok, message, user = await store.claim_daily(interaction.user.id)

        embed = discord.Embed(
            title="Greenville Roleplay Global | Daily Reward",
            description=message,
            color=embed_color,
        )
        if ok:
            embed.add_field(
                name="New Wallet Balance",
                value=f"`{user['balance']:,}`",
                inline=False,
            )
        embed.set_footer(text="Economy System")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="pay", description="Pay another user from your wallet")
    @app_commands.describe(user="Member to pay", amount="Amount to send")
    async def pay(
        interaction: discord.Interaction,
        user: discord.Member,
        amount: app_commands.Range[int, 1, 999_999_999],
    ):
        valid, err = _parse_amount(amount)
        if not valid:
            await interaction.response.send_message(err, ephemeral=True)
            return

        if user.bot:
            await interaction.response.send_message(
                "You cannot pay bots.", ephemeral=True
            )
            return

        if user.id == interaction.user.id:
            await interaction.response.send_message(
                "You cannot pay yourself.", ephemeral=True
            )
            return

        ok, message = await store.transfer(interaction.user.id, user.id, amount)
        if not ok:
            await interaction.response.send_message(message, ephemeral=True)
            return

        sender = await store.get_user(interaction.user.id)
        receiver = await store.get_user(user.id)

        embed = discord.Embed(
            title="Greenville Roleplay Global | Payment",
            description=(
                f"{interaction.user.mention} paid {user.mention} **`{amount:,}`** coins.\n\n"
                f"> **Your wallet:** `{sender['balance']:,}`\n"
                f"> **{user.display_name}'s wallet:** `{receiver['balance']:,}`"
            ),
            color=embed_color,
        )
        embed.set_footer(text="Economy System")
        await interaction.response.send_message(embed=embed)

    @bot.tree.command(name="leaderboard", description="Top users by net worth")
    async def leaderboard(interaction: discord.Interaction):
        rows = await store.leaderboard()
        if not rows:
            await interaction.response.send_message(
                "No economy data yet. Use `/daily` to get started!",
                ephemeral=True,
            )
            return

        lines = []
        medals = ["🥇", "🥈", "🥉"]
        for i, row in enumerate(rows, start=1):
            prefix = medals[i - 1] if i <= 3 else f"**{i}.**"
            member = interaction.guild.get_member(row["user_id"]) if interaction.guild else None
            name = member.display_name if member else f"User {row['user_id']}"
            net_worth = int(row["net_worth"])
            lines.append(f"{prefix} {name} — `{net_worth:,}`")

        embed = discord.Embed(
            title="Greenville Roleplay Global | Economy Leaderboard",
            description="\n".join(lines),
            color=embed_color,
        )
        embed.set_footer(text="Sorted by wallet + bank | Economy System")
        await interaction.response.send_message(embed=embed)

    return store
