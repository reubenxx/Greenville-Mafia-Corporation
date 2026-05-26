"""
Early Access session panel — persistent storage, host-only /early-access, role-gated joins.
"""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
from typing import Any, Callable

import discord
from discord import app_commands, ui

EARLY_ACCESS_ROLE_ID = 1508411766189850728
STAFF_ROLE_ID = 1474123995375992873

DENY_JOIN_MESSAGE = (
    "You are unauthorized to join via **early access**. "
    "Please wait for the **official release** of the session."
)

DEFAULT_STATE: dict[str, Any] = {
    "session_active": False,
    "server_link": "",
    "panel_channel_id": None,
    "panel_message_id": None,
    "joined_user_ids": [],
}


class EarlyAccessStore:
    def __init__(self, data_path: str):
        self.data_path = data_path
        self._lock = asyncio.Lock()
        os.makedirs(os.path.dirname(data_path) or ".", exist_ok=True)
        if not os.path.exists(data_path):
            self._write_sync(DEFAULT_STATE.copy())

    def _write_sync(self, data: dict[str, Any]) -> None:
        directory = os.path.dirname(self.data_path) or "."
        with tempfile.NamedTemporaryFile("w", delete=False, dir=directory) as tmp:
            json.dump(data, tmp, indent=4)
            temp_name = tmp.name
        os.replace(temp_name, self.data_path)

    def _read_sync(self) -> dict[str, Any]:
        if not os.path.exists(self.data_path):
            return DEFAULT_STATE.copy()
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return DEFAULT_STATE.copy()
        merged = DEFAULT_STATE.copy()
        merged.update(data)
        merged["joined_user_ids"] = list(merged.get("joined_user_ids") or [])
        return merged

    async def load(self) -> dict[str, Any]:
        async with self._lock:
            return await asyncio.to_thread(self._read_sync)

    async def save(self, data: dict[str, Any]) -> None:
        async with self._lock:
            await asyncio.to_thread(self._write_sync, data)

    async def reset_session(self) -> None:
        data = await self.load()
        data["session_active"] = False
        data["server_link"] = ""
        data["joined_user_ids"] = []
        await self.save(data)

    async def record_join(self, user_id: int) -> tuple[bool, dict[str, Any]]:
        async with self._lock:
            data = self._read_sync()
            joined = data.get("joined_user_ids") or []
            is_new = user_id not in joined
            if is_new:
                joined.append(user_id)
                data["joined_user_ids"] = joined
                self._write_sync(data)
            return is_new, data


def _can_join_early_access(member: discord.Member) -> bool:
    if member.guild_permissions.administrator:
        return True
    return any(role.id == EARLY_ACCESS_ROLE_ID for role in member.roles)


def _join_counter_text(count: int) -> str:
    return f"> -# **Early Access Joins: {count}**"


def _build_panel_embed(embed_color: int, footer_icon: str) -> discord.Embed:
    embed = discord.Embed(
        title="Greenville Roleplay Global | Early Access",
        description=(
            f"> The session has been released to those with the <@&{EARLY_ACCESS_ROLE_ID}> role. "
            "If you do not hold this role, you must wait for the **official session release**. "
            "Leaking of this link will result in immediate **restrictions.**"
        ),
        color=embed_color,
    )
    embed.set_footer(text="Early Access Release", icon_url=footer_icon)
    return embed


