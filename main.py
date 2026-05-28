import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import os
import sys
import json
import asyncio 
import time
import tempfile
import shutil
import aiohttp
import io

blacklist_lock = asyncio.Lock()

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=">", intents=intents)

# ----- Convoy state -----
startup_active = False
startup_host = None
startup_message = None
link_message = None
startup_reactors = set()
startup_time = None
required_reactions = 5
host_setup_sent = False

# ----- IDs & constants -----
NOTIFY_ROLE = 1480656237027660046
WELCOME_CHANNEL = 1471452865796116576
SESSION_LOG_CHANNEL = 1481568871679787088
FEEDBACK_CHANNEL = 1481568923504611439
KILL_ROLE = 1481266824917287124
ALLOWED_ROLES = [1474121009656500225, 1479832999435440178] # <-------- High Rank & Meet Launcher ---------
LOA_ROLE = 1474123995375992873
LOA_CHANNEL = 1485717423448653874
LOA_APPROVE_ROLES = [1474120141380911104, 1474116769458421973]
BLACKLIST_CHANNEL = 1485708172965580851
BLACKLIST_LOG_CHANNEL = 1487028216978739302
BLACKLIST_ROLE = 1474121009656500225
BLACKLIST_PING_ROLE = 1486271938631434363
BLACKLIST_MESSAGE_ID = 1491959706044993576  
GVMC_CONTRIBUTOR_ROLE = 1488794560740986970
GVMC_STATUS_CHANNEL = 1488795010475360347
GVMC_STATUS_TEXT = "/gvrpg"
MODLOG_CHANNEL = 1483351237394042910
DATA_DIR = "/mnt/disk"
BLACKLIST_FILE = f"{DATA_DIR}/blacklist.json"
REGISTRATION_FILE = f"{DATA_DIR}/registrations.json"
LICENSE_SUSPENDED_ROLE = 1492408999826555052
REG_LOG_CHANNEL = 1442212602762760434
# --- Ticket system status monitor ---
STATUS_CHANNEL_ID = 1443980437184577556
STATUS_FILE = f"{DATA_DIR}/ticket_status.json"
STATUS_MESSAGE_TITLE = "Greenville Roleplay Global | Ticket Panel Status"
STATUS_HEARTBEAT_TIMEOUT = 300
last_heartbeat_ts = 0

os.makedirs(os.path.dirname(REGISTRATION_FILE), exist_ok=True)

# Make sure the folder exists
os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)

FOOTER_ICON = "https://i.imgur.com/JaJ24WD.png"
STARTUP_BANNER = "https://i.imgur.com/cpnzBpT.jpeg"
LINK_BANNER = "https://i.imgur.com/5Eo9qNz.jpeg"
END_BANNER = "https://i.imgur.com/FE8kfRq.jpeg"
WELCOME_BANNER = "https://cdn.discordapp.com/attachments/1467783372469178442/1482361429188284606/Welcome_1.png"

EMBED_COLOR=0xEECB69
bot_start_time = datetime.datetime.now(datetime.UTC)

DATA_FILE = "roblox_links.json"

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)


def _load_status_data() -> dict:
    try:
        if not os.path.exists(STATUS_FILE):
            return {}
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_status_data(data: dict) -> None:
    try:
        os.makedirs(os.path.dirname(STATUS_FILE), exist_ok=True)
        with open(STATUS_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Failed to save status data: {e}")


async def _find_existing_status_message(channel: discord.TextChannel):
    if channel is None:
        return None
    try:
        async for msg in channel.history(limit=200):
            if msg.author != bot.user:
                continue
            if isinstance(msg.content, str) and msg.content.startswith("Greenville Roleplay Global | Ticket Panel Status"):
                return msg
    except Exception as e:
        print(f"Error searching status messages: {e}")
    return None


def _format_status_text(panel_exists: bool, ts: int, reason: str | None) -> str:
    text = "Greenville Roleplay Global | Ticket Panel Status\n\n"
    text += "Status:\n"
    if panel_exists:
        text += "🟢 All services running as expected.\n\n"
    else:
        text += "🔴 Services may not be running as expected.\n\n"
    text += f"Last Check: <t:{ts}:R>"
    if not panel_exists:
        text += "\n\n"
        text += f"-# {reason or 'If the last check exceeds 5 minutes, the ticket system may be inoperative.'}"
    return text


async def _ticket_panel_exists() -> bool:
    """Detect whether an active ticket panel exists in any accessible guild channel."""
    for guild in bot.guilds:
        for channel in guild.text_channels:
            try:
                async for msg in channel.history(limit=200):
                    if msg.author != bot.user:
                        continue
                    for row in getattr(msg, "components", []):
                        for comp in getattr(row, "children", []):
                            try:
                                if getattr(comp, "custom_id", None) == "ticket_panel:dropdown:category":
                                    return True
                            except Exception:
                                continue
            except (discord.Forbidden, discord.HTTPException):
                continue
    return False


async def _ensure_status_message():
    """Ensure a single persistent status message exists and return it."""
    channel = bot.get_channel(STATUS_CHANNEL_ID)
    if channel is None:
        print("Status channel not found")
        return None

    status_data = _load_status_data()
    persisted_id = status_data.get("status_message_id")
    if persisted_id:
        try:
            msg = await channel.fetch_message(persisted_id)
            return msg
        except (discord.NotFound, discord.HTTPException):
            pass

    msg = await _find_existing_status_message(channel)
    if msg:
        status_data["status_message_id"] = msg.id
        _save_status_data(status_data)
        return msg

    ts = int(time.time())
    content = _format_status_text(
        panel_exists=False,
        ts=ts,
        reason="The ticket panel could not be detected. The ticket system may currently be inoperative.",
    )

    try:
        new_msg = await channel.send(content)
        status_data.update({
            "status_message_id": new_msg.id,
            "last_heartbeat_ts": ts,
            "operational": False,
        })
        _save_status_data(status_data)
        return new_msg
    except Exception as e:
        print(f"Failed to create status message: {e}")
        return None


async def _update_status_message(status_msg: discord.Message) -> discord.Message | None:
    panel_exists = await _ticket_panel_exists()
    ts = int(time.time())
    reason = None
    operational = False
    if panel_exists:
        operational = True
    else:
        reason = "The ticket panel could not be detected. The ticket system may currently be inoperative."

    content = _format_status_text(panel_exists=panel_exists, ts=ts, reason=reason)

    try:
        await status_msg.edit(content=content)
    except discord.NotFound:
        status_msg = await _ensure_status_message()
        if status_msg is None:
            return None
        await status_msg.edit(content=content)
    except Exception as e:
        print(f"Failed to edit status message: {e}")
        return None

    status_data = {
        "status_message_id": status_msg.id,
        "last_heartbeat_ts": ts,
        "operational": operational,
    }
    _save_status_data(status_data)
    return status_msg


status_monitor_task = None
status_monitor_started = False


async def _start_status_monitor_task():
    global status_monitor_started, status_monitor_task
    if status_monitor_started:
        return
    status_monitor_started = True
    status_monitor_task = asyncio.create_task(_start_ticket_status_monitor())


async def _start_ticket_status_monitor():
    status_msg = await _ensure_status_message()
    if status_msg is None:
        print("Ticket status monitor could not create status message; aborting monitor.")
        return

    while True:
        try:
            status_msg = await _update_status_message(status_msg) or status_msg
        except Exception as e:
            print(f"Ticket status monitor loop error: {e}")
        await asyncio.sleep(60)


@bot.tree.command(name="ticket-status", description="Create or update the ticket panel status message")
async def ticket_status(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True,
        )
        return

    status_msg = await _ensure_status_message()
    if status_msg is None:
        await interaction.response.send_message(
            "Unable to initialize the ticket status message.",
            ephemeral=True,
        )
        return

    status_msg = await _update_status_message(status_msg)
    await _start_status_monitor_task()

    await interaction.response.send_message(
        "Ticket status monitor initialized.",
        ephemeral=True,
    )


def _persisted_status_exists() -> bool:
    data = _load_status_data()
    return bool(data.get("status_message_id"))


async def _maybe_resume_status_monitor():
    if _persisted_status_exists():
        await _start_status_monitor_task()


# -------- EVENTS --------
@bot.event
async def on_ready():

    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")

    except Exception as e:
        print(e)

    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Watching over 'Greenville Roleplay Global'"
        )
    )

    bot.add_view(LOAView(0, 0, 0))
    bot.add_view(EndView())
    bot.add_view(RegistrationView(0))
    bot.add_view(TicketPanelView())
    bot.add_view(GeneralSupportTicketView())
    bot.add_view(PartnershipTicketView())
    bot.add_view(StaffReportTicketView())
    bot.add_view(CivilianReportTicketView())
    early_access.register_persistent_views(bot)

    print(f"{bot.user} ready")
    try:
        await _maybe_resume_status_monitor()
        print("Ticket status monitor resumed if persisted")
    except Exception as e:
        print(f"Failed to resume ticket status monitor: {e}")

