import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import os
import time
import datetime
import random

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439
SESSION_LOG_CHANNEL = 1481568871679787088

# ===== Role IDs =====
ALLOWED_COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]
STARTUP_ROLE = 1479832999435440178
NOTIFY_ROLE = 1480656237027660046

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

# ===== Bot Setup =====
bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

# ===== Global Storage =====
startup_messages = {}  # message.id: set(user.id)
current_session = None  # track who ran startup
startup_start_time = None

# ===== Embed Banner =====
BANNER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png?ex=69b4fb59&is=69b3a9d9&hm=b10004a8613aaab64006fd5943d5f9c6d844d2b5be710e5795759297754637bd&=&format=webp&quality=lossless&width=2034&height=812"

# ===== Bot Ready =====
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching, name="Greenville Mafia Corporation")
    await bot.change_presence(activity=activity)
    print(f"{bot.user} is online!")
    await tree.sync()


# ===== Dyno-style modlog embed =====
def dyno_embed(action, user, moderator=None, reason="No reason provided"):
    embed = discord.Embed(description=f"**{action}**", color=0x2F3136)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=BANNER_IMAGE)
    return embed


# ===== Welcome / Leave Events =====
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    embed = discord.Embed(
        title="WELCOME TO GREENVILLE MAFIA CORPORATION",
        description=(
            f"Welcome to __**Greenville Mafia Corporation**__ {member.mention}!\n\n"
            f"Please read through our **[server rules](https://discord.com/channels/1441901639739904125/1442242436138274826)** to get started.\n\n"
            f"We appreciate having you here with us at **Greenville Mafia Corporation.**"
        ),
        color=0x87CEFA
    )
    embed.add_field(name="Member Number", value=f"You are **member #{member.guild.member_count}** in this server.", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=BANNER_IMAGE)
    await channel.send(embed=embed)
    await log_channel.send(embed=dyno_embed("Member Joined", member))


@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    await log_channel.send(embed=dyno_embed("Member Left", member))


@bot.event
async def on_member_ban(guild, user):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    await log_channel.send(embed=dyno_embed("User Banned", user))


@bot.event
async def on_member_unban(guild, user):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    await log_channel.send(embed=dyno_embed("User Unbanned", user))


# ===== >say Command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_ROLE_IDS_SAY = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS_SAY for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)


# ===== /startup Command =====
@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(count="Number of people (3-50)")
async def startup(interaction: discord.Interaction, count: int):
    global current_session, startup_start_time, startup_messages

    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return

    if current_session is not None:
        await interaction.response.send_message(f"Another session is active. Wait for /end.", ephemeral=True)
        return

    if not (3 <= count <= 50):
        await interaction.response.send_message("Number must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GREENVILLE MAFIA CORPORATION STARTUP",
        description=(
            f"A Convoy is currently being setup by {interaction.user.mention}. "
            f"Please read through our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending. "
            f"If you are affected by any form of **in-game chat restriction**, please communicate in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            f"If you are willing to attend, please react with the **✅** below. "
            f"If there are any issues joining or in session, please ping the host in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            f"-# Of course, please remain respectful and patient with hosts and members. Most importantly, enjoy your time in the **convoy!**\n"
            f"-# Hope to see you there!"
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_footer(text="Greenville Mafia Corporation")
    await interaction.response.send_message(content=f"<@&{NOTIFY_ROLE}>", embed=embed)
    msg = await interaction.original_response()
    await msg.add_reaction("✅")
    startup_messages[msg.id] = set()
    current_session = interaction.user
    startup_start_time = time.time()


# ===== /link Command =====
@tree.command(name="link", description="Release convoy link")
@app_commands.describe(link="Roblox private server link")
async def link(interaction: discord.Interaction, link: str):
    global startup_messages

    if current_session is None or interaction.user != current_session:
        await interaction.response.send_message("You cannot release a link before starting a session.", ephemeral=True)
        return

    embed = discord.Embed(
        title="CONVOY RELEASE",
        description=(
            f"The convoy link has been released! If you reacted, please join via the button below. "
            f"If there are any issues, ping the host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**."
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_footer(text="Greenville Mafia Corporation")

    button = ui.Button(label="Link", url=link)
    view = ui.View()
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view)


# ===== /end Command =====
@tree.command(name="end", description="End current convoy session")
async def end(interaction: discord.Interaction):
    global current_session, startup_messages, startup_start_time

    if current_session is None:
        await interaction.response.send_message("No active session to end.", ephemeral=True)
        return

    # Delete startup and link messages
    for msg_id in startup_messages.keys():
        try:
            msg = await interaction.channel.fetch_message(msg_id)
            await msg.delete()
        except:
            pass

    duration = int(time.time() - startup_start_time)
    hours, remainder = divmod(duration, 3600)
    minutes, seconds = divmod(remainder, 60)
    duration_str = f"{hours}h {minutes}m {seconds}s"

    embed = discord.Embed(
        title="CONVOY CONCLUSION",
        description=(
            f"We appreciate everyone who participated. "
            f"A 15 minute convoy cooldown is now active. Keep an eye out for the next convoy.\n\n"
            f"Want to give feedback to hosts? Click the button below."
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=current_session.display_avatar.url)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_footer(text="Greenville Mafia Corporation")

    button = ui.Button(label="Give Feedback", style=discord.ButtonStyle.link,
                       url="https://discord.com/channels/1441901639739904125/1481568923504611439")  # link to feedback channel
    view = ui.View()
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view)

    # Log session
    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)
    await log_channel.send(
        embed=discord.Embed(
            title="CONVOY SESSION LOG",
            description=f"Host: {current_session.mention}\nDuration: {duration_str}\nTotal reactions: {sum(len(r) for r in startup_messages.values())}",
            color=0x2F3136
        )
    )

    # Reset
    current_session = None
    startup_messages = {}
    startup_start_time = None


# ===== /info Command =====
@tree.command(name="info", description="Bot information")
async def info(interaction: discord.Interaction):
    uptime = datetime.datetime.utcnow() - bot.launch_time if hasattr(bot, "launch_time") else "Unknown"
    ping = round(bot.latency * 1000, 2)
    risk_levels = ["negligible", "Very unlikely", "Unlikely", "Even", "Likely", "Very likely"]
    risk = random.choice(risk_levels)

    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"Prefix: `>`\n"
            f"Uptime: {uptime}\n"
            f"Ping: {ping}ms\n"
            f"Status: Online\n"
            f"Crash Risk: {risk}"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=BANNER_IMAGE)
    await interaction.response.send_message(embed=embed, ephemeral=True)


# ===== Run Bot =====
bot.launch_time = time.time()
bot.run(os.getenv("TOKEN"))
