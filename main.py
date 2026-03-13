import discord
from discord import app_commands, ui
from discord.ext import commands
import os
import time

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439
SESSION_LOG_CHANNEL = 1481568871679787088

# ===== Roles =====
ALLOWED_COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]
STARTUP_ROLE = 1479832999435440178
NOTIFY_ROLE = 1480656237027660046

# ===== Convoy Image =====
CONVOY_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

# ===== Session State =====
session_active = False
session_host = None
session_start = None
startup_message = None


# ===== Embed Helper =====
def clean_embed(title, description):

    embed = discord.Embed(
        title=title,
        description=description,
        color=0x87CEFA
    )

    embed.set_footer(
        text="Greenville Mafia Corporation",
        icon_url=CONVOY_IMAGE
    )

    return embed


# ===== Ready =====
@bot.event
async def on_ready():
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Greenville Mafia Corporation"
        )
    )

    await tree.sync()

    print(f"{bot.user} online.")


# ===== SAY =====
@bot.command()
async def say(ctx, *, message: str):

    if not any(role.id in ALLOWED_COMMAND_ROLES for role in ctx.author.roles):
        await ctx.send("No permission.", delete_after=5)
        return

    await ctx.message.delete()
    await ctx.send(message)


# =================================================
# STARTUP
# =================================================

@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(players="Expected players (3-50)")
async def startup(interaction: discord.Interaction, players: int):

    global session_active
    global session_host
    global session_start
    global startup_message

    if session_active:
        await interaction.response.send_message(
            "A convoy session is already active.",
            ephemeral=True
        )
        return

    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message(
            "You cannot run this command.",
            ephemeral=True
        )
        return

    if players < 3 or players > 50:
        await interaction.response.send_message(
            "Players must be between **3 and 50**.",
            ephemeral=True
        )
        return

    session_active = True
    session_host = interaction.user
    session_start = time.time()

    embed = clean_embed(
        "GVMC Convoy Launch",
        f"A convoy is currently being hosted by {interaction.user.mention}.\n\n"
        f"React with ✅ if you are intending to join.\n\n"
        f"Please review our **convoy rules** before attending.\n\n"
        f"Enjoy your time in **Greenville Mafia Corporation** convoys."
    )

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed
    )

    startup_message = await interaction.original_response()

    await startup_message.add_reaction("✅")


# =================================================
# RELEASE LINK
# =================================================

@tree.command(name="release", description="Release convoy server link")
@app_commands.describe(link="Roblox private server link")
async def release(interaction: discord.Interaction, link: str):

    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message(
            "You cannot run this command.",
            ephemeral=True
        )
        return

    embed = clean_embed(
        "Convoy Server Released",
        "Click the button below to join the convoy server."
    )

    view = ui.View()

    view.add_item(
        ui.Button(
            label="Join Server",
            url=link,
            style=discord.ButtonStyle.link
        )
    )

    await interaction.response.send_message(
        embed=embed,
        view=view
    )


# =================================================
# FEEDBACK MODAL
# =================================================

class FeedbackModal(ui.Modal, title="Convoy Feedback"):

    rating = ui.TextInput(
        label="Rating (1-5)",
        max_length=1
    )

    feedback = ui.TextInput(
        label="Feedback",
        style=discord.TextStyle.paragraph
    )

    async def on_submit(self, interaction: discord.Interaction):

        channel = bot.get_channel(FEEDBACK_CHANNEL)

        embed = clean_embed(
            "Convoy Feedback Submitted",
            f"**Host:** {session_host.mention}\n"
            f"**Feedback From:** {interaction.user.mention}\n\n"
            f"**Rating:** {self.rating.value}\n"
            f"**Feedback:** {self.feedback.value}"
        )

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "Feedback submitted successfully.",
            ephemeral=True
        )


# =================================================
# END SESSION
# =================================================

class FeedbackButton(ui.View):

    @ui.button(label="Give Feedback", style=discord.ButtonStyle.primary)
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):

        await interaction.response.send_modal(FeedbackModal())


@tree.command(name="end", description="End convoy session")
async def end(interaction: discord.Interaction):

    global session_active
    global session_host
    global session_start
    global startup_message

    if not session_active:
        await interaction.response.send_message(
            "No convoy session is active.",
            ephemeral=True
        )
        return

    if interaction.user != session_host:
        await interaction.response.send_message(
            "Only the session host can end the convoy.",
            ephemeral=True
        )
        return

    duration = int(time.time() - session_start)

    minutes = duration // 60
    seconds = duration % 60

    reaction_count = 0

    if startup_message:
        message = await interaction.channel.fetch_message(startup_message.id)

        for reaction in message.reactions:
            if str(reaction.emoji) == "✅":
                reaction_count = reaction.count - 1

    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)

    log_embed = clean_embed(
        "Convoy Session Logged",
        f"**Host:** {session_host.mention}\n"
        f"**Duration:** {minutes}m {seconds}s\n"
        f"**Participants:** {reaction_count}"
    )

    await log_channel.send(embed=log_embed)

    end_embed = clean_embed(
        "Convoy Session Ended",
        "Thanks for attending the convoy.\n\n"
        "Please leave feedback below."
    )

    await interaction.response.send_message(
        embed=end_embed,
        view=FeedbackButton()
    )

    session_active = False
    session_host = None
    session_start = None
    startup_message = None


bot.run(os.getenv("TOKEN"))
# ===== Bot Run =====
bot.run(os.getenv("TOKEN"))
