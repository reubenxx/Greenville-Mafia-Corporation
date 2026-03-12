import discord
import os
from discord.ext import commands
from discord import app_commands, Interaction
from discord.ui import Button, View

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439

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
    print(f"{bot.user} is online!")
    # Sync app commands (slash commands)
    await bot.tree.sync()

# ===== Dyno-style modlog embed =====
def dyno_embed(action, user, moderator=None, reason="No reason provided"):
    embed = discord.Embed(description=f"**{action}**", color=0x2F3136)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Greenville Mafia Corporation")
    return embed

# ===== Welcome Message =====
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
    embed.set_footer(text="Greenville Mafia Corporation")

    await channel.send(embed=embed)

    log = dyno_embed("Member Joined", member)
    await log_channel.send(embed=log)

# ===== Member Leave =====
@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    log = dyno_embed("Member Left", member)
    await log_channel.send(embed=log)

# ===== Ban / Unban =====
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

# ===== Say Command (restricted to multiple roles) =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_ROLE_IDS = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return

    await ctx.message.delete()
    await ctx.send(message)

# ===== Convoy Tracking =====
active_reactors = {}  # message.id -> set of user_ids

# ===== Slash Commands =====
ALLOWED_COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]
PING_ROLE = 1480656237027660046

@bot.tree.command(name="startup", description="Launch a convoy")
@app_commands.describe(participants="Number of participants (3-50)")
async def startup(interaction: Interaction, participants: int):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return
    if not (3 <= participants <= 50):
        await interaction.response.send_message("Number must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(
            f"A convoy is currently being hosted by {interaction.user.mention}. Please react if you are intending to join.\n"
            f"We ask you kindly review our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
            f"If you are affected by the **Roblox Chat Ban**, feel free to talk in our [convoy chat](https://discord.com/channels/1441901639739904126/1474109435751305286).\n\n"
            f"All of our **Meet Launchers** are constantly monitoring the chat in case you might be in need of any assistance.\n\n"
            f"**Most importantly, enjoy your time in Greenville Mafia Corporation convoys.**"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    msg = await interaction.channel.send(f"<@&{PING_ROLE}>", embed=embed)
    await msg.add_reaction("✅")
    active_reactors[msg.id] = set()

@bot.tree.command(name="link", description="Release convoy link")
@app_commands.describe(link="Roblox private server link")
async def link(interaction: Interaction, link: str):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    # Find latest startup message in channel
    last_msg = None
    async for m in interaction.channel.history(limit=50):
        if m.embeds and m.id in active_reactors:
            last_msg = m
            break
    if not last_msg:
        await interaction.response.send_message("No active startup message found.", ephemeral=True)
        return

    # Filter users who reacted
    message = last_msg
    reacted_users = set()
    for reaction in message.reactions:
        if str(reaction.emoji) == "✅":
            async for user in reaction.users():
                reacted_users.add(user.id)

    # Make button
    view = View()
    view.add_item(Button(label="Link", url=link))
    embed = discord.Embed(
        title="Convoy Release",
        description=(
            "The convoy link has been released! If you reacted, please join via the button below.\n"
            f"If there are any issues, ping the host {interaction.user.mention} in [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    await interaction.channel.send(embed=embed, view=view)

@bot.tree.command(name="end", description="End the convoy")
async def end(interaction: Interaction):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You do not have permission to use this command.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            "We appreciate everyone who participated in the event. A 15 minute convoy cooldown is currently active.\n"
            "Keep on the lookout for the next convoy as we host them frequently.\n\n"
            "Want to give feedback to hosts for improved sessions? Click the button below."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    view = View()
    view.add_item(Button(label="Feedback", style=discord.ButtonStyle.link, url="https://discord.com/channels/1441901639739904125/1481568923504611439"))
    await interaction.channel.send(embed=embed, view=view)

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
