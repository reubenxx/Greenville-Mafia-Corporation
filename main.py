import discord
import os
from discord.ext import commands
from discord import app_commands, Interaction, ui

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439

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
tree = bot.tree  # For slash commands

# ===== Keep track of reactions for /startup =====
convoy_reactors = {}  # {message_id: set(user_ids)}

# ===== Bot Ready Event =====
@bot.event
async def on_ready():
    activity = discord.Activity(type=discord.ActivityType.watching,
                                name="Greenville Mafia Corporation")
    await bot.change_presence(activity=activity)
    await tree.sync()
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
        description=(f"Welcome to __**Greenville Mafia Corporation**__ {member.mention}!\n\n"
                     f"Please read through our **[server rules](https://discord.com/channels/1441901639739904125/1442242436138274826)** to get started.\n\n"
                     f"We appreciate having you here with us at **Greenville Mafia Corporation.**"),
        color=0x87CEFA
    )
    embed.add_field(name="Member Number", value=f"You are **member #{member.guild.member_count}** in this server.", inline=False)
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

# ===== >say Command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    ALLOWED_ROLE_IDS = [1474121009656500225, 1474116769458421973]
    if not any(role.id in ALLOWED_ROLE_IDS for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return
    await ctx.message.delete()
    await ctx.send(message)

# ===== Feedback Modal =====
class FeedbackModal(ui.Modal, title="Give Feedback"):
    rating = ui.TextInput(label="Rating (1-5)", placeholder="Enter a number from 1 to 5", max_length=1)
    feedback = ui.TextInput(label="Feedback", style=discord.TextStyle.paragraph, placeholder="Your feedback here")

    async def on_submit(self, interaction: Interaction):
        channel = bot.get_channel(FEEDBACK_CHANNEL)
        embed = discord.Embed(title="Convoy Feedback", color=0x87CEFA)
        embed.add_field(name="Rating", value=self.rating.value)
        embed.add_field(name="Feedback", value=self.feedback.value)
        embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
        await channel.send(embed=embed)
        await interaction.response.send_message("Feedback submitted! ✅", ephemeral=True)

# ===== /startup Command =====
@tree.command(name="startup", description="Start a convoy session")
@app_commands.describe(participants="Number of participants (3-50)")
async def startup(interaction: Interaction, participants: int):
    if not any(role.id == STARTUP_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return
    if participants < 3 or participants > 50:
        await interaction.response.send_message("Participants must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(title="GVMC Convoy Launch",
                          description=(f"A convoy is currently being hosted by {interaction.user.mention}. "
                                       f"Please react if you are intending to join. We ask you kindly review our **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
                                       f"If you are affected by the **Roblox Chat Ban**, feel free to talk in our [convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286).\n\n"
                                       f"-# Most importantly, enjoy your time in **Greenville Mafia Corporation** convoys."),
                          color=0x87CEFA)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")
    
    msg = await interaction.response.send_message(content=f"<@&{NOTIFY_ROLE}>", embed=embed, fetch_response=True)
    convoy_reactors[msg.id] = set()

    # Add white checkmark reaction automatically
    await msg.add_reaction("✅")

# ===== /link Command =====
@tree.command(name="link", description="Release the convoy link")
@app_commands.describe(link="Roblox private server link")
async def link(interaction: Interaction, link: str):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return

    # Find last startup message
    if not convoy_reactors:
        await interaction.response.send_message("No active convoy found.", ephemeral=True)
        return

    last_msg_id = list(convoy_reactors.keys())[-1]
    embed = discord.Embed(title="Convoy Release",
                          description="The convoy link has been released! If you reacted, please join via the button below. If there are any issues, feel free to ping the host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**.",
                          color=0x87CEFA)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")

    # Button
    class LinkButton(ui.View):
        @ui.button(label="Link", url=link, style=discord.ButtonStyle.link)
        async def link_button(self, interaction: Interaction, button: ui.Button):
            pass

    await interaction.response.send_message(embed=embed, view=LinkButton())

# ===== /end Command =====
@tree.command(name="end", description="End the convoy session")
async def end(interaction: Interaction):
    if not any(role.id in ALLOWED_COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission.", ephemeral=True)
        return

    # Delete previous startup/link messages if possible
    for msg_id in convoy_reactors.keys():
        try:
            msg = await interaction.channel.fetch_message(msg_id)
            await msg.delete()
        except:
            pass
    convoy_reactors.clear()

    embed = discord.Embed(title="Convoy Conclusion",
                          description="We appreciate everyone who participated in the event. A 15 minute convoy cooldown is currently active. Keep on the lookout for the next convoy as we host them frequently.\n\nWant to give feedback to hosts for improved sessions? Click the button below.",
                          color=0x87CEFA)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url="https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png")

    class FeedbackButton(ui.View):
        @ui.button(label="Give Feedback", style=discord.ButtonStyle.primary)
        async def feedback_button(self, interaction: Interaction, button: ui.Button):
            await interaction.response.send_modal(FeedbackModal())

    await interaction.response.send_message(embed=embed, view=FeedbackButton())

# ===== Run Bot =====
bot.run(os.getenv("TOKEN"))
