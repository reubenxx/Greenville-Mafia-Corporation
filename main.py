import discord
from discord.ext import commands
from discord import app_commands, ui
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

# ===== Banner =====
CONVOY_BANNER = "https://media.discordapp.net/attachments/1467783372469178442/1481896699763888270/Convoy_2.png"

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

# ===== Session Data =====
session_active = False
session_host = None
session_start = None
startup_message = None
release_message = None


def convoy_embed(title, description):
    embed = discord.Embed(
        title=title,
        description=description,
        color=0x87CEFA
    )
    embed.set_image(url=CONVOY_BANNER)
    return embed


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


@bot.command()
async def say(ctx, *, message: str):

    if not any(role.id in ALLOWED_COMMAND_ROLES for role in ctx.author.roles):
        await ctx.send("No permission.", delete_after=5)
        return

    await ctx.message.delete()
    await ctx.send(message)


# ==================================================
# STARTUP
# ==================================================

@tree.command(name="startup", description="Start convoy session")
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
            "Player count must be between **3 and 50**.",
            ephemeral=True
        )
        return

    session_active = True
    session_host = interaction.user
    session_start = time.time()

    embed = convoy_embed(
        "Greenville Mafia Corporation Startup",
        f"A Convoy is currently being setup by {interaction.user.mention}. Please read through our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending. If you are affected by any form of **in-game chat restriction**, please communicate in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
        f"If you are willing to attend, please react with the **checkmark** below. If there are any issues joining or in session, please ping the host in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
        f"-# Of course, please remain respectful and patient with hosts and members. Most importantly, enjoy your time in the **convoy!**\n\n"
        f"-# Hope to see you there!"
    )

    await interaction.response.send_message(
        content=f"<@&{NOTIFY_ROLE}>",
        embed=embed
    )

    startup_message = await interaction.original_response()

    await startup_message.add_reaction("✅")


# ==================================================
# RELEASE
# ==================================================

@tree.command(name="release", description="Release convoy server link")
@app_commands.describe(link="Roblox private server link")
async def release(interaction: discord.Interaction, link: str):

    global release_message

    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message(
            "You cannot run this command.",
            ephemeral=True
        )
        return

    embed = convoy_embed(
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

    release_message = await interaction.original_response()


# ==================================================
# FEEDBACK MODAL
# ==================================================

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

        embed = convoy_embed(
            "Convoy Feedback",
            f"**Host:** {session_host.mention if session_host else 'Unknown'}\n"
            f"**Feedback From:** {interaction.user.mention}\n\n"
            f"**Rating:** {self.rating.value}\n"
            f"**Feedback:** {self.feedback.value}"
        )

        await channel.send(embed=embed)

        await interaction.response.send_message(
            "Feedback submitted.",
            ephemeral=True
        )


class FeedbackView(ui.View):

    @ui.button(label="Give Feedback", style=discord.ButtonStyle.primary)
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FeedbackModal())


# ==================================================
# END
# ==================================================

@tree.command(name="end", description="End convoy session")
async def end(interaction: discord.Interaction):

    global session_active
    global session_host
    global session_start
    global startup_message
    global release_message

    if not session_active:
        await interaction.response.send_message(
            "No convoy session is active.",
            ephemeral=True
        )
        return

    if interaction.user != session_host:
        await interaction.response.send_message(
            "Only the convoy host can end the session.",
            ephemeral=True
        )
        return

    duration = int(time.time() - session_start)

    minutes = duration // 60
    seconds = duration % 60

    reaction_count = 0

    if startup_message:

        msg = await interaction.channel.fetch_message(startup_message.id)

        for reaction in msg.reactions:
            if str(reaction.emoji) == "✅":
                reaction_count = reaction.count - 1

        try:
            await startup_message.delete()
        except:
            pass

    if release_message:
        try:
            await release_message.delete()
        except:
            pass

    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)

    log_embed = convoy_embed(
        "Convoy Session Logged",
        f"**Host:** {session_host.mention}\n"
        f"**Duration:** {minutes}m {seconds}s\n"
        f"**Participants:** {reaction_count}"
    )

    await log_channel.send(embed=log_embed)

    end_embed = convoy_embed(
        "Convoy Ended",
        "Thank you for attending.\n\nPlease leave feedback below."
    )

    await interaction.response.send_message(
        embed=end_embed,
        view=FeedbackView()
    )

    session_active = False
    session_host = None
    session_start = None
    startup_message = None
    release_message = None


bot.run(os.getenv("TOKEN"))