@bot.event
async def on_member_join(member):
    # -------- WELCOME MESSAGE --------
    channel = bot.get_channel(WELCOME_CHANNEL)
    if channel:
        embed = discord.Embed(
            title="Welcome to __**Greenville Roleplay Global**__",
            description=(
                "<:yellowheart:1491007395546005514> **Welcome to __Greenville Roleplay Global!__**\n"
                "We are honored to have you here with us! Before you venture off into **GVRPG**, please "
                "**[verify](https://discord.com/channels/1441901639739904125/1471452917163884738)** "
                "to gain full access to our server.\n\n"
                "<:dmsarrow:1491008371682443325> We host daily Roleplays, Events, Occasional Giveaways "
                "and other fun surprises! We look forward to seeing you participate in the full life of "
                "__**Greenville Roleplay Global**__. If you require any form of assistance, please do not "
                "hesitate to contact our Staff Team "
                "**[here](https://discord.com/channels/1441901639739904125/1443980437184577556)**. "
            ),
            color=EMBED_COLOR
        )
        embed.set_footer(text="Greenville Roleplay Global", icon_url=FOOTER_ICON)
        await channel.send(content=member.mention, embed=embed)

    # -------- MODLOG JOIN --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        account_created = member.created_at
        account_age_days = (discord.utils.utcnow() - account_created).days

        log_embed = discord.Embed(
            description=f"**Member Joined**\n{member.mention} has joined the server",
            color=EMBED_COLOR
        )
        log_embed.add_field(name="User ID", value=member.id)
        log_embed.add_field(
            name="Account Created",
            value=f"<t:{int(account_created.timestamp())}:F>",
            inline=False
        )
        log_embed.add_field(
            name="Account Age",
            value=f"{account_age_days} days",
            inline=False
        )
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.timestamp = discord.utils.utcnow()

        await log_channel.send(embed=log_embed)

@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        account_created = member.created_at
        account_age_days = (discord.utils.utcnow() - account_created).days

        log_embed = discord.Embed(
            description=f"**Member Left**\n{member.mention} has left the server",
            color=EMBED_COLOR
        )
        log_embed.add_field(name="User ID", value=member.id)
        log_embed.add_field(name="Account Created", value=f"<t:{int(account_created.timestamp())}:F>", inline=False)
        log_embed.add_field(name="Account Age", value=f"{account_age_days} days", inline=False)
        log_embed.set_thumbnail(url=member.display_avatar.url)
        log_embed.timestamp = discord.utils.utcnow()
        await log_channel.send(embed=log_embed)

