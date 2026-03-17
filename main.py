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

# ----- IDs -----
NOTIFY_ROLE = 1480656237027660046
WELCOME_CHANNEL = 1471452865796116576
SESSION_LOG_CHANNEL = 1481568871679787088
FEEDBACK_CHANNEL = 1481568923504611439
KILL_ROLE = 1481266824917287124

# ----- Assets -----
FOOTER_ICON = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png"
STARTUP_BANNER = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"
LINK_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965398411968512/Convoy_5_1.png"
END_BANNER = "https://media.discordapp.net/attachments/1451418684752134146/1481965219818373262/Convoy_4_12.png"

WELCOME_THUMB = "https://media.discordapp.net/attachments/1451418684752134146/1483404347441156166/Untitled_design_1024x1024.png"

bot_start_time = datetime.datetime.utcnow()

# --------------------------------------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Watching 'Greenville Mafia Corporation'"
        )
    )
    print(f"{bot.user} ready")

# --------------------------------------------------
# WELCOME SYSTEM
# --------------------------------------------------

@bot.event
async def on_member_join(member):

    channel = bot.get_channel(WELCOME_CHANNEL)

    embed = discord.Embed(
        title="<a:welcome:1483008041413509141> Welcome to __**Greenville Mafia Corporation**__ <a:welcome:1483008041413509141>",
        color=0x87CEFA,
        description=(
            "> <a:gvmc_heart:1480637190685069472> Welcome to __**Greenville Mafia Corporation!**__! "
            "We are honored to have you here with us! Before you venture off into **GVMC**, "
            "please **[verify](https://discord.com/channels/1441901639739904125/1471452917163884738)** "
            "to gain full access to our server.\n\n"

            "> <a:pulsatingheart:1478774678645637160> We host daily Convoys, Events, "
            "Occasional Giveaways and other fun surprises! We look forward to seeing you "
            "participate in the full life of __**Greenville Mafia Corporation**__.\n\n"

            "If you require assistance please contact staff "
            "**[here](https://discord.com/channels/1441901639739904125/1443980437184577556)**."
        )
    )

    embed.set_thumbnail(url=WELCOME_THUMB)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    await channel.send(content=member.mention, embed=embed)

# --------------------------------------------------
# SAY COMMAND
# --------------------------------------------------

@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)

# --------------------------------------------------
# REACTION TRACKING
# --------------------------------------------------

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

# --------------------------------------------------
# STARTUP COMMAND
# --------------------------------------------------

@bot.tree.command(name="startup", description="Start a convoy session.")
@app_commands.describe(reactions="Required reactions before link release")

async def startup(interaction: discord.Interaction, reactions: int):

    global startup_active, startup_host, startup_message
    global startup_reactors, startup_time, required_reactions

    if startup_active:
        await interaction.response.send_message(
            "A convoy session is already active.",
            ephemeral=True
        )
        return

    required_reactions = reactions

    startup_active = True
    startup_host = interaction.user
    startup_reactors = set()
    startup_time = datetime.datetime.utcnow()

    embed = discord.Embed(
        title="Greenville Mafia Corporation Convoy Startup <:announcement:1480640464737800253>",
        description=(
            f"{interaction.user.mention} is currently __**hosting a Convoy**__.\n\n"

            "┃ <:dot:1480643720687915058> React with "
            "<:blueheart:1483008124024524820> to confirm attendance.\n\n"

            f"┃ <:dot:1480643720687915058> The host has requested "
            f"__**{required_reactions}+**__ reactions before this session commences."
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

# --------------------------------------------------
# LINK COMMAND
# --------------------------------------------------

class LinkView(ui.View):

    def __init__(self, url):
        super().__init__(timeout=None)
        self.url = url

    @ui.button(label="Join Private Server", style=discord.ButtonStyle.primary)
    async def join(self, interaction: discord.Interaction, button: ui.Button):

        if interaction.user.id not in startup_reactors:
            await interaction.response.send_message(
                "React to the startup message first.",
                ephemeral=True
            )
            return

        embed = discord.Embed(
            title="Private Server Link",
            description=f"> Click **[here]({self.url})** to join.",
            color=0x87CEFA
        )

        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="link", description="Release the private server link.")

async def link(interaction: discord.Interaction, url: str):

    global link_message

    if interaction.user != startup_host:
        await interaction.response.send_message(
            "Only the host can release the link.",
            ephemeral=True
        )
        return

    if len(startup_reactors) < required_reactions:
        await interaction.response.send_message(
            f"Need {required_reactions} reactions first.",
            ephemeral=True
        )
        return

    embed = discord.Embed(
        title="SESSION RELEASE",
        description=f"{interaction.user.mention} has released the session link.",
        color=0x87CEFA
    )

    embed.set_image(url=LINK_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    view = LinkView(url)

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed,
        view=view
    )

    link_message = await interaction.original_response()

# --------------------------------------------------
# END COMMAND
# --------------------------------------------------

@bot.tree.command(name="end", description="End the convoy session.")
@app_commands.describe(host_note="Host note")

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
        await startup_message.delete()
    except:
        pass

    try:
        await link_message.delete()
    except:
        pass

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            f"> This convoy has **concluded** by {interaction.user.mention}\n\n"
            f"> Host Note: {host_note}"
        ),
        color=0x87CEFA
    )

    embed.set_image(url=END_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)

    await interaction.response.send_message(embed=embed)

    log = bot.get_channel(SESSION_LOG_CHANNEL)

    log_embed = discord.Embed(
        title="Session Logged",
        description=f"Host: {interaction.user.mention}\nDuration: {str(duration).split('.')[0]}",
        color=0x87CEFA
    )

    await log.send(embed=log_embed)

    startup_active = False

# --------------------------------------------------
# MEMBER COUNT
# --------------------------------------------------

@bot.tree.command(name="members", description="Show server member count.")

async def members(interaction: discord.Interaction):

    guild = interaction.guild
    now = datetime.datetime.now().strftime("%B %d %Y • %I:%M %p")

    embed = discord.Embed(
        title="Member",
        description=f"**{guild.member_count}**",
        color=0x87CEFA
    )

    embed.set_footer(text=now)

    await interaction.response.send_message(embed=embed)

# --------------------------------------------------
# INFO COMMAND
# --------------------------------------------------

@bot.tree.command(name="info")

async def info(interaction: discord.Interaction):

    uptime = datetime.datetime.utcnow() - bot_start_time

    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"> Developer: Reuben2k11\n"
            f"> Prefix: >\n"
            f"> Uptime: {str(uptime).split('.')[0]}\n"
            f"> Ping: {round(bot.latency*1000)}ms"
        ),
        color=0x87CEFA
    )

    await interaction.response.send_message(embed=embed)

# --------------------------------------------------
# KILL COMMAND
# --------------------------------------------------

@bot.tree.command(name="kill")

async def kill(interaction: discord.Interaction):

    if KILL_ROLE not in [r.id for r in interaction.user.roles]:
        await interaction.response.send_message(
            "Not authorized.",
            ephemeral=True
        )
        return

    await interaction.response.send_message(
        "Shutting down...",
        ephemeral=True
    )

    sys.exit()

# --------------------------------------------------

bot.run(TOKEN)
