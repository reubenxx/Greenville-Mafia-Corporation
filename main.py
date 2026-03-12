import discord
import os
from discord.ext import commands
from discord import app_commands, ui, Interaction
from typing import List

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439

# ===== Allowed Roles =====
COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]
STARTUP_ROLE = 1479832999435440178
LINK_NOTIFY_ROLE = 1480656237027660046

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

# ===== Bot Setup =====
bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

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

# ===== Say Command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_ROLE_IDS = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)

# ===== Convoy System =====
active_convoy_reactors = {}  # message_id -> set(user_ids)

class FeedbackModal(ui.Modal, title="Convoy Feedback"):
    rating = ui.TextInput(label="Rating (1-5)", placeholder="Enter a number from 1 to 5")
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph, placeholder="Your feedback here")

    async def on_submit(self, interaction: Interaction):
        channel = bot.get_channel(FEEDBACK_CHANNEL)
        await channel.send(f"**Rating:** {self.rating.value}\n**Feedback:** {self.feedback.value}\nFrom: {interaction.user.mention}")
        await interaction.response.send_message("Thanks for your feedback!", ephemeral=True)

class LinkButton(ui.View):
    def __init__(self, url: str, allowed_users: List[int]):
        super().__init__()
        self.url = url
        self.allowed_users = allowed_users
        self.add_item(ui.Button(label="Link", url=url))

# ===== Slash Commands =====
@tree.command(name="startup", description="Start a convoy session")
@app_commands.checks.has_role(STARTUP_ROLE)
async def startup(interaction: Interaction, participants: int):
    if participants < 3 or participants > 50:
        await interaction.response.send_message("Number of participants must be between 3-50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(
            f"A convoy is currently being hosted by {interaction.user.mention}. "
            "Please react if you are intending to join. We ask you kindly review our "
            "**[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
            "If you are affected by the **Roblox Chat Ban**, feel free to talk in our "
            "[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    msg = await interaction.channel.send(content=f"<@&{LINK_NOTIFY_ROLE}>", embed=embed)
    await msg.add_reaction("✅")
    active_convoy_reactors[msg.id] = set()
    await interaction.response.send_message("Convoy started!", ephemeral=True)

@tree.command(name="link", description="Send convoy link")
@app_commands.checks.has_any_roles(*COMMAND_ROLES)
async def link(interaction: Interaction, url: str):
    # find the active startup message for this channel
    channel = interaction.channel
    if not active_convoy_reactors:
        await interaction.response.send_message("No active convoy to link.", ephemeral=True)
        return

    # allow all users who reacted with ✅
    allowed_users = set()
    for msg_id, users in active_convoy_reactors.items():
        allowed_users.update(users)

    embed = discord.Embed(
        title="Convoy Release",
        description=(
            "The convoy link has been released! If you reacted, please join via the button below. "
            "If there are any issues, ping the host in [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    view = LinkButton(url, list(allowed_users))
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Convoy link sent!", ephemeral=True)

@tree.command(name="end", description="End a convoy session")
@app_commands.checks.has_any_roles(*COMMAND_ROLES)
async def end(interaction: Interaction):
    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            "We appreciate everyone who participated in the event. "
            "A 15 minute convoy cooldown is currently active. Keep on the lookout for the next convoy.\n\n"
            "Want to give feedback to hosts for improved sessions? Click on the button below."
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    view = ui.View()
    view.add_item(ui.Button(label="Feedback", style=discord.ButtonStyle.primary, custom_id="feedback_modal"))
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Convoy ended!", ephemeral=True)

@bot.event
async def on_raw_reaction_add(payload):
    if payload.emoji.name != "✅":
        return
    if payload.message_id in active_convoy_reactors:
        active_convoy_reactors[payload.message_id].add(payload.user_id)

@bot.event
async def on_interaction(interaction: Interaction):
    if interaction.type == discord.InteractionType.component:
        if interaction.data["custom_id"] == "feedback_modal":
            await interaction.response.send_modal(FeedbackModal())

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