@bot.event
async def on_member_update(before, after):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if not log_channel:
        return

    # Check for role changes
    added_roles = [role for role in after.roles if role not in before.roles]
    removed_roles = [role for role in before.roles if role not in after.roles]

    # Roles Added
    if added_roles:
        executor = None
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id == after.id and entry.created_at > (discord.utils.utcnow() - datetime.timedelta(seconds=5)):
                executor = entry.user
                break

        embed = discord.Embed(
            title="Member Roles Updated",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.add_field(name="**Executor**", value=executor.mention if executor else "Unknown", inline=True)
        embed.add_field(name="**Target**", value=after.mention, inline=True)
        embed.add_field(name="**Time**", value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>", inline=False)

        roles_added_text = "\n".join(f"<:Checkmark:1490181125325193369> | {role.mention}" for role in added_roles)
        embed.add_field(name="**Roles Added**", value=roles_added_text, inline=False)

        await log_channel.send(embed=embed)

    # Roles Removed
    if removed_roles:
        executor = None
        async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.member_role_update):
            if entry.target.id == after.id and entry.created_at > (discord.utils.utcnow() - datetime.timedelta(seconds=5)):
                executor = entry.user
                break

        embed = discord.Embed(
            title="Member Roles Updated",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.add_field(name="**Executor**", value=executor.mention if executor else "Unknown", inline=True)
        embed.add_field(name="**Target**", value=after.mention, inline=True)
        embed.add_field(name="**Time**", value=f"<t:{int(discord.utils.utcnow().timestamp())}:F>", inline=False)

        roles_removed_text = "\n".join(f"<:crossmark:1490180947507675367> | {role.mention}" for role in removed_roles)
        embed.add_field(name="**Roles Removed**", value=roles_removed_text, inline=False)

        await log_channel.send(embed=embed)

@bot.event
async def on_guild_channel_update(before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if not log_channel:
        return

    changes_detected = []

    for target in after.overwrites:
        before_perm = before.overwrites.get(target)
        after_perm = after.overwrites.get(target)

        if before_perm != after_perm:
            for perm_name in discord.Permissions.VALID_FLAGS:
                before_value = getattr(before_perm, perm_name, None) if before_perm else None
                after_value = getattr(after_perm, perm_name, None) if after_perm else None
                if before_value != after_value:
                    # Emoji representation
                    def perm_emoji(val):
                        if val is True:
                            return "<:Checkmark:1490181125325193369>"
                        elif val is False:
                            return "<:crossmark:1490180947507675367>"
                        else:
                            return "<:slash:1490874469848449195>"

                    changes_detected.append(
                        f"**{perm_name.replace('_', ' ').title()}:** {perm_emoji(before_value)} **-->** {perm_emoji(after_value)}"
                    )

            if changes_detected:
                embed = discord.Embed(
                    title="Changes below:",
                    color=EMBED_COLOR,
                    timestamp=discord.utils.utcnow()
                )

                # Small circle next to title, can be optional emoji or None
                embed.set_author(
                    name="Channel Permission Updated",
                    icon_url=None  # OR put a small icon URL here
                )

                embed.add_field(name="**Channel**", value=after.mention, inline=True)
                embed.add_field(name="**Executor**", value="Unknown", inline=True)
                embed.add_field(name="**Target**", value=target.mention if isinstance(target, (discord.Member, discord.Role)) else str(target), inline=True)
                embed.add_field(name="**Permission**", value="\n".join(changes_detected), inline=False)

                # Human-readable footer
                embed.set_footer(
                    text=f"Channel ID: {after.id} | {discord.utils.format_dt(datetime.datetime.now(datetime.UTC), style='F')}"
                )

                # Try to get executor from audit logs
                try:
                    async for entry in after.guild.audit_logs(limit=5, action=discord.AuditLogAction.overwrite_update):
                        if entry.target.id == after.id:
                            embed.set_field_at(1, name="**Executor**", value=entry.user.mention, inline=True)
                            break
                except:
                    pass

                await log_channel.send(embed=embed)
                changes_detected.clear()
        
# ------- PARTNERSHIP EMBED --------
@bot.event
async def on_message(message):
    if message.author.bot:
        return

    if message.channel.id == 1480243298294694200:
        embed = discord.Embed(
            description=(
                "### Tired of Pings?\n"
                "> <:dot:1491005539201843290> Sick of being pinged? Simply mute this channel in settings to prevent further notifications. There is nothing we can do on our end.\n\n"
                "> <:dmsarrow:1491008371682443325> Interested in partnering with us? Please open a **[partnership ticket](https://discord.com/channels/1441901639739904125/1443980437184577556)** today. Ensure you have reviewed our **[blacklisted servers](https://discord.com/channels/1441901639739904125/1485708172965580851)** before proceeding."
            ),
            color=EMBED_COLOR
        )

        await message.channel.send(embed=embed)

    await bot.process_commands(message)
    
# -------- MODLOG MESSAGE DELETE --------
@bot.event
async def on_message_delete(message):
    if message.author.bot:
        return  # ignore bot messages

    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if not log_channel:
        return

    # Build horizontal embed
    embed = discord.Embed(
        description=f"**Message from {message.author.mention} was deleted in {message.channel.mention}.**\n"
                    f"It was sent on | <t:{int(message.created_at.timestamp())}:F>",
        color=EMBED_COLOR
    )
    embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)  # PFP + username
    embed.add_field(name="Message Content", value=message.content or "*(Embed/Attachment/Empty Message)*", inline=False)
    embed.timestamp = discord.utils.utcnow()

    await log_channel.send(embed=embed)
# -------- MODLOG MESSAGE EDIT --------
@bot.event
async def on_message_edit(before, after):
    if before.author.bot:
        return  # ignore bot edits

    if before.content == after.content:
        return  # ignore edits that don’t change text

    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if not log_channel:
        return

    embed = discord.Embed(
        description=f"**Message from {before.author.mention} edited in {before.channel.mention}.**\n"
                    f"[**Jump to Message**]({after.jump_url})",
        color=EMBED_COLOR
    )
    embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
    embed.add_field(name="Before", value=before.content or "*(Empty Message)*", inline=False)
    embed.add_field(name="After", value=after.content or "*(Empty Message)*", inline=False)
    embed.timestamp = discord.utils.utcnow()

    await log_channel.send(embed=embed)
        
@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    try:
        role = after.guild.get_role(GVMC_CONTRIBUTOR_ROLE)
        channel = bot.get_channel(GVMC_STATUS_CHANNEL)

        if role is None or channel is None:
            return

        before_status = None
        after_status = None

        # Get custom status BEFORE change
        for activity in (before.activities or []):
            if isinstance(activity, discord.CustomActivity):
                before_status = activity.name

        # Get custom status AFTER change
        for activity in (after.activities or []):
            if isinstance(activity, discord.CustomActivity):
                after_status = activity.name

        # ---- USER ADDED /GVMC ----
        if after_status and GVMC_STATUS_TEXT.lower() in after_status.lower():
            if role not in after.roles:
                await after.add_roles(role)

                embed = discord.Embed(
                    title="Greenville Roleplay Global | Server Contributor",
                    description=(
                        f"> <:yellowheart:1491007395546005514> | Thank you {after.mention} for becoming an official **Greenville Roleplay Global** contributor!\n"
                        f"> They have received the <@&{GVMC_CONTRIBUTOR_ROLE}> role which contains benefits such as image permissions and exclusive giveaways!\n\n"
                        f"> <:dmsarrow:1491008371682443325> Would you like to receive the <@&{GVMC_CONTRIBUTOR_ROLE}> role?\n"
                        "> Please put ``/gvrpg`` as your status and you will receive all the perks & role."
                    ),
                    color=EMBED_COLOR
                )

                embed.set_footer(
                    text="Greenville Roleplay Global",
                    icon_url=FOOTER_ICON
                )

                await channel.send(embed=embed)

        # ---- USER REMOVED /GVMC ----
        if before_status and GVMC_STATUS_TEXT.lower() in before_status.lower():
            if (not after_status) or (GVMC_STATUS_TEXT.lower() not in after_status.lower()):
                if role in after.roles:
                    await after.remove_roles(role)

    except Exception as e:
        print(f"GVMC status error: {e}")
# -------- /SAY COMMAND WITH RIGHT-ALIGNED MODLOG --------
@bot.tree.command(name="say", description="Say something as the bot")
@app_commands.describe(content="Content to send")
async def say(interaction: discord.Interaction, content: str):
    # Step 1: Respond ephemerally to bypass the default slash command header
    await interaction.response.send_message("> Message sent!", ephemeral=True)

    # Step 2: Send the actual message as the bot in the channel
    await interaction.channel.send(content)

    # -------- MODLOG --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )

        # Single field with "label | value" format
        embed.add_field(
            name="\u200b",  # blank field name
            value=(
                f"**Command Executed** | /say\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Content** | {content}\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}"
            ),
            inline=False
        )

        # PFP + username at the top
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        await log_channel.send(embed=embed)

# -------- REACTION TRACKING --------
host_setup_sent = False  # ONLY flag used

@bot.event
async def on_raw_reaction_add(payload):
    global startup_reactors, host_setup_sent

    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:Checkmark:1490181125325193369>":
            startup_reactors.add(payload.user_id)

            # ONLY host + ONLY once
            if startup_host and payload.user_id == startup_host.id and not host_setup_sent:
                channel = bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)

                embed = discord.Embed(
                    title="Event Setup",
                    description=(
                        "> The host is currently setting up the Event. Please remain patient as they get everything ready. "
                        "Ensure you have set all your privacy settings set to __**everyone**__.\n\n"
                        "> During this time, we recommend that you look over our "
                        "**[Event Guidelines](https://discord.com/channels/1441901639739904125/1481562585781239969)**. "
                        "After this step is completed, the host will release the link. "
                        "You will be pinged again if you have the **Convoy Ping** role."
                    ),
                    color=EMBED_COLOR
                )

                await message.reply(embed=embed)

                # LOCK IT FOREVER FOR THIS CONVOY
                host_setup_sent = True
@bot.event
async def on_raw_reaction_remove(payload):
    global startup_reactors

    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:Checkmark:1490181125325193369>":
            startup_reactors.discard(payload.user_id)

# -------- BLACKLIST STORAGE --------
async def load_blacklist():
    async with blacklist_lock:
        if not os.path.exists(BLACKLIST_FILE):
            with open(BLACKLIST_FILE, "w") as f:
                json.dump([], f)
            return []

        try:
            with open(BLACKLIST_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            backup_path = BLACKLIST_FILE + ".corrupt"
            shutil.copy(BLACKLIST_FILE, backup_path)

            with open(BLACKLIST_FILE, "w") as f:
                json.dump([], f)

            print(f"Blacklist corrupted. Backup saved to {backup_path}")
            return []


async def save_blacklist(data):
    async with blacklist_lock:
        dir_name = os.path.dirname(BLACKLIST_FILE)

        with tempfile.NamedTemporaryFile("w", delete=False, dir=dir_name) as tmp:
            json.dump(data, tmp, indent=4)
            temp_name = tmp.name

        os.replace(temp_name, BLACKLIST_FILE)


# -------- REGISTRATION STORAGE --------
async def load_registrations():
    if not os.path.exists(REGISTRATION_FILE):
        with open(REGISTRATION_FILE, "w") as f:
            json.dump({}, f)
        return {}

    with open(REGISTRATION_FILE, "r") as f:
        return json.load(f)


async def save_registrations(data):
    with tempfile.NamedTemporaryFile("w", delete=False, dir=DATA_DIR) as tmp:
        json.dump(data, tmp, indent=4)
        temp_name = tmp.name

    os.replace(temp_name, REGISTRATION_FILE)
    
# -------- UPDATE BLACKLIST MESSAGE --------
async def update_blacklist_message(bot):
    channel = bot.get_channel(BLACKLIST_CHANNEL)
    if channel is None:
        return

    data = await load_blacklist()

    description = (
        "All servers below are blacklisted from all **Greenville Roleplay Global** fast-passing, partnerships and any other affiliations. "
        "For proof of a specific blacklist or appeal a blacklist, please open a "
        "**[support ticket](https://discord.com/channels/1441901639739904125/1443980437184577556)** today "
        "and a member of the **High Ranking** Team will provide assistance.\n\n"
    )

    for i, entry in enumerate(data, start=1):
        description += (
            f"**{entry['server_name']}**\n"
            f"**Server ID** | {entry['server_id']}\n"
            f"**Reason for Blacklist** | {entry['reason']}\n"
            f"**Additional Notes** | {entry['notes']}\n"
            f"**Blacklist Number** | {i}\n\n"
        )

    embed = discord.Embed(
        title="Blacklisted Servers",
        description=description,
        color=EMBED_COLOR
    )

    message = await channel.fetch_message(BLACKLIST_MESSAGE_ID)
    await message.edit(embed=embed)

async def get_roblox_data(discord_id: int, guild_id: int):
    urls = [
        f"https://api.blox.link/v4/public/guilds/{guild_id}/discord-to-roblox/{discord_id}",
        f"https://api.blox.link/v4/public/discord-to-roblox/{discord_id}"
    ]

    async with aiohttp.ClientSession() as session:
        for url in urls:
            try:
                async with session.get(url, timeout=10) as resp:
                    print(f"[BLOXLINK] {resp.status} -> {url}")

                    if resp.status != 200:
                        continue

                    data = await resp.json()
                    print("[BLOXLINK RAW]", data)

                    roblox_id = None

                    if isinstance(data, dict):
                        roblox_id = (
                            data.get("robloxId")
                            or data.get("robloxID")
                            or data.get("userId")
                            or data.get("id")
                            or (data.get("user", {}).get("robloxId")
                                if isinstance(data.get("user"), dict)
                                else None)
                        )

                    if roblox_id:
                        try:
                            return int(roblox_id)
                        except:
                            return None

            except Exception as e:
                print("[BLOXLINK ERROR]", e)

    return None
            
# -------- STARTUP COMMAND --------
@bot.tree.command(name="startup", description="Start a convoy session.")
@app_commands.describe(reactions="Number of reactions required to release link")
async def startup(interaction: discord.Interaction, reactions: int):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    global startup_active, startup_host, startup_message, startup_reactors, startup_time, required_reactions, host_setup_sent

    if startup_active:
        await interaction.response.send_message("A convoy session is already active.", ephemeral=True)
        return

    required_reactions = reactions
    startup_active = True
    startup_host = member
    startup_reactors = set()
    startup_time = datetime.datetime.now(datetime.UTC)
    host_setup_sent = False

    # -------- MAIN EMBED --------
    embed = discord.Embed(
        title="<:GVMC_trophy:1480637860590911610> Greenville Roleplay Global Event Startup <:GVMC_trophy:1480637860590911610>",
        description=(
            f"<a:Animated_Arrow_Bluelite:1484055930919190589> | An Event is currently being started by {member.mention}. "
            "Before reacting, please ensure you have read all of our "
            "**[guidelines](https://discord.com/channels/1441901639739904125/1481562585781239969)** "
            "to ensure a smooth event for everyone. To confirm your presence, please react with the <:Checkmark:1490181125325193369> below. "
            "We also ask that you have your privacy settings set to __**everyone**__ to ensure a trouble free event.\n\n"
            f"**Information**\n"
            f"<:dot:1491005539201843290> | The host has requested __**{required_reactions}**__ reactions. "
            "Once we reach the reaction count, the link will be released within this channel.\n"
            "<:dot:1491005539201843290> | Affected by **Roblox Chat Restriction**? Feel free to communicate with others or the host in our "
            "**[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**\n\n"
            "<a:pulsatingheart:1480637910347940064> | Please wait for the **session release**. "
            "You will be notified within this channel when it has been **released**."
        ),
        color=EMBED_COLOR
    )
    embed.set_image(url=STARTUP_BANNER)
    embed.set_footer(text="Greenville Roleplay Global", icon_url=FOOTER_ICON)

    await interaction.response.send_message("Convoy started!", ephemeral=True)

    startup_message = await interaction.channel.send(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    await startup_message.add_reaction("<:Checkmark:1490181125325193369>")

    # -------- MODLOG --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        log_embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )

        # PFP + username at top
        log_embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        # Horizontal info
        log_embed.add_field(
            name="\u200b",
            value=(
                f"**Command Executed** | /startup\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Content** | {reactions} reactions requested\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}"
            ),
            inline=False
        )

        await log_channel.send(embed=log_embed)

@bot.tree.command(name="blacklist", description="Blacklist a server")
@app_commands.describe(
    server_name="<a:Animated_Arrow_Bluelite:1484055930919190589> Server Name",
    server_id="<:dot:1480643720687915058> Server ID",
    reason="<:dot:1480643720687915058> Reason",
    notes="<:dot:1480643720687915058> Additional Notes"
)
async def blacklist(interaction: discord.Interaction, server_name: str, server_id: str, reason: str, notes: str):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    data = await load_blacklist()

    data.append({
        "server_name": server_name,
        "server_id": server_id,
        "reason": reason,
        "notes": notes
    })

    await save_blacklist(data)
    await update_blacklist_message(bot)

    # LOG EMBED
    log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL)

    embed = discord.Embed(
        title="Blacklist Added",
        description=(
            f"Added by: {interaction.user.mention}\n\n"
            f"**{server_name}**\n"
            f"Server ID: {server_id}\n"
            f"Reason: {reason}\n"
            f"Notes: {notes}"
        ),
        color=EMBED_COLOR
    )

    await log_channel.send(embed=embed)

    await interaction.response.send_message("Blacklist added.", ephemeral=True)

# -------- DELETE BLACKLIST --------
@bot.tree.command(name="delblacklist", description="Delete a blacklist entry")
@app_commands.describe(number="Blacklist Number")
async def delblacklist(interaction: discord.Interaction, number: int):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    data = await load_blacklist()

    if number < 1 or number > len(data):
        await interaction.response.send_message("Invalid blacklist number.", ephemeral=True)
        return

    removed = data.pop(number - 1)
    await save_blacklist(data)

    await update_blacklist_message(bot)

    log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL)

    embed = discord.Embed(
        title="Blacklist Removed",
        description=(
            f"Deleted by: {interaction.user.mention}\n"
            f"Blacklist Number: {number}\n\n"
            f"**{removed['server_name']}**\n"
            f"Server ID: {removed['server_id']}\n"
            f"Reason: {removed['reason']}\n"
            f"Notes: {removed['notes']}"
        ),
        color=EMBED_COLOR
    )

    await log_channel.send(f"<@&{BLACKLIST_PING_ROLE}>", embed=embed)
    await interaction.response.send_message("Blacklist removed.", ephemeral=True)

#--------- Plate Finder Command ---------
@bot.tree.command(name="platefinder", description="Find a registered vehicle by plate")
@app_commands.describe(plate="License plate to search for")
async def platefinder(interaction: discord.Interaction, plate: str):
    await interaction.response.defer()

    data = await load_registrations()
    plate_search = plate.strip().lower()

    matches = []

    # -------- SEARCH ALL REGISTRATIONS --------
    for user_id, registrations in data.items():
        for reg in registrations:
            reg_plate = str(reg.get("plate", "")).strip().lower()

            if reg_plate == plate_search:
                matches.append((int(user_id), reg))

    # -------- NOT FOUND --------
    if not matches:
        embed = discord.Embed(
            description=(
                f"The License plate ({plate}) could not be found on an actively registered vehicle.\n"
                "Please ensure the vehicle is registered under the **GVRPG** bot."
            ),
            color=EMBED_COLOR
        )
        await interaction.followup.send(embed=embed)
        return

    # -------- MULTIPLE MATCHES CHECK --------
    suspicious = len(matches) > 1

    embed = discord.Embed(
        title="Plate Lookup Result",
        color=EMBED_COLOR
    )

    # -------- BUILD RESULTS --------
    for i, (owner_id, reg) in enumerate(matches, start=1):
        member = interaction.guild.get_member(owner_id)
        owner_mention = member.mention if member else f"<@{owner_id}>"

        timestamp = reg.get("timestamp")
        time_text = f"<t:{timestamp}:F>" if timestamp else "Unknown"

        embed.add_field(
            name=f"Match #{i}",
            value=(
                f"__**Vehicle Owner**__ | {owner_mention}\n"
                f"**Brand** | {reg.get('brand', 'N/A')}\n"
                f"**Model** | {reg.get('model', 'N/A')}\n"
                f"**Color** | {reg.get('color', 'N/A')}\n"
                f"**Year** | {reg.get('year', 'N/A')}\n"
                f"**Registered On** | {time_text}"
            ),
            inline=False
        )

    # -------- SUSPICIOUS WARNING --------
    if suspicious:
        embed.description = (
            "⚠️ **MULTIPLE VEHICLES FOUND WITH SAME PLATE**\n"
            "This plate may be duplicated or fraudulently registered."
        )

    embed.set_footer(text="GVRPG Vehicle Database")

    await interaction.followup.send(embed=embed)

# -------- BLACKLIST START COMMAND --------
@bot.tree.command(name="setupblacklist", description="Setup blacklist message")
async def setupblacklist(interaction: discord.Interaction):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return

    channel = bot.get_channel(BLACKLIST_CHANNEL)

    embed = discord.Embed(
        title="Blacklisted Servers",
        description=(
            "All servers below are blacklisted from all **Greenville Roleplay Global** fast-passing, partnerships and any other affiliations. "
            "For proof of a specific blacklist or appeal a blacklist, please open a support ticket.\n\n"
            "No blacklisted servers."
        ),
        color=EMBED_COLOR
    )

    msg = await channel.send(embed=embed)

    await interaction.response.send_message(
        f"Blacklist message created. Message ID: {msg.id}",
        ephemeral=True
    )

# -------- TICKET CLOSE (shared) --------
TICKET_CLOSE_STAFF_ROLE_ID = 1474123995375992873


def get_ticket_opener(channel: discord.TextChannel):
    for target, overwrite in channel.overwrites.items():
        if isinstance(target, discord.Member) and overwrite.view_channel is True:
            return target
    return None


def can_close_ticket(interaction: discord.Interaction) -> bool:
    if interaction.guild is None or not isinstance(interaction.channel, discord.TextChannel):
        return False
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    if any(role.id == TICKET_CLOSE_STAFF_ROLE_ID for role in member.roles):
        return True
    opener = get_ticket_opener(interaction.channel)
    return opener is not None and opener.id == member.id


async def build_ticket_transcript(channel: discord.TextChannel) -> str:
    lines = []
    async for message in channel.history(limit=None, oldest_first=True):
        content = message.content
        if not content:
            if message.attachments:
                content = "[Attachment]"
            elif message.embeds:
                content = "[Embed]"
            else:
                content = ""
        timestamp = message.created_at.strftime("%Y-%m-%d %H:%M:%S")
        username = message.author.display_name if message.author else "Unknown"
        lines.append(f"[{timestamp}] {username}: {content}")
    return "\n".join(lines) if lines else "(No messages)"


async def handle_ticket_close_request(interaction: discord.Interaction):
    if not can_close_ticket(interaction):
        await interaction.response.send_message(
            "You do not have permission to close this ticket.",
            ephemeral=True,
        )
        return

    embed = discord.Embed(
        title="Close Ticket",
        description="Are you sure you want to close this ticket?",
        color=EMBED_COLOR,
    )
    await interaction.response.send_message(
        embed=embed,
        view=TicketConfirmCloseView(),
        ephemeral=True,
    )


class TicketConfirmCloseView(ui.View):
    def __init__(self):
        super().__init__(timeout=120)

    @ui.button(label="Confirm Close", style=discord.ButtonStyle.danger)
    async def confirm_close(self, interaction: discord.Interaction, button: ui.Button):
        if not can_close_ticket(interaction):
            await interaction.response.send_message(
                "You do not have permission to close this ticket.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        if not isinstance(channel, discord.TextChannel):
            await interaction.response.send_message(
                "This can only be used in a ticket channel.",
                ephemeral=True,
            )
            return

        await interaction.response.defer()

        closer = interaction.user
        opener = get_ticket_opener(channel)

        await channel.send("> Ticket closing in 3 seconds - generating transcript")
        await asyncio.sleep(3)

        transcript = await build_ticket_transcript(channel)
        filename = f"{channel.name}-transcript.txt"

        if opener is not None:
            try:
                transcript_file = discord.File(
                    io.BytesIO(transcript.encode("utf-8")),
                    filename=filename,
                )
                await opener.send(
                    f"Your ticket `{channel.name}` was closed by {closer.display_name}. Transcript is attached.",
                    file=transcript_file,
                )
            except discord.HTTPException:
                pass

        await channel.delete(reason=f"Ticket closed by {closer} ({closer.id})")


@bot.tree.command(name="add", description="Add a member to this ticket")
@app_commands.describe(user="The member to add to the ticket")
async def add(interaction: discord.Interaction, user: discord.Member):
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or not any(role.id == TICKET_CLOSE_STAFF_ROLE_ID for role in member.roles):
        await interaction.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or channel.category_id != 1443979964482584688:
        await interaction.response.send_message(
            "This command can only be used in ticket channels.",
            ephemeral=True,
        )
        return

    await channel.set_permissions(
        user,
        overwrite=discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            read_message_history=True,
        ),
        reason=f"Added to ticket by {interaction.user} ({interaction.user.id})",
    )

    await interaction.response.send_message(
        f"> {interaction.user.mention} has added {user.mention} to this ticket. "
        "Please run `/remove` if you would like to remove them."
    )


@bot.tree.command(name="remove", description="Remove a member from this ticket")
@app_commands.describe(user="The member to remove from the ticket")
async def remove(interaction: discord.Interaction, user: discord.Member):
    member = interaction.guild.get_member(interaction.user.id)
    if member is None or not any(role.id == TICKET_CLOSE_STAFF_ROLE_ID for role in member.roles):
        await interaction.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True,
        )
        return

    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel) or channel.category_id != 1443979964482584688:
        await interaction.response.send_message(
            "This command can only be used in ticket channels.",
            ephemeral=True,
        )
        return

    await channel.set_permissions(
        user,
        overwrite=discord.PermissionOverwrite(
            view_channel=False,
            send_messages=False,
            read_message_history=False,
        ),
        reason=f"Removed from ticket by {interaction.user} ({interaction.user.id})",
    )

    await interaction.response.send_message(
        f"> {interaction.user.mention} has removed {user.mention} from this ticket."
    )


