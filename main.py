import discord
from discord import app_commands, ui
from discord.ext import commands, tasks
import os
import datetime
import random

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439
SESSION_LOG_CHANNEL = 1481568871679787088

# ===== Roles =====
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

# ===== Globals =====
startup_active = None  # track the current startup session
startup_messages = {}  # message.id: set(user.id)
startup_start_time = None
bot_launch_time = datetime.datetime.utcnow()

# ===== Images =====
FOOTER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?ex=69b3bc5e&is=69b26ade&hm=79308b7601efdc372c21f5c2660ebeeefdf5e39b85a66636845f6f392c52468c&=&format=webp&quality=lossless&width=1656&height=1369"
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
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
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

# ===== STARTUP COMMAND =====
@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(count="Number of people (3-50)")
async def startup(interaction: discord.Interaction, count: int):
    global startup_active, startup_messages, startup_start_time
    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You cannot use this command.", ephemeral=True)
        return
    if startup_active:
        await interaction.response.send_message(f"A convoy is already active hosted by {startup_active['host'].mention}.", ephemeral=True)
        return
    if not (3 <= count <= 50):
        await interaction.response.send_message("Number must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GREENVILLE MAFIA CORPORATION STARTUP",
        description=(
            f"A Convoy is currently being setup by {interaction.user.mention}. Please read through our "
            f"**[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending. "
            f"If you are affected by any form of **in-game chat restriction**, please communicate in our "
            f"[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            f"If you are willing to attend, please react with the **✅** below. "
            f"If there are any issues joining or in session, please ping the host in our "
            f"[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
            f"-# Of course, please remain respectful and patient with hosts and members. "
            f"Most importantly, enjoy your time in the **convoy!**\n\n"
            f"-# Hope to see you there!"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    msg = await interaction.response.send_message(content=f"<@&{NOTIFY_ROLE}>", embed=embed)
    sent_msg = await interaction.original_response()
    await sent_msg.add_reaction("✅")

    startup_active = {"host": interaction.user, "message": sent_msg}
    startup_messages = {}
    startup_start_time = datetime.datetime.utcnow()

# ===== LINK COMMAND =====
@tree.command(name="link", description="Release convoy link")
@app_commands.describe(url="Private server URL")
async def link(interaction: discord.Interaction, url: str):
    global startup_active, startup_messages
    if not startup_active:
        await interaction.response.send_message("No active convoy to release link for.", ephemeral=True)
        return
    if interaction.user != startup_active["host"]:
        await interaction.response.send_message("Only the host can release the link.", ephemeral=True)
        return

    embed = discord.Embed(
        title="CONVOY RELEASE",
        description=(
            f"The convoy link has been released! If you reacted, please join via the button below. "
            f"If there are any issues, please ping the host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)

    view = ui.View()
    button = ui.Button(label="Link", url=url)
    view.add_item(button)
    await interaction.response.send_message(embed=embed, view=view)

# ===== END COMMAND =====
@tree.command(name="end", description="End current convoy session")
async def end(interaction: discord.Interaction):
    global startup_active, startup_start_time
    if not startup_active:
        await interaction.response.send_message("No active convoy to end.", ephemeral=True)
        return
    host = startup_active["host"]
    duration = datetime.datetime.utcnow() - startup_start_time
    reactions_count = len(startup_messages)

    # Delete startup and link messages
    try:
        await startup_active["message"].delete()
    except:
        pass

    startup_active = None
    startup_start_time = None
    startup_messages.clear()

    embed = discord.Embed(
        title="CONVOY CONCLUSION",
        description=(
            f"We appreciate everyone who participated. A 15 minute convoy cooldown is active.\n"
            f"Keep on the lookout for the next convoy!\n\n"
            f"Host: {host.mention}\n"
            f"Duration: {str(duration).split('.')[0]}\n"
            f"Participants: {reactions_count}"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    embed.set_image(url=BANNER_IMAGE)
    embed.set_thumbnail(url=host.display_avatar.url)
    await interaction.response.send_message(embed=embed)

    # Log session
    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)
    await log_channel.send(embed=embed)

# ===== INFO COMMAND =====
@tree.command(name="info", description="Bot info")
async def info(interaction: discord.Interaction):
    uptime = datetime.datetime.utcnow() - bot_launch_time
    ping_ms = round(bot.latency * 1000)
    crash_risks = ["negligible", "Very unlikely", "Unlikely", "Even", "Likely", "Very likely"]
    risk = random.choice(crash_risks)

    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"Prefix: `>`\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Ping: {ping_ms}ms\n"
            f"Latency: {ping_ms}ms\n"
            f"Status: Online\n"
            f"Risk of crash: {risk}"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    await interaction.response.send_message(embed=embed)

# ===== FEEDBACK MODAL =====
class FeedbackModal(ui.Modal, title="Give Feedback"):
    rating = ui.TextInput(label="Rating (1-5)", placeholder="Enter number 1-5", max_length=1)
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph, placeholder="Your feedback here")

    def __init__(self, host):
        super().__init__()
        self.host = host

    async def on_submit(self, interaction: discord.Interaction):
        channel = bot.get_channel(FEEDBACK_CHANNEL)
        embed = discord.Embed(
            title="CONVOY FEEDBACK",
            description=(
                f"Feedback by {interaction.user.mention}\n"
                f"Host: {self.host.mention}\n"
                f"Rating: {self.rating.value}\n"
                f"Feedback: {self.feedback.value}"
            ),
            color=0x87CEFA
        )
        embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
        await channel.send(embed=embed)
        await interaction.response.send_message("Feedback submitted!", ephemeral=True)

@tree.command(name="feedback", description="Give feedback to host")
async def feedback(interaction: discord.Interaction):
    if not startup_active:
        await interaction.response.send_message("No active convoy to give feedback for.", ephemeral=True)
        return
    await interaction.response.send_modal(FeedbackModal(startup_active["host"]))

# ===== Bot Run =====
bot.run(os.getenv("TOKEN"))
