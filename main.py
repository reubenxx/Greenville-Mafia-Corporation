import discord
from discord.ext import commands
from discord import app_commands, Interaction, ButtonStyle
from discord.ui import Button, View, Modal, TextInput
import os

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439
NOTIFY_ROLE = 1480656237027660046

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

# ===== Bot Setup =====
bot = commands.Bot(command_prefix=">", intents=intents)

# ===== Bot Ready Event =====
@bot.event
async def on_ready():
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="Greenville Mafia Corporation"
    )
    await bot.change_presence(activity=activity)
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} slash commands")
    except Exception as e:
        print(f"Failed to sync commands: {e}")
    print(f"{bot.user} is online!")

# ===== Dyno-style modlog embed =====
def dyno_embed(action, user, moderator=None, reason="No reason provided"):
    embed = discord.Embed(description=f"**{action}**", color=0x2F3136)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Greenville Mafia Corporation",
                     icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?width=1656&height=1369")
    return embed

# ===== Welcome / Leave / Ban / Unban =====
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    log_channel = bot.get_channel(MODLOG_CHANNEL)

    embed = discord.Embed(
        title="Welcome to Greenville Mafia Corporation",
        description=(
            f"Welcome to __**Greenville Mafia Corporation**__ {member.mention}!\n\n"
            f"Please read through our **[server rules](https://discord.com/channels/1441901639739904125/1442242436138274826)** to get started.\n\n"
            f"We appreciate having you here with us at **Greenville Mafia Corporation.**"
        ),
        color=0x87CEFA
    )
    embed.add_field(
        name="Member Number",
        value=f"You are **member #{member.guild.member_count}** in this server.",
        inline=False
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Greenville Mafia Corporation",
                     icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?width=1656&height=1369")

    await channel.send(embed=embed)
    log = dyno_embed("Member Joined", member)
    await log_channel.send(embed=log)

@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    log = dyno_embed("Member Left", member)
    await log_channel.send(embed=log)

@bot.event
async def on_member_ban(guild, user):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    log = dyno_embed("User Banned", user)
    await log_channel.send(embed=log)

@bot.event
async def on_member_unban(guild, user):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    log = dyno_embed("User Unbanned", user)
    await log_channel.send(embed=log)

# ===== Say Command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_ROLE_IDS = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)

# ===== Slash Commands for Convoy =====

# Store reactions per startup message
convoy_reactors = {}

@bot.tree.command(name="startup", description="Launch a convoy (3-50 players)")
async def startup(interaction: Interaction, number_of_players: int):
    allowed_roles = [1479832999435440178]
    if not any(role.id in allowed_roles for role in interaction.user.roles):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return

    if number_of_players < 3 or number_of_players > 50:
        await interaction.response.send_message("Number must be between 3-50.", ephemeral=True)
        return

    await interaction.response.defer()
    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(
            f"A convoy is currently being hosted by {interaction.user.mention}. "
            f"Please react if you are intending to join. We ask you kindly review our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
            f"If you are affected by the **Roblox Chat Ban**, feel free to talk in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286). "
            f"All of our **Meet Launchers** are constantly monitoring the chat in case you might be in need of any assistance.\n\n"
            f"-# Most importantly, enjoy your time in **Greenville Mafia Corporation** convoys."
        ),
        color=0x87CEFA
    )
    embed.set_footer(icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?width=1656&height=1369")
    msg = await interaction.followup.send(embed=embed, content=f"<@&{NOTIFY_ROLE}>", wait=True)
    await msg.add_reaction("✅")
    convoy_reactors[msg.id] = set()

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