# -------- TICKET PANEL --------
class GeneralSupportTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:general_support:close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await handle_ticket_close_request(interaction)


class PartnershipTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:partnership_request:close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await handle_ticket_close_request(interaction)


class StaffReportTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:staff_report:close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await handle_ticket_close_request(interaction)


class GeneralSupportModal(ui.Modal, title="General Support"):
    reason = ui.TextInput(
        label="What is the reason for this ticket?",
        custom_id="ticket_modal:general_support:reason",
        style=discord.TextStyle.paragraph,
        placeholder="Type reason here...",
        required=True
    )
    additional_details = ui.TextInput(
        label="Additional Details",
        custom_id="ticket_modal:general_support:additional_details",
        style=discord.TextStyle.paragraph,
        placeholder="Type additional details here...",
        required=False
    )

    def __init__(self):
        super().__init__(custom_id="ticket_modal:general_support")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This can only be used in a server.", ephemeral=True)
            return

        category = guild.get_channel(1443979964482584688)
        support_role = guild.get_role(1474123995375992873)
        member = guild.get_member(interaction.user.id)

        if category is None or support_role is None or member is None:
            await interaction.followup.send("Unable to create ticket. Please contact staff.", ephemeral=True)
            return

        channel_name = f"support-{interaction.user.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"General Support ticket created by {interaction.user} ({interaction.user.id})"
        )

        additional_details = self.additional_details.value.strip() or "None provided"
        embed = discord.Embed(
            title="**Welcome to General Support**",
            description=(
                "<:dasharrow:1496224193531084852> Welcome to the **General Support Ticket**. Please await a member of the **Global staff team** to assist you. You may use this ticket for **giveaway claims, general questions, server-wide issues and appeals**. We kindly ask that you refrain from pinging **staff members** and wait patiently.\n\n"
                "> <:dmsarrow:1491008371682443325> If you have not received a response within **72 hours**, please close this ticket and open a new one.\n\n"
                f"**User:** {member.mention}\n"
                f"**Assistance Requested:** {self.reason.value}\n"
                f"**Additional Information:** {additional_details}"
            ),
            color=0xEECB69
        )

        await ticket_channel.send(
            content=f"{member.mention} <@&1474123995375992873>",
            embed=embed,
            view=GeneralSupportTicketView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True)
        )
        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