class EarlyAccessView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Early Access",
        style=discord.ButtonStyle.secondary,
        custom_id="early_access:join",
    )
    async def early_access_join(
        self, interaction: discord.Interaction, button: ui.Button
    ):
        store: EarlyAccessStore = interaction.client.early_access_store  # type: ignore[attr-defined]
        bot = interaction.client

        state = await store.load()
        if not state.get("session_active"):
            await interaction.response.send_message(DENY_JOIN_MESSAGE, ephemeral=True)
            return

        member = interaction.user
        if not isinstance(member, discord.Member) or not _can_join_early_access(member):
            await interaction.response.send_message(DENY_JOIN_MESSAGE, ephemeral=True)
            return

        link = (state.get("server_link") or "").strip()
        if not link:
            await interaction.response.send_message(
                "Early access is not ready yet. Please wait for the host.",
                ephemeral=True,
            )
            return

        is_new, state = await store.record_join(member.id)

        if is_new and state.get("panel_channel_id") and state.get("panel_message_id"):
            channel = bot.get_channel(state["panel_channel_id"])
            if channel is not None:
                try:
                    message = await channel.fetch_message(state["panel_message_id"])
                    count = len(state.get("joined_user_ids") or [])
                    await message.edit(
                        content=_join_counter_text(count),
                        embed=_build_panel_embed(
                            interaction.client.early_access_embed_color,  # type: ignore[attr-defined]
                            interaction.client.early_access_footer_icon,  # type: ignore[attr-defined]
                        ),
                        view=EarlyAccessView(),
                    )
                except discord.HTTPException:
                    pass

        embed = discord.Embed(
            description=f"[Join the private server]({link})",
            color=interaction.client.early_access_embed_color,  # type: ignore[attr-defined]
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class EarlyAccessLinkModal(ui.Modal, title="Early Access Link"):
    server_link = ui.TextInput(
        label="Roblox Private Server Link",
        placeholder="https://www.roblox.com/games/...",
        required=True,
        max_length=500,
    )

    def __init__(self, store: EarlyAccessStore, embed_color: int, footer_icon: str):
        super().__init__(custom_id="early_access:link_modal")
        self.store = store
        self.embed_color = embed_color
        self.footer_icon = footer_icon

    async def on_submit(self, interaction: discord.Interaction):
        link = self.server_link.value.strip()
        if not link.startswith(("http://", "https://")):
            await interaction.response.send_message(
                "Please provide a valid link starting with http:// or https://",
                ephemeral=True,
            )
            return

        state = await self.store.load()
        state["session_active"] = True
        state["server_link"] = link
        state["joined_user_ids"] = []

        embed = _build_panel_embed(self.embed_color, self.footer_icon)
        content = _join_counter_text(0)
        view = EarlyAccessView()

        await interaction.response.defer(ephemeral=True)

        panel_message = None
        if state.get("panel_channel_id") and state.get("panel_message_id"):
            channel = interaction.client.get_channel(state["panel_channel_id"])
            if channel is not None:
                try:
                    panel_message = await channel.fetch_message(state["panel_message_id"])
                    await panel_message.edit(content=content, embed=embed, view=view)
                except discord.HTTPException:
                    panel_message = None

        if panel_message is None:
            panel_message = await interaction.channel.send(
                content=content,
                embed=embed,
                view=view,
            )
            state["panel_channel_id"] = panel_message.channel.id
            state["panel_message_id"] = panel_message.id

        await self.store.save(state)
        await interaction.followup.send(
            "Early access is live. The panel has been posted.",
            ephemeral=True,
        )


def setup(
    bot: discord.ext.commands.Bot,
    embed_color: int,
    footer_icon: str,
    data_dir: str,
    get_convoy_active: Callable[[], bool],
    get_convoy_host: Callable[[], Any],
) -> EarlyAccessStore:
    data_path = os.path.join(data_dir, "early_access.json")
    store = EarlyAccessStore(data_path)

    bot.early_access_store = store  # type: ignore[attr-defined]
    bot.early_access_embed_color = embed_color  # type: ignore[attr-defined]
    bot.early_access_footer_icon = footer_icon  # type: ignore[attr-defined]
    bot.get_convoy_active = get_convoy_active  # type: ignore[attr-defined]
    bot.get_convoy_host = get_convoy_host  # type: ignore[attr-defined]

    @bot.tree.command(
        name="early-access",
        description="Open early access for this session (host only)",
    )
    async def early_access_cmd(interaction: discord.Interaction):
        if not get_convoy_active():
            await interaction.response.send_message(
                "There is no active session. Use `/startup` first.",
                ephemeral=True,
            )
            return

        host = get_convoy_host()
        if host is None or interaction.user.id != host.id:
            await interaction.response.send_message(
                "Only the **session host** can start early access.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(
            EarlyAccessLinkModal(store, embed_color, footer_icon)
        )

    return store


def register_persistent_views(bot: discord.ext.commands.Bot) -> None:
    bot.add_view(EarlyAccessView())


async def reset_on_convoy_end(bot: discord.ext.commands.Bot) -> None:
    store: EarlyAccessStore = bot.early_access_store  # type: ignore[attr-defined]
    await store.reset_session()
