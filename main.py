```python
import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import os
import random

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.all()
bot = commands.Bot(command_prefix=">", intents=intents)

startup_active = False
startup_host = None
startup_message = None
link_message = None
startup_reactors = set()
startup_time = None

bot_start_time = datetime.datetime.utcnow()

NOTIFY_ROLE = 1480656237027660046
WELCOME_CHANNEL = 1471452865796116576
SESSION_LOG_CHANNEL = 1481568871679787088
FEEDBACK_CHANNEL = 1481568923504611439

FOOTER_ICON = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png"
STARTUP_BANNER = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"
LINK_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965398411968512/Convoy_5_1.png"
END_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965219818373262/Convoy_4_12.png"


@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} online")


@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL)

    embed = discord.Embed(
        title="WELCOME TO GREENVILLE MAFIA CORPORATION",
        description=f"> Welcome {member.mention}! We're glad you're here.",
        color=0x87CEFA
    )

    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=STARTUP_BANNER)

    await channel.send(embed=embed)


@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)


@bot.event
async def on_raw_reaction_add(payload):

    global startup_reactors

    if startup_message and payload.message_id == startup_message.id:

        if str(payload.emoji) == "✅":
            startup_reactors.add(payload.user_id)


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
            f"> A convoy is currently being setup by {interaction.user.mention}. "
            f"Please read the **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"

            f"> If you have an **in-game chat restriction**, communicate in "
            f"[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"

            f"> React with the **checkmark** below if attending. "
            f"If issues occur joining, ping the host in convoy chat.\n\n"

            f"> Please remain respectful and patient with hosts and members. "
            f"Most importantly, enjoy your time in the convoy!"
        ),
        color=0x87CEFA
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=STARTUP_BANNER)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    startup_message = await interaction.original_response()
    await startup_message.add_reaction("✅")


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

        embed = discord.Embed(
            title="Private Server Link",
            description=f"> Click **[here]({self.url})** to join the private server.",
            color=0x87CEFA
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)


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
            f"> Thank you for your patience. {interaction.user.mention} has released the session link.\n\n"

            f"> Please read the **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before continuing.\n\n"

            f"> Maintain respect with hosts, members, and staff. "
            f"If joining issues occur check privacy settings first.\n\n"

            f"> If problems continue ping the host in "
            f"**[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**.\n\n"

            f"> Most importantly enjoy the convoy!"
        ),
        color=0x87CEFA
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=LINK_BANNER)

    view = LinkView(url)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    link_message = await interaction.original_response()


class FeedbackModal(ui.Modal, title="Convoy Feedback"):

    rating = ui.TextInput(label="Rating (1-5)")
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):

        channel = bot.get_channel(FEEDBACK_CHANNEL)

        embed = discord.Embed(
            title="NEW CONVOY FEEDBACK",
            color=0x87CEFA
        )

        embed.add_field(name="User", value=interaction.user.mention)
        embed.add_field(name="Rating", value=self.rating.value)
        embed.add_field(name="Feedback", value=self.feedback.value)

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "Feedback submitted.",
            ephemeral=True
        )


class EndView(ui.View):

    @ui.button(label="Feedback", style=discord.ButtonStyle.secondary)
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.send_modal(FeedbackModal())


@bot.tree.command(name="end")
@app_commands.describe(host_note="Host note for the convoy")

async def end(interaction: discord.Interaction, host_note: str):

    global startup_active

    if not startup_active:
        await interaction.response.send_message(
            "No active convoy.",
            ephemeral=True
        )
        return

    duration = datetime.datetime.utcnow() - startup_time

    try:
        if startup_message:
            await startup_message.delete()
    except:
        pass

    try:
        if link_message:
            await link_message.delete()
    except:
        pass

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            f"> This convoy has **concluded** by {interaction.user.mention}. "
            f"We highly appreciate you for attending.\n\n"

            f"> We host frequently so stay tuned for the next event hosted right here.\n\n"

            f"> Thank you again for your participation. We hope to see you in the future!\n\n"

            f"> **Host Note —** {host_note}\n\n"

            f"> Want to give feedback? Click the **feedback** button below."
        ),
        color=0x87CEFA
    )

    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=END_BANNER)

    view = EndView()

    await interaction.response.send_message(embed=embed, view=view)

    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)

    log_embed = discord.Embed(
        title="Session Logged",
        description=(
            f"Host: {interaction.user.mention}\n"
            f"Duration: {str(duration).split('.')[0]}\n"
            f"Host Note: {host_note}"
        ),
        color=0x87CEFA
    )

    await log_channel.send(embed=log_embed)

    startup_active = False


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
            f"> Prefix: `>` | Ping: {ping}ms\n"
            f"> Uptime: {str(uptime).split('.')[0]}\n"
            f"> Status: Online | Crash Risk: {random.choice(risks)}"
        ),
        color=0x87CEFA
    )

    await interaction.response.send_message(embed=embed)


bot.run(TOKEN)
```
