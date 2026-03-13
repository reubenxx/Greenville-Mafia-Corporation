import discord
from discord import app_commands, ui
from discord.ext import commands
import os
import datetime

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
tree = bot.tree  # app_commands tree for slash commands

# ===== Session tracking =====
current_session = None  # store info about ongoing /startup

# ===== Helper Images =====
BANNER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png?ex=69b4fb59&is=69b3a9d9&hm=b10004a8613aaab64006fd5943d5f9c6d844d2b5be710e5795759297754637bd&=&format=webp&quality=lossless&width=2034&height=812"
FOOTER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?ex=69b3bc5e&is=69b26ade&hm=79308b7601efdc372c21f5c2660ebeeefdf5e39b85a66636845f6f392c52468c&=&format=webp&quality=lossless&width=1656&height=1369"


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
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    return embed


# ===== Welcome / Leave Events =====
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    embed = discord.Embed(
        title="WELCOME",
        description=(
            f"Welcome to __**Greenville Mafia Corporation**__ {member.mention}!\n\n"
            f"Please read through our **[server rules](https://discord.com/channels/1441901639739904125/1442242436138274826)** to get started.\n\n"
            f"We appreciate having you here with us at **Greenville Mafia Corporation.**"
        ),
        color=0x87CEFA
    )
    embed.add_field(name="Member Number", value=f"You are **member #{member.guild.member_count}** in this server.", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
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
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)


# ===== /startup Command =====
@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(count="Number of people (3-50)")
async def startup(interaction: discord.Interaction, count: int):
    global current_session
    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    if current_session:
        await interaction.response.send_message("A session is already running. Wait for /end.", ephemeral=True)
        return
    if not (3 <= count <= 50):
        await interaction.response.send_message("Number must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GREENVILLE MAFIA CORPORATION STARTUP",
        description=(
            f"A Convoy is currently being setup by {interaction.user.mention}. Please read through our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending. "
            f"If you are affected by any form of **in-game chat restriction**, please communicate in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            f"If you are willing to attend, please react with the **checkmark** below. If there are any issues joining or in session, please ping the host in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            "-# Of course, please remain respectful and patient with hosts and members. Most importantly, enjoy your time in the **convoy!**\n"
            "-# Hope to see you there!"
        ),
        color=0x87CEFA
    )
    embed.set_image(url=BANNER_IMAGE)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    msg = await interaction.response.send_message(content=f"<@&{NOTIFY_ROLE}>", embed=embed, fetch_response=True)

    current_session = {
        "host": interaction.user,
        "startup_msg": msg,
        "start_time": datetime.datetime.utcnow(),
        "attendees": set()
    }

    # React to message
    await msg.add_reaction("✅")


# ===== /end Command =====
@tree.command(name="end", description="End the current convoy session")
async def end(interaction: discord.Interaction):
    global current_session
    if not current_session:
        await interaction.response.send_message("No active session.", ephemeral=True)
        return
    session = current_session

    # Count reactions
    msg = session["startup_msg"]
    msg = await msg.fetch()  # fetch latest
    reaction = discord.utils.get(msg.reactions, emoji="✅")
    attendees = set()
    if reaction:
        async for user in reaction.users():
            if not user.bot:
                attendees.add(user)

    # Delete startup message
    try:
        await msg.delete()
    except:
        pass

    # Send end message
    embed = discord.Embed(
        title="CONVOY CONCLUSION",
        description=(
            f"We appreciate everyone who participated in the event.\n"
            f"A 15 minute convoy cooldown is now active.\n"
            f"Keep on the lookout for the next convoy.\n"
        ),
        color=0x87CEFA
    )
    embed.set_image(url=BANNER_IMAGE)
    await interaction.response.send_message(embed=embed)

    # Log session
    duration = datetime.datetime.utcnow() - session["start_time"]
    log_embed = discord.Embed(
        title="Convoy Session Log",
        description=(
            f"Host: {session['host'].mention}\n"
            f"Duration: {str(duration).split('.')[0]}\n"
            f"Attendees: {len(attendees)}"
        ),
        color=0x87CEFA
    )
    await bot.get_channel(SESSION_LOG_CHANNEL).send(embed=log_embed)

    current_session = None


# ===== Bot Run =====
bot.run(os.getenv("TOKEN"))
