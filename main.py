import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import os
import random

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=">", intents=intents)

# -------- GLOBAL DATA --------

startup_active = False
startup_host = None
startup_message = None
link_message = None
startup_reactors = set()
startup_time = None

bot_start_time = datetime.datetime.utcnow()

# -------- IDs --------

NOTIFY_ROLE = 1480656237027660046
WELCOME_CHANNEL = 1471452865796116576
SESSION_LOG_CHANNEL = 1481568871679787088
FEEDBACK_CHANNEL = 1481568923504611439

# -------- IMAGES --------

FOOTER_ICON = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png"

STARTUP_BANNER = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"

LINK_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965398411968512/Convoy_5_1.png"

# -------- READY --------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} ready")

# -------- WELCOME --------

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL)

    embed = discord.Embed(
        title="WELCOME TO GREENVILLE MAFIA CORPORATION",
        description=f"Welcome {member.mention}!",
        color=0x87CEFA
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=STARTUP_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    await channel.send(embed=embed)

# -------- SAY COMMAND --------

@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)

# -------- REACTION TRACKING --------

@bot.event
async def on_raw_reaction_add(payload):

    global startup_reactors

    if payload.message_id == getattr(startup_message, "id", None):

        if str(payload.emoji) == "✅":

            startup_reactors.add(payload.user_id)

# -------- STARTUP --------

@bot.tree.command(name="startup")

async def startup(interaction: discord.Interaction):

    global startup_active
    global startup_host
    global startup_message
    global startup_reactors
    global startup_time

    if startup_active:

        await interaction.response.send_message(
            "A convoy session is already active.",
            ephemeral=True
        )
        return

    startup_active = True
    startup_host = interaction.user
    startup_reactors = set()
    startup_time = datetime.datetime.utcnow()

    embed = discord.Embed(

        title="GREENVILLE MAFIA CORPORATION STARTUP",

        description=(

            f"A Convoy is currently being setup by {interaction.user.mention}. "
            f"Please read through our "
            f"**[convoy rules]"
            f"(https://discord.com/channels/1441901639739904125/1481562585781239969)** "
            f"before attending.\n\n"

            f"If you are willing to attend, please react with **✅** below.\n\n"

            f"-# Hope to see you there!"

        ),

        color=0x87CEFA
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=STARTUP_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed
    )

    startup_message = await interaction.original_response()
    await startup_message.add_reaction("✅")

# -------- LINK VIEW --------

class LinkView(ui.View):

    def __init__(self, url):
        super().__init__(timeout=None)
        self.url = url

    @ui.button(label="Join Private Server", style=discord.ButtonStyle.primary)

    async def join(self, interaction: discord.Interaction, button: ui.Button):

        if interaction.user.id not in startup_reactors:

            await interaction.response.send_message(
                "You must react to the startup message first.",
                ephemeral=True
            )
            return

        await interaction.response.send_message(self.url, ephemeral=True)

# -------- LINK --------

@bot.tree.command(name="link")

async def link(interaction: discord.Interaction, url: str):

    global link_message

    if not startup_active:

        await interaction.response.send_message(
            "No active convoy.",
            ephemeral=True
        )
        return

    if interaction.user != startup_host:

        await interaction.response.send_message(
            "Only the host can release the link.",
            ephemeral=True
        )
        return

    embed = discord.Embed(

        title="SESSION RELEASE",

        description=(

            f"Thank you for your patience. {interaction.user.mention} has released the session link. "
            f"Please ensure you have read through all of our "
            f"**[convoy rules]"
            f"(https://discord.com/channels/1441901639739904125/1481562585781239969)** "
            f"before continuing.\n\n"

            f"We ask of you to maintain full respect and patience with hosts, members & staff. "
            f"If you have any issues joining, we suggest you check your privacy settings. "
            f"If all seems fine, ping the host in "
            f"**[convoy chat]"
            f"(https://discord.com/channels/1441901639739904125/1474109435751305286)** "
            f"for assistance.\n\n"

            f"-# Most importantly, enjoy the convoy. We are always here to help if needed."

        ),

        color=0x87CEFA
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=LINK_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    view = LinkView(url)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        view=view
    )

    link_message = await interaction.original_response()

# -------- FEEDBACK MODAL --------

class FeedbackModal(ui.Modal, title="Convoy Feedback"):

    rating = ui.TextInput(label="Rating (1-5)")
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):

        channel = bot.get_channel(FEEDBACK_CHANNEL)

        embed = discord.Embed(
            title="NEW CONVOY FEEDBACK",
            description=f"User: {interaction.user.mention}",
            color=0x87CEFA
        )

        embed.add_field(name="Rating", value=self.rating.value)
        embed.add_field(name="Feedback", value=self.feedback.value)

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "Feedback submitted.",
            ephemeral=True
        )

# -------- END VIEW --------

class EndView(ui.View):

    @ui.button(label="Give Feedback", style=discord.ButtonStyle.secondary)

    async def feedback(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.send_modal(FeedbackModal())

# -------- END COMMAND --------

@bot.tree.command(name="end")

async def end(interaction: discord.Interaction):

    global startup_active

    if not startup_active:

        await interaction.response.send_message(
            "No active convoy.",
            ephemeral=True
        )
        return

    duration = datetime.datetime.utcnow() - startup_time

    try:
        await startup_message.delete()
    except:
        pass

    try:
        await link_message.delete()
    except:
        pass

    embed = discord.Embed(

        title="CONVOY CONCLUSION",

        description=(
            f"Hosted by {startup_host.mention}\n"
            f"Duration: {str(duration).split('.')[0]}"
        ),

        color=0x87CEFA
    )

    embed.set_thumbnail(url=startup_host.display_avatar.url)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    view = EndView()

    await interaction.response.send_message(embed=embed, view=view)

    # -------- LOG SESSION --------

    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)

    await log_channel.send(embed=embed)

    startup_active = False

# -------- INFO --------

@bot.tree.command(name="info")

async def info(interaction: discord.Interaction):

    uptime = datetime.datetime.utcnow() - bot_start_time
    ping = round(bot.latency * 1000)

    risks = [
        "negligible",
        "Very unlikely",
        "Unlikely",
        "Even",
        "Likely",
        "Very likely"
    ]

    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"Prefix: `>`\n"
            f"Uptime: {str(uptime).split('.')[0]}\n"
            f"Ping: {ping}ms\n"
            f"Status: Online\n"
            f"Crash Risk: {random.choice(risks)}"
        ),
        color=0x87CEFA
    )

    await interaction.response.send_message(embed=embed)

bot.run(TOKEN)