class PartnershipRequestModal(ui.Modal, title="Partnership Request"):
    server_name = ui.TextInput(
        label="Server Name",
        custom_id="ticket_modal:partnership_request:server_name",
        placeholder="Type server name here...",
        required=True
    )
    server_membercount = ui.TextInput(
        label="Server Membercount",
        custom_id="ticket_modal:partnership_request:server_membercount",
        placeholder="Type server membercount here...",
        required=True
    )
    requirements_agreement = ui.TextInput(
        label="Do you agree to our requirements?",
        custom_id="ticket_modal:partnership_request:requirements_agreement",
        placeholder="Type Yes or No",
        required=True
    )

    def __init__(self):
        super().__init__(custom_id="ticket_modal:partnership_request")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This can only be used in a server.", ephemeral=True)
            return

        category = guild.get_channel(1443979964482584688)
        support_role = guild.get_role(1474123995375992873)
        member = guild.get_member(interaction.user.id)

        if category is None or support_role is None or member is None:
            await interaction.followup.send("Unable to create ticket. Please contact staff.", ephemeral=True)
            return

        channel_name = f"partnership-{interaction.user.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Partnership Request ticket created by {interaction.user} ({interaction.user.id})"
        )

        embed = discord.Embed(
            title="****Welcome to Partnership Requests****",
            description=(
                "<:dasharrow:1496224193531084852> Welcome to the **Partnership Request Ticket**. Please await a member of the **Global staff team** to assist you. You may use this ticket solely for **partnership requests**. We kindly ask that you refrain from pinging **staff members** and wait patiently.\n\n"
                "> <:dmsarrow:1491008371682443325> If you have not received a response within **72 hours**, please close this ticket and open a new one.\n\n"
                f"**User:** {member.mention}\n"
                f"**Server Name:** {self.server_name.value}\n"
                f"**Server Membercount:** {self.server_membercount.value}\n"
                f"**Agreeance to requirements:** {self.requirements_agreement.value}"
            ),
            color=0xEECB69
        )

        await ticket_channel.send(
            content=f"{member.mention} <@&1486271938631434363>",
            embed=embed,
            view=PartnershipTicketView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True)
        )
        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


class StaffReportModal(ui.Modal, title="Staff Report"):
    staff_members = ui.TextInput(
        label="Staff Member(s)",
        custom_id="ticket_modal:staff_report:staff_members",
        style=discord.TextStyle.paragraph,
        placeholder="Type the username(s) of the staff member(s) being reported...",
        required=True
    )
    additional_information = ui.TextInput(
        label="Additional Information",
        custom_id="ticket_modal:staff_report:additional_information",
        style=discord.TextStyle.paragraph,
        placeholder="Type additional information here...",
        required=False
    )

    def __init__(self):
        super().__init__(custom_id="ticket_modal:staff_report")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This can only be used in a server.", ephemeral=True)
            return

        category = guild.get_channel(1443979964482584688)
        high_rank_role = guild.get_role(1474121009656500225)
        member = guild.get_member(interaction.user.id)

        if category is None or high_rank_role is None or member is None:
            await interaction.followup.send("Unable to create ticket. Please contact staff.", ephemeral=True)
            return

        channel_name = f"staffreport-{interaction.user.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            high_rank_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Staff Report ticket created by {interaction.user} ({interaction.user.id})"
        )

        additional_information = self.additional_information.value.strip() or "None provided"
        embed = discord.Embed(
            title="****Welcome to Staff Report****",
            description=(
                "<:dasharrow:1496224193531084852> Welcome to the **Staff Report Ticket**. Please await a member of the **Global High Ranking Team** to assist you. You may use this ticket solely for **reporting staff members**. We kindly ask that you refrain from pinging **High Ranking members** and wait patiently. During this time, please explain **in detail** the situation and any valid proof.\n\n"
                "> <:dmsarrow:1491008371682443325> If you have not received a response within **72 hours**, please close this ticket and open a new one.\n\n"
                f"**User:** {member.mention}\n"
                f"**Reporting Member(s):** {self.staff_members.value}\n"
                f"**Additional Information:** {additional_information}"
            ),
            color=0xEECB69
        )

        await ticket_channel.send(
            content=f"{member.mention} <@&1474121009656500225>",
            embed=embed,
            view=StaffReportTicketView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True)
        )
        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


class CivilianReportTicketView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Close",
        style=discord.ButtonStyle.danger,
        custom_id="ticket:civilian_report:close"
    )
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        await handle_ticket_close_request(interaction)


class CivilianReportModal(ui.Modal, title="Civilian Report"):
    civilian_members = ui.TextInput(
        label="Civilian Member(s)",
        custom_id="ticket_modal:civilian_report:civilian_members",
        style=discord.TextStyle.paragraph,
        placeholder="Type the username(s) of the civilian(s) being reported...",
        required=True
    )
    additional_information = ui.TextInput(
        label="Additional Information",
        custom_id="ticket_modal:civilian_report:additional_information",
        style=discord.TextStyle.paragraph,
        placeholder="Type any additional information here...",
        required=False
    )

    def __init__(self):
        super().__init__(custom_id="ticket_modal:civilian_report")

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("This can only be used in a server.", ephemeral=True)
            return

        category = guild.get_channel(1443979964482584688)
        support_role = guild.get_role(1474123995375992873)
        member = guild.get_member(interaction.user.id)

        if category is None or support_role is None or member is None:
            await interaction.followup.send("Unable to create ticket. Please contact staff.", ephemeral=True)
            return

        channel_name = f"civilianreport-{interaction.user.name}".lower()
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            ),
            support_role: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                read_message_history=True
            )
        }

        ticket_channel = await guild.create_text_channel(
            channel_name,
            category=category,
            overwrites=overwrites,
            reason=f"Civilian Report ticket created by {interaction.user} ({interaction.user.id})"
        )

        additional_information = self.additional_information.value.strip() or "None provided"
        embed = discord.Embed(
            title="****Welcome to Civilian Report****",
            description=(
                "<:dasharrow:1496224193531084852> Welcome to the **Civilian Report Ticket**. Please await a member of the **Global Staff Team** to assist you. You may use this ticket solely for **reporting civilian(s)**. We kindly ask that you refrain from pinging staff members and wait patiently. During this time, please explain **in detail** the situation and any valid proof.\n\n"
                "> <:dmsarrow:1491008371682443325> If you have not received a response within **72 hours**, please close this ticket and open a new one.\n\n"
                f"**User:** {member.mention}\n"
                f"**Reporting Member(s):** {self.civilian_members.value}\n"
                f"**Additional Information:** {additional_information}"
            ),
            color=0xEECB69
        )

        await ticket_channel.send(
            content=f"{member.mention} <@&1474123995375992873>",
            embed=embed,
            view=CivilianReportTicketView(),
            allowed_mentions=discord.AllowedMentions(users=True, roles=True)
        )
        await interaction.followup.send(f"Ticket created: {ticket_channel.mention}", ephemeral=True)


class TicketPanelView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.select(
        placeholder="Select a support option...",
        min_values=1,
        max_values=1,
        custom_id="ticket_panel:dropdown:category",
        options=[
            discord.SelectOption(
                label="General Support",
                emoji=discord.PartialEmoji.from_str("<:1_:1497905729305186375>")
            ),
            discord.SelectOption(
                label="Partnership Request",
                emoji=discord.PartialEmoji.from_str("<:2_:1497905850596069497>")
            ),
            discord.SelectOption(
                label="Staff Report",
                emoji=discord.PartialEmoji.from_str("<:3_:1497905775979270224>")
            ),
            discord.SelectOption(
                label="Civilian Report",
                emoji=discord.PartialEmoji.from_str("<:4_:1497905846368075936>")
            )
        ]
    )
    async def select_ticket_type(self, interaction: discord.Interaction, select: ui.Select):
        selected_option = select.values[0]

        if selected_option == "General Support":
            await interaction.response.send_modal(GeneralSupportModal())
        elif selected_option == "Partnership Request":
            await interaction.response.send_modal(PartnershipRequestModal())
        elif selected_option == "Staff Report":
            await interaction.response.send_modal(StaffReportModal())
        elif selected_option == "Civilian Report":
            await interaction.response.send_modal(CivilianReportModal())


