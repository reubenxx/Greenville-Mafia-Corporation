import discord
import os
from discord.ext import commands

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044

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

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
