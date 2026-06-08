from __future__ import annotations

import asyncio
import json
import os
import sqlite3
from typing import Any

import asyncpg

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL environment variable is required for PostgreSQL storage.")

LEGACY_ECONOMY_DB_PATH = "/mnt/disk/data/economy/economy.db"
LEGACY_REGISTRATIONS_PATH = "/mnt/disk/data/profiles/registrations.json"
LEGACY_BLACKLIST_PATH = "/mnt/disk/data/systems/blacklist.json"
LEGACY_STATUS_PATH = "/mnt/disk/data/systems/ticket_status.json"
LEGACY_EARLY_ACCESS_PATH = "/mnt/disk/data/systems/early_access.json"


class Database:
    def __init__(self, dsn: str):
        self._dsn = dsn
        self._pool: asyncpg.Pool | None = None
        self._init_lock = asyncio.Lock()

    async def _get_pool(self) -> asyncpg.Pool:
        if self._pool is None:
            async with self._init_lock:
                if self._pool is None:
                    self._pool = await asyncpg.create_pool(dsn=self._dsn, min_size=1, max_size=10)
                    async with self._pool.acquire() as conn:
                        await self._ensure_schema(conn)
                        await self._migrate_legacy(conn)
        return self._pool

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.fetchval(query, *args)

    async def execute(self, query: str, *args: Any) -> str:
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            return await conn.execute(query, *args)

    async def _ensure_schema(self, conn: asyncpg.Connection) -> None:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS economy_users (
                user_id BIGINT PRIMARY KEY,
                balance BIGINT NOT NULL DEFAULT 0 CHECK (balance >= 0),
                bank_balance BIGINT NOT NULL DEFAULT 0 CHECK (bank_balance >= 0),
                last_daily_timestamp DOUBLE PRECISION,
                inventory JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS registrations (
                discord_id BIGINT PRIMARY KEY,
                registrations JSONB NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS blacklist (
                id SERIAL PRIMARY KEY,
                server_name TEXT NOT NULL,
                server_id TEXT NOT NULL,
                reason TEXT NOT NULL,
                notes TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value JSONB NOT NULL
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS early_access (
                id INTEGER PRIMARY KEY,
                session_active BOOLEAN NOT NULL DEFAULT FALSE,
                server_link TEXT NOT NULL DEFAULT '',
                panel_channel_id BIGINT,
                panel_message_id BIGINT,
                joined_user_ids JSONB NOT NULL DEFAULT '[]'::jsonb
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS tickets (
                ticket_id SERIAL PRIMARY KEY,
                channel_id BIGINT,
                opener_id BIGINT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                state JSONB NOT NULL DEFAULT '{}'
            )
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS cooldowns (
                user_id BIGINT NOT NULL,
                cooldown_key TEXT NOT NULL,
                expires_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY (user_id, cooldown_key)
            )
            """
        )

    async def _migrate_legacy(self, conn: asyncpg.Connection) -> None:
        if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM economy_users)"):
            await self._migrate_economy_sqlite(conn)
        if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM registrations)"):
            await self._migrate_registrations_json(conn)
        if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM blacklist)"):
            await self._migrate_blacklist_json(conn)
        if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM system_state)"):
            await self._migrate_status_json(conn)
        if not await conn.fetchval("SELECT EXISTS (SELECT 1 FROM early_access)"):
            await self._migrate_early_access_json(conn)

    async def _migrate_economy_sqlite(self, conn: asyncpg.Connection) -> None:
        if not os.path.exists(LEGACY_ECONOMY_DB_PATH):
            return
        try:
            with sqlite3.connect(LEGACY_ECONOMY_DB_PATH) as legacy:
                legacy.row_factory = sqlite3.Row
                cursor = legacy.execute(
                    "SELECT user_id, balance, bank_balance, last_daily_timestamp, inventory FROM users"
                )
                rows = cursor.fetchall()
        except sqlite3.Error:
            return

        for row in rows:
            inventory_raw = row["inventory"] if row["inventory"] is not None else "[]"
            try:
                inventory = json.loads(inventory_raw)
            except (json.JSONDecodeError, TypeError):
                inventory = []

            await conn.execute(
                """
                INSERT INTO economy_users (user_id, balance, bank_balance, last_daily_timestamp, inventory)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (user_id) DO NOTHING
                """,
                int(row["user_id"] or 0),
                int(row["balance"] or 0),
                int(row["bank_balance"] or 0),
                float(row["last_daily_timestamp"]) if row["last_daily_timestamp"] is not None else None,
                inventory,
            )

            if isinstance(inventory, dict):
                cooldowns = inventory.get("cooldowns") or {}
                if isinstance(cooldowns, dict):
                    for key, expires in cooldowns.items():
                        try:
                            expires_at = float(expires)
                        except (TypeError, ValueError):
                            continue
                        await conn.execute(
                            """
                            INSERT INTO cooldowns (user_id, cooldown_key, expires_at)
                            VALUES ($1, $2, $3)
                            ON CONFLICT (user_id, cooldown_key) DO UPDATE SET expires_at = EXCLUDED.expires_at
                            """,
                            int(row["user_id"] or 0),
                            str(key),
                            expires_at,
                        )

    async def _migrate_registrations_json(self, conn: asyncpg.Connection) -> None:
        if not os.path.exists(LEGACY_REGISTRATIONS_PATH):
            return
        try:
            with open(LEGACY_REGISTRATIONS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict):
            return

        await conn.execute("DELETE FROM registrations")
        for raw_id, registrations in data.items():
            try:
                discord_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            if not isinstance(registrations, list):
                continue
            await conn.execute(
                """
                INSERT INTO registrations (discord_id, registrations)
                VALUES ($1, $2)
                ON CONFLICT (discord_id) DO UPDATE SET registrations = EXCLUDED.registrations
                """,
                discord_id,
                registrations,
            )

    async def _migrate_blacklist_json(self, conn: asyncpg.Connection) -> None:
        if not os.path.exists(LEGACY_BLACKLIST_PATH):
            return
        try:
            with open(LEGACY_BLACKLIST_PATH, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, list):
            return

        await conn.execute("DELETE FROM blacklist")
        for entry in data:
            if not isinstance(entry, dict):
                continue
            await conn.execute(
                """
                INSERT INTO blacklist (server_name, server_id, reason, notes)
                VALUES ($1, $2, $3, $4)
                """,
                entry.get("server_name", ""),
                entry.get("server_id", ""),
                entry.get("reason", ""),
                entry.get("notes", ""),
            )

    async def _migrate_status_json(self, conn: asyncpg.Connection) -> None:
        if not os.path.exists(LEGACY_STATUS_PATH):
            return
        try:
            with open(LEGACY_STATUS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict):
            return

        await conn.execute(
            """
            INSERT INTO system_state (key, value)
            VALUES ($1, $2)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            "ticket_status",
            data,
        )

    async def _migrate_early_access_json(self, conn: asyncpg.Connection) -> None:
        if not os.path.exists(LEGACY_EARLY_ACCESS_PATH):
            return
        try:
            with open(LEGACY_EARLY_ACCESS_PATH, "r") as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            return

        if not isinstance(data, dict):
            return

        await conn.execute("DELETE FROM early_access")
        await conn.execute(
            """
            INSERT INTO early_access (id, session_active, server_link, panel_channel_id, panel_message_id, joined_user_ids)
            VALUES (1, $1, $2, $3, $4, $5)
            ON CONFLICT (id) DO UPDATE SET
                session_active = EXCLUDED.session_active,
                server_link = EXCLUDED.server_link,
                panel_channel_id = EXCLUDED.panel_channel_id,
                panel_message_id = EXCLUDED.panel_message_id,
                joined_user_ids = EXCLUDED.joined_user_ids
            """,
            bool(data.get("session_active", False)),
            str(data.get("server_link", "")),
            data.get("panel_channel_id"),
            data.get("panel_message_id"),
            data.get("joined_user_ids", []),
        )

    async def close(self) -> None:
        if self._pool is not None:
            await self._pool.close()
            self._pool = None


db = Database(DATABASE_URL)