@bot.tree.command(name="ticketpanel", description="Send the support ticket panel")
async def ticketpanel(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "You do not have permission to use this command.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="Greenville Roleplay Global | Support Panel",
        description=(
            "Welcome to the __Greenville Roleplay Global Support Panel__! All support inquiries will be processed here. Please select the options from the dropdown below which best describes your need.\n\n"
            "`General Support`\n"
            "<:dot:1491005539201843290> Please select this option if you have general server concerns or questions. Additionally, if no other option describes your issue, select this. Do **not** use this for partnership requests.\n\n"
            "`Partnership Request`\n"
            "<:dot:1491005539201843290> Please select this option if you would like to request a partnership. Ensure you have read our requirements and blacklisted servers before continuing.\n\n"
            "`Staff Report`\n"
            "<:dot:1491005539201843290> Please select this option if you believe one of our **staff member(s)** may be in violation of the guidelines. Ensure you have proof upon proposal. Insufficient proof may lead to dismissal of the case.\n\n"
            "`Civilian Report`\n"
            "<:dot:1491005539201843290> Please select this option if you believe a **civilian(s)** may be in violation of our guidelines. You must have proof upon proposal, insufficient or absent proof may result in a dismissal.\n\n"
            "-# > Please be respectful to our staff members at all times. Tickets may take anywhere from __24-72__ to be processed, please be patient."
        ),
        color=0xEECB69
    )
    embed.set_image(url="https://i.imgur.com/FsQIqHn.jpeg")

    await interaction.response.send_message("Support panel sent.", ephemeral=True)
    await interaction.channel.send(embed=embed, view=TicketPanelView())

