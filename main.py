import discord
from discord import app_commands, ui
from discord.ext import commands
import os

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439

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

# Store startup messages and reactions
startup_messages = {}  # message.id: set(user.id)


# ===== Helper Embed Footer Image =====
FOOTER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?ex=69b3bc5e&is=69b26ade&hm=79308b7601efdc372c21f5c2660ebeeefdf5e39b85a66636845f6f392c52468c&=&format=webp&quality=lossless&width=1656&height=1369"


# ===== Bot Ready Event =====
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
        title="Welcome to Greenville Mafia Corporation",
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
    ALLOWED_ROLE_IDS = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)


# ===== /startup Command =====
@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(count="Number of people (3-50)")
async def startup(interaction: discord.Interaction, count: int):
    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return

    if not (3 <= count <= 50):
        await interaction.response.send_message("Number must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(
            f"A convoy is currently being hosted by {interaction.user.mention}. Please react if you are intending to join.\n"
            f"Please review our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
            f"If affected by Roblox Chat Ban, feel free to talk in our **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**.\n\n"
            f"Enjoy your time in **Greenville Mafia Corporation** convoys!"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    msg = await interaction.response.send_message(content=f"<@&{NOTIFY_ROLE}>", embed=embed)
    # Store message.id if you want to track reactions later


# ===== Bot Run =====
bot.run(os.getenv("TOKEN"))
