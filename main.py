# main.py
import discord
from discord.ext import commands
from discord import app_commands, ui
import os
import threading
from flask import Flask

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439
NOTIFY_ROLE = 1480656237027660046

# ===== Roles =====
ALLOWED_SAY_ROLES = [1474121009656500225, 1474116769458421973]
ALLOWED_COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]

# ===== Intents & Bot =====
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

# ===== Dyno-style modlog embed =====
def dyno_embed(action, user, moderator=None, reason="No reason provided"):
    embed = discord.Embed(description=f"**{action}**", color=0x2F3136)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Greenville Mafia Corporation",
                     icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    return embed

# ===== Bot Ready Event =====
@bot.event
async def on_ready():
    await tree.sync()
    activity = discord.Activity(
        type=discord.ActivityType.watching,
        name="Greenville Mafia Corporation"
    )
    await bot.change_presence(activity=activity)
    print(f"{bot.user} is online!")

# ===== Welcome Message =====
@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    log_channel = bot.get_channel(MODLOG_CHANNEL)

    embed = discord.Embed(
        title="Welcome to Greenville Mafia Corporation",
        description=(f"Welcome to __**Greenville Mafia Corporation**__ {member.mention}!\n\n"
                     f"Please read through our **[server rules](https://discord.com/channels/1441901639739904125/1442242436138274826)** to get started.\n\n"
                     f"We appreciate having you here with us at **Greenville Mafia Corporation.**"),
        color=0x87CEFA
    )
    embed.add_field(name="Member Number", value=f"You are **member #{member.guild.member_count}**", inline=False)
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text="Greenville Mafia Corporation",
                     icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")

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

# ===== >say Command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    if not any(role.id in ALLOWED_SAY_ROLES for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)

# ===== Convoy System =====
convoy_reactors = {}

class ConvoyLinkButton(ui.View):
    def __init__(self, url):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Link", url=url, style=discord.ButtonStyle.link))

class ConvoyFeedbackButton(ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ui.Button(label="Give Feedback", custom_id="feedback_btn", style=discord.ButtonStyle.primary))

@tree.command(name="startup", description="Start a convoy")
@app_commands.describe(players="Number of players (3-50)")
async def startup(interaction: discord.Interaction, players: int):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return
    if not 3 <= players <= 50:
        await interaction.response.send_message("Must be between 3 and 50 players.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(f"A convoy is currently being hosted by {interaction.user.mention}. "
                     "Please react if you are intending to join. We ask you kindly review our "
                     "**[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)**."),
        color=0x87CEFA
    )
    embed.add_field(name="Info", value="If you are affected by Roblox Chat Ban, join our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).", inline=False)
    embed.add_field(name="-#", value=f"Most importantly, enjoy your time in **Greenville Mafia Corporation** convoys.", inline=False)
    embed.set_footer(icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png",
                     text="Greenville Mafia Corporation")
    message = await interaction.channel.send(content=f"<@&{NOTIFY_ROLE}>", embed=embed)
    await message.add_reaction("✅")
    convoy_reactors[message.id] = set()

@tree.command(name="link", description="Release the convoy link")
@app_commands.describe(link="Roblox private server link")
async def link(interaction: discord.Interaction, link: str):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return

    # Find the latest startup message in the channel
    messages = await interaction.channel.history(limit=20).flatten()
    for msg in messages:
        if msg.id in convoy_reactors:
            users = convoy_reactors[msg.id]
            view = ConvoyLinkButton(link)
            embed = discord.Embed(
                title="Convoy Release",
                description=(f"The convoy link has been released! If you reacted, please join via the button below. "
                             f"If there are any issues, feel free to ping the host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**."),
                color=0x87CEFA
            )
            embed.set_footer(icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png",
                             text="Greenville Mafia Corporation")
            await interaction.channel.send(embed=embed, view=view)
            break

@tree.command(name="end", description="End the convoy session")
async def end(interaction: discord.Interaction):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("No permission.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=("We appreciate everyone who participated in the event. "
                     "A 15 minute convoy cooldown is currently active. Keep on the lookout for the next convoy."),
        color=0x87CEFA
    )
    embed.set_footer(icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png",
                     text="Greenville Mafia Corporation")
    feedback_view = ConvoyFeedbackButton()
    await interaction.channel.send(embed=embed, view=feedback_view)

# ===== Flask WSGI Keep-Alive =====
app = Flask("")

@app.route("/")
def home():
    return "Bot is running."

def run_flask():
    app.run(host="0.0.0.0", port=8080)

threading.Thread(target=run_flask).start()

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