# -------- REGISTRATION VIEW --------
class RegistrationView(discord.ui.View):
    def __init__(self, user_id: int):
        super().__init__(timeout=None)
        self.user_id = user_id

    @discord.ui.button(label="Registrations", style=discord.ButtonStyle.secondary, custom_id="view_regs")
    async def view_regs(self, interaction: discord.Interaction, button: discord.ui.Button):
        data = await load_registrations()
        user_regs = data.get(str(self.user_id), [])

        if not user_regs:
            embed = discord.Embed(
                description="No active registrations found.",
                color=EMBED_COLOR
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        embed = discord.Embed(
            title=f"{len(user_regs)} found.",
            color=EMBED_COLOR
        )

        for reg in user_regs:
            embed.add_field(
                name="Vehicle",
                value=(
                    f"**Vehicle Brand** | {reg.get('brand', 'N/A')}\n"
                    f"**Vehicle Model** | {reg.get('model', 'N/A')}\n"
                    f"**Vehicle Color** | {reg.get('color', 'N/A')}\n"
                    f"**Vehicle Plate** | {reg.get('plate', 'N/A')}\n"
                    f"**Vehicle Year** | {reg.get('year', 'N/A')}"
                ),
                inline=False
            )

        await interaction.response.send_message(embed=embed, ephemeral=True)

#---------- UNREGISTER VIEW ----------
class UnregisterSelect(discord.ui.Select):
    def __init__(self, user_id, registrations):
        self.user_id = user_id
        self.registrations = registrations

        options = [
            discord.SelectOption(
                label=f"{r.get('brand', 'Unknown')} {r.get('model', '')}".strip(),
                description=f"{r.get('color','?')} | {r.get('plate','?')} | {r.get('year','?')}",
                value=str(i)
            )
            for i, r in enumerate(registrations)
        ]

        super().__init__(
            placeholder="Select vehicle(s) to unregister...",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id="unregister_select"
        )

    async def callback(self, interaction: discord.Interaction):
        data = await load_registrations()
        user_id = str(self.user_id)
        user_regs = data.get(user_id, [])

        # Remove selected vehicles
        selected_indexes = sorted([int(v) for v in self.values], reverse=True)

        removed = []
        for index in selected_indexes:
            if index < len(user_regs):
                removed.append(user_regs.pop(index))

        data[user_id] = user_regs
        await save_registrations(data)

        # Build embed
        if removed:
            description = "\n".join(
                f"Removed: {r.get('brand','Unknown')} {r.get('model','')}".strip()
                for r in removed
            )
        else:
            description = "No vehicles were removed."

        embed = discord.Embed(
            title="Unregistered Vehicles",
            description=description,
            color=EMBED_COLOR
        )

        await interaction.response.edit_message(embed=embed, view=None)


class UnregisterView(discord.ui.View):
    def __init__(self, user_id, registrations):
        super().__init__(timeout=None)
        self.add_item(UnregisterSelect(user_id, registrations))
        
# -------- LINK COMMAND --------
class LinkView(ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.url = url

    @ui.button(
    label="Server Access",
    style=discord.ButtonStyle.secondary,
    emoji=discord.PartialEmoji.from_str("<:extlink:1491980087065837748>")
)
    async def join(self, interaction: discord.Interaction, button: ui.Button):
        if not startup_active:
            await interaction.response.send_message("No active convoy.", ephemeral=True)
            return
        if interaction.user.id not in startup_reactors:
            await interaction.response.send_message("You must react to the startup message first.", ephemeral=True)
            return
        embed = discord.Embed(
            title="Private Server Link",
            description=f"> Click **[here]({self.url})** to join the private server.",
            color=EMBED_COLOR
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="release", description="Release the private server link")
@app_commands.describe(
    url="Private server link",
    session_type="Session type",
    additional_info="Additional information",
    frp_speed="FRP Speed Limit (numbers only)",
    peacetime="Peacetime Status",
    aorp="Area of Roleplay"
)
@app_commands.choices(peacetime=[
    app_commands.Choice(name="Strict", value="Strict"),
    app_commands.Choice(name="Normal", value="Normal"),
    app_commands.Choice(name="Off", value="Off")
])
async def release(
    interaction: discord.Interaction,
    url: str,
    session_type: str,
    additional_info: str,
    frp_speed: int,
    peacetime: app_commands.Choice[str],
    aorp: str
):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    global link_message
    if not startup_active:
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return
    if member != startup_host:
        await interaction.response.send_message("Only the host can release the link.", ephemeral=True)
        return

      # -------- MAIN EMBED --------
    embed = discord.Embed(
        title="SESSION RELEASE",
        description=(
            f"> <:dmsarrow:1491008371682443325> {member.mention} has released the following session. "
            "Please ensure you have read over our "
            "**[guidelines](https://discord.com/channels/1441901639739904125/1481562585781239969)** before proceeding. "
            "Please remember to use our "
            "**[event chat](https://discord.com/channels/1441901639739904125/1474109435751305286)** "
            "if you are affected by any form of **Roblox Chat Restrictions.**\n\n"

            f"**Information**\n"
f"> <:dot:1491005539201843290> **Session Type** | {session_type}\n"
f"> <:dot:1491005539201843290> **Host** | {startup_host.mention}\n"
f"> <:dot:1491005539201843290> **Additional Information** | {additional_info}\n"
f"> <:dot:1491005539201843290> **FRP Speed Limit** | {frp_speed}\n"
f"> <:dot:1491005539201843290> **Peacetime Status** | {peacetime.value}\n"
f"> <:dot:1491005539201843290> **Area of Roleplay** | {aorp}\n\n"
            "> Join using the button beneath this embed. We hope you enjoy the session, leave feedback at the end!"
        ),
        color=EMBED_COLOR
    )

    embed.set_image(url=LINK_BANNER)
    embed.set_footer(text="Greenville Roleplay Global", icon_url=FOOTER_ICON)

    view = LinkView(url)
    await interaction.response.send_message("Link released!", ephemeral=True)
    link_message = await interaction.channel.send(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    # -------- MODLOG --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        log_embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )

        # PFP + username at top
        log_embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        # Horizontal info
        log_embed.add_field(
            name="\u200b",
            value=(
                f"**Command Executed** | /release\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Content** | {url}\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}"
            ),
            inline=False
        )

        await log_channel.send(embed=log_embed)
# -------- LOA SYSTEM AND MODALS --------
class DenyModal(ui.Modal, title="Deny LOA"):
    reason = ui.TextInput(label="Reason for denial", style=discord.TextStyle.paragraph)
    def __init__(self, target_user: discord.User):
        super().__init__()
        self.target_user = target_user
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="LOA Denied",
            description=(
                f"Dear {self.target_user.mention},\n\n"
                f"Your LOA has been **Denied** for the following reason | {self.reason.value} |.\n\n"
                "If this is a misunderstanding, please contact management. "
                "Please do not submit another LOA until you have discussed with Management."
            ),
            color=EMBED_COLOR
        )
        try: await self.target_user.send(embed=embed)
        except: pass
        await interaction.response.send_message("LOA denied.", ephemeral=True)

class LOAView(ui.View):
    def __init__(self, user_id: int, start_ts: int, end_ts: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.handled = False
    def has_permission(self, member):
        return any(role.id in LOA_APPROVE_ROLES for role in member.roles)
    def disable_all(self):
        for item in self.children: item.disabled = True
    @ui.button(
    label="Approve",
    style=discord.ButtonStyle.success,
    custom_id="loa_approve"
)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not self.has_permission(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        if self.handled:
            await interaction.response.send_message("This LOA has already been handled.", ephemeral=True)
            return
        self.handled = True
        user = await interaction.client.fetch_user(self.user_id)
        embed = discord.Embed(
            title="LOA Approved",
            description=(
                f"Dear {user.mention},\n\n"
                f"Your LOA has been **approved** by {interaction.user.mention}.\n\n"
                f"**LOA Information**\n"
                f"<:dot:1480643720687915058> Start Date | <t:{self.start_ts}:f>\n"
                f"<:dot:1480643720687915058> End Date | <t:{self.end_ts}:f>\n\n"
                "You are exempt from **Staff Quota** during this period.\n\n"
                "After your LOA ends, activity is expected. You may not submit another LOA for 28 days.\n\n"
                "Kind Regards,\nGreenville Roleplay Global,\nManagement."
            ),
            color=EMBED_COLOR
        )
        try: await user.send(embed=embed)
        except: pass
        self.disable_all()
        await interaction.message.edit(view=self)
        await interaction.response.send_message("LOA approved.", ephemeral=True)
    @ui.button(
    label="Deny",
    style=discord.ButtonStyle.danger,
    custom_id="loa_deny"
)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not self.has_permission(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        if self.handled:
            await interaction.response.send_message("This LOA has already been handled.", ephemeral=True)
            return
        self.handled = True
        user = await interaction.client.fetch_user(self.user_id)
        await interaction.response.send_modal(DenyModal(user))
        self.disable_all()
        await interaction.message.edit(view=self)

# -------- END COMMANDS --------
class FeedbackModal(ui.Modal, title="Session Feedback"):
    rating = ui.TextInput(label="Rating (1-5)")
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        channel = bot.get_channel(FEEDBACK_CHANNEL)

        embed = discord.Embed(
            title="Convoy Feedback",
            description=(
                f"**Event Hoster** | {startup_host.mention if startup_host else 'Unknown'}\n"
                f"**Rater** | {interaction.user.mention}\n"
                f"**Rating** | {self.rating.value}\n"
                f"**Feedback** | {self.feedback.value}"
            ),
            color=EMBED_COLOR
        )

        await channel.send(embed=embed)
        await interaction.response.send_message("Feedback submitted.", ephemeral=True)


class EndView(ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Provide Feedback",
        style=discord.ButtonStyle.secondary,
        custom_id="feedback_button"
    )
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FeedbackModal())


@bot.tree.command(name="end", description="End the current convoy")
@app_commands.describe(host_note="Host note for the convoy")
async def end(interaction: discord.Interaction, host_note: str):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return

    global startup_active, startup_message, link_message, startup_time, startup_host, startup_reactors

    if not startup_active:
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return

    end_time = datetime.datetime.now(datetime.UTC)
    duration = end_time - startup_time
    channel = interaction.channel

    # ---- Send the end embed first ----
    embed = discord.Embed(
        title="<:Gvmc_crown:1491015668215058572> Greenville Roleplay Global Conclusion <:Gvmc_crown:1491015668215058572>",
        description=(
            f"<a:Animated_Arrow_Bluelite:1484055930919190589> | The Event that was hosted by {member.mention} has concluded. "
            "We appreciate those who were actively involved & participating in this event. "
            "We hope to see you in more of our events in the future as there are **many** more to come!\n\n"
            f"**Event Information**\n"
            f"<:dot:1491005539201843290> Event Start Time | <t:{int(startup_time.timestamp())}:f>\n"
            f"<:dot:1491005539201843290> Event End Time | <t:{int(end_time.timestamp())}:f>\n"
            f"<:dot:1491005539201843290> Event Duration | {str(duration).split('.')[0]}\n\n"
            f"<:announcement:1491014792440451082> Additional Notes | {host_note}\n\n"
            "<a:gvmc_heart:1480637190685069472> | Want to help improve our Events? Give us feedback by clicking the feedback button below!"
        ),
        color=EMBED_COLOR
    )
    embed.set_image(url=END_BANNER)
    embed.set_footer(text="Greenville Roleplay Global", icon_url=FOOTER_ICON)

    # ✅ FIX: View must NOT take arguments
    view = EndView()

    await interaction.response.send_message("Convoy ended!", ephemeral=True)

    end_msg = await channel.send(embed=embed, view=view)

    # ---- Purge the rest of the messages ----
    def check(msg):
        return not msg.pinned and msg.id != end_msg.id

    await channel.purge(check=check, limit=None)

    # ---- Session log (internal) ----
    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)
    log_embed = discord.Embed(
        title="Session Logged",
        description=f"Host: {member.mention}\nDuration: {str(duration).split('.')[0]}\nHost Note: {host_note}",
        color=EMBED_COLOR
    )
    await log_channel.send(embed=log_embed)

    # ---- MODLOG ----
    modlog_channel = bot.get_channel(MODLOG_CHANNEL)
    if modlog_channel:
        log_embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )
        log_embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)
        log_embed.add_field(
            name="\u200b",
            value=(
                f"**Command Executed** | /end\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}\n"
                f"**Host Note** | {host_note}\n"
                f"**Event Duration** | {str(duration).split('.')[0]}"
            ),
            inline=False
        )
        await modlog_channel.send(embed=log_embed)

    # ---- Reset convoy state (MUST stay inside function) ----
    startup_active = False
    startup_message = None
    link_message = None
    startup_reactors = set()
    startup_time = None
    startup_host = None
    await early_access.reset_on_convoy_end(bot)
# -------- LOA COMMAND CONTINUED --------
@bot.tree.command(name="loa", description="Submit a Leave of Absence")
@app_commands.describe(
    reason="Reason for LOA",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    rank="Your rank",
    notes="Additional notes"
)
async def loa(interaction: discord.Interaction, reason: str, start_date: str, end_date: str, rank: str, notes: str):
    member = interaction.guild.get_member(interaction.user.id)

    if LOA_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    except:
        await interaction.response.send_message("Invalid date format. Use YYYY-MM-DD.", ephemeral=True)
        return

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Defer the response to avoid "did not respond"
    await interaction.response.defer()

    # confirmation embed
    confirm_embed = discord.Embed(
        title="LOA Submission",
        description=(
            "> <a:Animated_Arrow_Bluelite:1484055930919190589> Your LOA has been submitted. Our Management team will review it shortly.\n\n"
            "> Please look out for a **Direct Message** confirming your submission and another when we have approved or denied your submission.\n\n"
            "> If there are any issues, contact management."

            "**If you do not get a DM response within 1 day, please create a ticket.**"
        ),
        color=EMBED_COLOR
    )

    # Send confirmation via followup
    await interaction.followup.send(embed=confirm_embed)

    # send to staff channel
    channel = bot.get_channel(LOA_CHANNEL)
    if channel:
        try:
            embed = discord.Embed(
                title="LOA Request",
                description=(
                    f"User requesting | {member.mention}\n"
                    f"<:dot:1480643720687915058> Start Date | <t:{start_ts}:f>\n"
                    f"<:dot:1480643720687915058> End Date | <t:{end_ts}:f>\n"
                    f"<:dot:1480643720687915058> Reason | {reason}\n"
                    f"<:dot:1480643720687915058> Rank | {rank}\n"
                    f"<:dot:1480643720687915058> Additional Notes | {notes}\n\n"
                    "Please use the buttons below to approve/deny this LOA."
                ),
                color=EMBED_COLOR
            )

            view = LOAView(member.id, start_ts, end_ts)
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print("Failed to send LOA to staff channel:", e)

# -------- REGISTER COMMAND --------
@bot.tree.command(name="register", description="Register a vehicle")
@app_commands.describe(
    brand="Vehicle brand",
    model="Vehicle model",
    color="Vehicle color",
    plate="Plate number",
    year="Vehicle year"
)
async def register(interaction: discord.Interaction, brand: str, model: str, color: str, plate: str, year: str):
    await interaction.response.defer(ephemeral=True)

    data = await load_registrations()
    user_id = str(interaction.user.id)

    if user_id not in data:
        data[user_id] = []

    new_reg = {
        "brand": brand,
        "model": model,
        "color": color,
        "plate": plate,
        "year": year,  # <-- Added missing comma here
        "timestamp": int(datetime.datetime.now(datetime.timezone.utc).timestamp())       # <-- Corrected datetime.UTC to timezone.utc
    }

    data[user_id].append(new_reg)
    await save_registrations(data)

    # ✅ THIS MUST BE INSIDE THE FUNCTION
    log_channel = bot.get_channel(REG_LOG_CHANNEL)

    if log_channel:
        embed = discord.Embed(title="New Registration", color=EMBED_COLOR)
        embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        embed.add_field(name="Brand", value=brand, inline=True)
        embed.add_field(name="Model", value=model, inline=True)
        embed.add_field(name="Color", value=color, inline=True)
        embed.add_field(name="Plate", value=plate, inline=True)
        embed.add_field(name="Year", value=year, inline=True)

        await log_channel.send(embed=embed)

    await interaction.followup.send("Vehicle registered successfully.", ephemeral=True)

# -------- UNREGISTER COMMAND (UPGRADED) --------
@bot.tree.command(name="unregister", description="Remove registered vehicle(s)")
async def unregister(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    data = await load_registrations()
    user_id = str(interaction.user.id)
    user_regs = data.get(user_id, [])

    if not user_regs:
        embed = discord.Embed(
            description="No registered vehicles found.",
            color=EMBED_COLOR
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        return

    view = UnregisterView(user_id, user_regs)
    await interaction.followup.send(
        embed=discord.Embed(
            title="__Your registered vehicles__",
            description="\n".join(
                f"<:dmsarrow:1491008371682443325> {r.get('brand','Unknown')} {r.get('model','')}".strip()
                for r in user_regs
            ),
            color=EMBED_COLOR
        ),
        view=view,
        ephemeral=True
    )

@bot.tree.command(name="verifyall", description="Verify all users whose nickname matches a Roblox account")
async def verifyall(interaction: discord.Interaction):

    # admin only
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild

    if guild is None:
        await interaction.followup.send(
            "❌ This command can only be used in a server."
        )
        return

    db = load_data()

    verified_count = 0

    async with aiohttp.ClientSession() as session:

        for member in guild.members:

            # skip bots
            if member.bot:
                continue

            # skip already verified
            if str(member.id) in db:
                continue

            nickname = member.nick or member.name

            try:

                async with session.post(
                    "https://users.roblox.com/v1/usernames/users",
                    json={
                        "usernames": [nickname],
                        "excludeBannedUsers": True
                    }
                ) as resp:

                    data = await resp.json()

                    if not data.get("data"):
                        continue

                    user = data["data"][0]

                    roblox_id = user["id"]
                    username = user["name"]

                    # save verification
                    db[str(member.id)] = {
                        "roblox_id": roblox_id,
                        "username": username
                    }

                    verified_count += 1

                # prevent rate limits
                await asyncio.sleep(0.35)

            except Exception as e:
                print(f"[VERIFYALL ERROR] {member.id}: {e}")

    save_data(db)

    await interaction.followup.send(
        f"✅ Verified {verified_count} users successfully."
    )

@bot.tree.command(name="verifyuser", description="Manually verify a user")
@app_commands.describe(
    member="Discord user to verify",
    robloxname="Roblox username"
)
async def verifyuser(
    interaction: discord.Interaction,
    member: discord.Member,
    robloxname: str
):

    # admin only
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message(
            "❌ You do not have permission to use this command.",
            ephemeral=True
        )
        return

    await interaction.response.defer(ephemeral=True)

    async with aiohttp.ClientSession() as session:

        try:

            async with session.post(
                "https://users.roblox.com/v1/usernames/users",
                json={
                    "usernames": [robloxname],
                    "excludeBannedUsers": True
                }
            ) as resp:

                data = await resp.json()

                if not data.get("data"):
                    await interaction.followup.send(
                        "❌ Roblox user not found."
                    )
                    return

                user = data["data"][0]

                roblox_id = user["id"]
                username = user["name"]

        except Exception as e:
            await interaction.followup.send(
                f"❌ Error: {e}"
            )
            return

    db = load_data()

    db[str(member.id)] = {
        "roblox_id": roblox_id,
        "username": username
    }

    save_data(db)

    await interaction.followup.send(
        f"✅ Successfully verified {member.mention} as **{username}**"
    )

@bot.tree.command(name="verify", description="Link your Roblox account")
@app_commands.describe(robloxname="Your Roblox username")
async def verify(interaction: discord.Interaction, robloxname: str):

    await interaction.response.defer(ephemeral=True)

    # OPTIONAL SAFETY: must match nickname (prevents random linking abuse)
    nickname = interaction.user.nick or interaction.user.name

    async with aiohttp.ClientSession() as session:

        async with session.post(
            "https://users.roblox.com/v1/usernames/users",
            json={"usernames": [robloxname], "excludeBannedUsers": True}
        ) as resp:

            data = await resp.json()

            if not data.get("data"):
                await interaction.followup.send("User could not be fetched. Please ensure you are verified via bloxlink before contiuing.")
                return

            user = data["data"][0]
            roblox_id = user["id"]
            username = user["name"]

        # 🔒 BASIC ANTI-IMPERSONATION CHECK
        if robloxname.lower() != nickname.lower():
            await interaction.followup.send(
                "Your Discord username must match your Roblox username. Please verify via bloxlink before continuing."
            )
            return

    db = load_data()

    db[str(interaction.user.id)] = {
        "roblox_id": roblox_id,
        "username": username
    }

    save_data(db)

    await interaction.followup.send(f"✅ Verified as **{username}**")
    
# -------- INFO COMMAND --------
@bot.tree.command(name="botinfo", description="View the Bot's information")
async def info(interaction: discord.Interaction):
    uptime = datetime.datetime.now(datetime.UTC) - bot_start_time
    api_ping = round(bot.latency * 1000)

    # Step 1: Bot info embed
    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"> Developer: Reuben2k11\n"
            f"> Prefix: >\n"
            f"> Uptime: {str(uptime).split('.')[0]}\n"
            f"> Ping: {api_ping}ms\n"
            f"> Discord.py Version: {discord.__version__}\n"
            f"> Status: Online"
        ),
        color=EMBED_COLOR,
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    await interaction.response.send_message(embed=embed)

    # -------- MODLOG --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        log_embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )

        # PFP + username at top
        log_embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        # Horizontal info (no content field needed for info command)
        log_embed.add_field(
            name="\u200b",
            value=(
                f"**Command Executed** | /botinfo\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}"
            ),
            inline=False
        )

        await log_channel.send(embed=log_embed)

@bot.tree.command(name="profile", description="View a civilian profile")
@app_commands.describe(user="User to view")
async def profile(interaction: discord.Interaction, user: discord.Member = None):

    await interaction.response.defer()

    print("🔥 PROFILE COMMAND IS RUNNING")

    target = user or interaction.user

    print("[PROFILE] Target:", target.id)

    # -------- ROBLOX FROM YOUR DATABASE (NO BLOXLINK) --------
    db = load_data()
    user_data = db.get(str(target.id))

    roblox_id = None
    username = None
    profile_url = None
    avatar_url = None

    if user_data:
        roblox_id = user_data.get("roblox_id")
        username = user_data.get("username")

    print("[PROFILE] Roblox ID:", roblox_id)

    # -------- ROBLOX FETCH --------
    if roblox_id:
        profile_url = f"https://www.roblox.com/users/{roblox_id}/profile"

        try:
            async with aiohttp.ClientSession() as session:

                async with session.get(f"https://users.roblox.com/v1/users/{roblox_id}") as resp:
                    print("[ROBLOX USER STATUS]", resp.status)

                    if resp.status == 200:
                        data = await resp.json()
                        username = data.get("name", username)

                async with session.get(
                    f"https://thumbnails.roblox.com/v1/users/avatar"
                    f"?userIds={roblox_id}&size=420x420&format=Png&isCircular=false"
                ) as resp:
                    print("[ROBLOX AVATAR STATUS]", resp.status)

                    if resp.status == 200:
                        avatar_data = await resp.json()
                        avatar_url = avatar_data["data"][0]["imageUrl"]

        except Exception as e:
            print("[ROBLOX ERROR]", e)

    else:
        print("[PROFILE] No Roblox link found")

    # -------- REGISTRATIONS --------
    data = await load_registrations()
    reg_count = len(data.get(str(target.id), []))

    # -------- LICENSE STATUS --------
    license_status = "Suspended" if any(role.id == LICENSE_SUSPENDED_ROLE for role in target.roles) else "Active"

    # -------- EMBED --------
    if roblox_id and username:
        roblox_display = f"[{username}]({profile_url})"
    else:
        roblox_display = "Not Linked"

    embed = discord.Embed(
        title="Greenville Roleplay Global | Civilian Profile",
        description=(
            f"> You are currently viewing {target.display_name}'s profile.\n\n"
            f"> <:roblox:1502473899349377045> Roblox Profile: {roblox_display}\n"
            f"> <:licence:1508378444684197991> License Status: {license_status}\n"
            f"> <:registration:1508379502319767653> Registration(s): `{reg_count}`\n\n"
            f"-# ><:dmsarrow:1491008371682443325> To **register a vehicle**, use `/register`"
        ),
        color=EMBED_COLOR
    )

    embed.set_thumbnail(url=avatar_url or target.display_avatar.url)

    embed.set_footer(text="Greenville Roleplay Global", icon_url=FOOTER_ICON)

    view = RegistrationView(target.id)

    await interaction.followup.send(embed=embed, view=view)
    
# -------- MEMBERCOUNT COMMAND --------
@bot.tree.command(name="membercount", description="Show total member count")
async def membercount(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return

    # Step 1: Send the actual embed in the channel
    count = guild.member_count
    embed = discord.Embed(
        title="**Members**",
        description=f"{count}",
        color=EMBED_COLOR,
        timestamp=datetime.datetime.now(datetime.UTC)
    )
    await interaction.response.send_message(embed=embed)

    # -------- MODLOG --------
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    if log_channel:
        log_embed = discord.Embed(
            title="__**Command Execution**__",
            color=EMBED_COLOR,
            timestamp=discord.utils.utcnow()
        )

        # PFP + username at top
        log_embed.set_author(name=str(interaction.user), icon_url=interaction.user.display_avatar.url)

        # Horizontal info like /say but without content
        log_embed.add_field(
            name="\u200b",
            value=(
                f"**Command Executed** | /membercount\n"
                f"**User** | {interaction.user.mention}\n"
                f"**Time** | <t:{int(datetime.datetime.now(datetime.UTC).timestamp())}:F>\n"
                f"**Channel** | {interaction.channel.mention}"
            ),
            inline=False
        )

        await log_channel.send(embed=log_embed)
# -------- KILL COMMAND --------
@bot.tree.command(name="botreset", description="Restart the Bot")
async def kill(interaction: discord.Interaction):
    member = interaction.guild.get_member(interaction.user.id)
    if KILL_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("Only the Bot Developer is authorized to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("The bot has restarted.", ephemeral=True)
    sys.exit()

import economy
import early_access

economy.setup(bot, EMBED_COLOR)
early_access.setup(
    bot,
    EMBED_COLOR,
    FOOTER_ICON,
    DATA_DIR,
    get_convoy_active=lambda: startup_active,
    get_convoy_host=lambda: startup_host,
)


def main():
    bot.run(TOKEN)


if __name__ == "__main__":
    main()
