import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import os
import sys

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

# ----- IDs & constants -----
NOTIFY_ROLE = 1480656237027660046
WELCOME_CHANNEL = 1471452865796116576
SESSION_LOG_CHANNEL = 1481568871679787088
FEEDBACK_CHANNEL = 1481568923504611439
KILL_ROLE = 1481266824917287124

FOOTER_ICON = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png"
STARTUP_BANNER = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"
LINK_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965398411968512/Convoy_5_1.png"
END_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965219818373262/Convoy_4_12.png"
WELCOME_BANNER = "https://cdn.discordapp.com/attachments/1467783372469178442/1482361429188284606/Welcome_1.png"

bot_start_time = datetime.datetime.utcnow()

# -------- EVENTS --------
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name="Managing Greenville Mafia Corporation"))
    print(f"{bot.user} ready")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    embed = discord.Embed(
        title="Welcome to __**Greenville Mafia Corporation**__  <:blueheart:1483008124024524820>",
        description=(
            "┃ <:gvmc_star:1480630313234333758> We warmly welcome you! "
            "Please read **[server guidelines](https://discord.com/channels/1441901639739904125/1442242436138274826)**. "
            "For support, reach staff **[here](https://discord.com/channels/1441901639739904125/1443980437184577556)**.\n\n"
            "<:verified:1483008933365813330> Remember to verify **[here](https://discord.com/channels/1441901639739904125/1471452917163884738)**."
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=WELCOME_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)
    await channel.send(content=member.mention, embed=embed)

# -------- SAY COMMAND --------
@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)

# -------- REACTION TRACKING --------
@bot.event
async def on_raw_reaction_add(payload):
    global startup_reactors
    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:blueheart:1483008124024524820>":
            startup_reactors.add(payload.user_id)

@bot.event
async def on_raw_reaction_remove(payload):
    global startup_reactors
    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:blueheart:1483008124024524820>":
            startup_reactors.discard(payload.user_id)

# -------- STARTUP COMMAND --------
@bot.tree.command(name="startup")
async def startup(interaction: discord.Interaction):
    global startup_active, startup_host, startup_message, startup_reactors, startup_time
    if startup_active:
        await interaction.response.send_message("A convoy session is already active.", ephemeral=True)
        return

    startup_active = True
    startup_host = interaction.user
    startup_reactors = set()
    startup_time = datetime.datetime.utcnow()

    embed = discord.Embed(
        title="Greenville Mafia Corporation Convoy Startup <:announcement:1480640464737800253>",
        description=(
            f"{interaction.user.mention} is currently __**hosting a Convoy**__. "
            "Please ensure that you have your Roblox privacy settings set to __**everyone**__. "
            "If they're not, you may be unable to join the session. During this time, please review our "
            "**[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before proceeding.\n\n"
            "┃ <:dot:1480643720687915058> To confirm your presence, please react with the "
            "<:blueheart:1483008124024524820> below. You will be pinged in this channel again when the "
            "session releases. If there are any issues with joining or other session related issues, "
            "please ping the host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)** "
            "and they will assist you accordingly.\n\n"
            f"┃ <:dot:1480643720687915058> The host has requested __**{required_reactions}+**__ reactions before this session commences."
        ),
        color=0x87CEFA
    )

    embed.set_image(url=STARTUP_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )

    startup_message = await interaction.original_response()
    await startup_message.add_reaction("<:blueheart:1483008124024524820>")

# -------- LINK COMMAND --------
class LinkView(ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.url = url

    @ui.button(label="Join Private Server", style=discord.ButtonStyle.primary)
    async def join(self, interaction: discord.Interaction, button: ui.Button):
        if not startup_active:
            await interaction.response.send_message("No active convoy.", ephemeral=True)
            return

        # Only allow users who have reacted and meet required reaction count
        if interaction.user.id not in startup_reactors:
            await interaction.response.send_message(
                "You must react to the startup message first.", ephemeral=True
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
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return
    if interaction.user != startup_host:
        await interaction.response.send_message("Only the host can release the link.", ephemeral=True)
        return

    embed = discord.Embed(
        title="SESSION RELEASE",
        description=(
            f"> {interaction.user.mention} has released the session link.\n"
            "Please read all **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)**.\n"
            "Respect hosts, members & staff. Ping host in "
            "**[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)** if needed."
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
        view=view,
        allowed_mentions=discord.AllowedMentions(roles=True)
    )
    link_message = await interaction.original_response()

# -------- FEEDBACK SYSTEM --------
class FeedbackModal(ui.Modal, title="Convoy Feedback"):
    rating = ui.TextInput(label="Rating (1-5)")
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph)

    async def on_submit(self, interaction: discord.Interaction):
        channel = bot.get_channel(FEEDBACK_CHANNEL)
        embed = discord.Embed(title="NEW CONVOY FEEDBACK", color=0x87CEFA)
        embed.add_field(name="User", value=interaction.user.mention)
        embed.add_field(name="Rating", value=self.rating.value)
        embed.add_field(name="Feedback", value=self.feedback.value)
        await channel.send(embed=embed)
        await interaction.response.send_message("Feedback submitted.", ephemeral=True)

class EndView(ui.View):
    @ui.button(label="Feedback", style=discord.ButtonStyle.secondary)
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FeedbackModal())

# -------- END COMMAND --------
@bot.tree.command(name="end")
@app_commands.describe(host_note="Host note for the convoy")
async def end(interaction: discord.Interaction, host_note: str):
    global startup_active
    if not startup_active:
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return

    duration = datetime.datetime.utcnow() - startup_time
    try: await startup_message.delete()
    except: pass
    try: await link_message.delete()
    except: pass

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            f"> This convoy has **concluded** by {interaction.user.mention}.\n"
            f"> Thank you for attending.\n\n"
            f"> **Host Note:** {host_note}\n"
            f"> Click **feedback** below to submit feedback."
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_image(url=END_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    view = EndView()
    await interaction.response.send_message(embed=embed, view=view)

    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)
    log_embed = discord.Embed(
        title="Session Logged",
        description=f"Host: {interaction.user.mention}\nDuration: {str(duration).split('.')[0]}\nHost Note: {host_note}",
        color=0x87CEFA
    )
    await log_channel.send(embed=log_embed)
    startup_active = False

# -------- INFO COMMAND --------
@bot.tree.command(name="info")
async def info(interaction: discord.Interaction):
    uptime = datetime.datetime.utcnow() - bot_start_time
    api_ping = round(bot.latency * 1000)
    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"> Developer: Reuben2k11\n"
            f"> Prefix: `>`\n"
            f"> Uptime: {str(uptime).split('.')[0]}\n"
            f"> Ping: {api_ping}ms\n"
            f"> Discord.py Version: {discord.__version__}\n"
            f"> Status: Online"
        ),
        color=0x87CEFA
    )
    await interaction.response.send_message(embed=embed)

# -------- KILL COMMAND --------
@bot.tree.command(name="kill")
async def kill(interaction: discord.Interaction):
    if KILL_ROLE not in [role.id for role in interaction.user.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    await interaction.response.send_message("Shutting down...", ephemeral=True)
    sys.exit()

# -------- RUN BOT --------
bot.run(TOKEN)
