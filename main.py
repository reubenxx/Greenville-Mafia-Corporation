import discord
import os
import asyncio
from discord.ext import commands
from discord import app_commands

# ===== Channels =====
WELCOME_CHANNEL = 1471452865796116576
MODLOG_CHANNEL = 1474350885508350044
FEEDBACK_CHANNEL = 1481568923504611439

# ===== Role IDs =====
ALLOWED_SAY_ROLES = [1474121009656500225, 1474116769458421973]
COMMAND_ROLES = [1474116769458421973, 1474121009656500225, 1479832999435440178]
CONVO_HOST_ROLE = 1479832999435440178
NOTIFY_ROLE = 1480656237027660046

# ===== Intents =====
intents = discord.Intents.default()
intents.members = True
intents.bans = True
intents.message_content = True

# ===== Bot Setup =====
bot = commands.Bot(command_prefix=">", intents=intents)
tree = bot.tree

# ===== Embed footer image =====
FOOTER_IMAGE = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png?ex=69b3bc5e&is=69b26ade&hm=79308b7601efdc372c21f5c2660ebeeefdf5e39b85a66636845f6f392c52468c&=&format=webp&quality=lossless&width=1656&height=1369"

# ===== Convoy tracking =====
active_convoy_message = None
convoy_reactors = set()


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


# ===== Dyno-style modlog embed =====
def dyno_embed(action, user, moderator=None, reason="No reason provided"):
    embed = discord.Embed(description=f"**{action}**", color=0x2F3136)
    embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
    if moderator:
        embed.add_field(name="Moderator", value=f"{moderator} ({moderator.id})", inline=False)
    embed.add_field(name="Reason", value=reason, inline=False)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)
    return embed


# ===== Welcome & Leave =====
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
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_IMAGE)

    await channel.send(embed=embed)
    log = dyno_embed("Member Joined", member)
    await log_channel.send(embed=log)


@bot.event
async def on_member_remove(member):
    log_channel = bot.get_channel(MODLOG_CHANNEL)
    log = dyno_embed("Member Left", member)
    await log_channel.send(embed=log)


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


# ===== >say command =====
@bot.command(name="say")
async def say(ctx, *, message: str):
    if not any(role.id in ALLOWED_SAY_ROLES for role in ctx.author.roles):
        await ctx.send("You don't have permission to use this command.", delete_after=5)
        return

    await ctx.message.delete()
    await ctx.send(message)


# ===== /startup slash command =====
@tree.command(name="startup", description="Start a convoy", guild=None)
@app_commands.describe(participants="Number of participants (3-50)")
async def startup(interaction: discord.Interaction, participants: int):
    global active_convoy_message, convoy_reactors

    if not any(role.id == CONVO_HOST_ROLE for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to run this.", ephemeral=True)
        return

    if participants < 3 or participants > 50:
        await interaction.response.send_message("Participants must be between 3 and 50.", ephemeral=True)
        return

    embed = discord.Embed(
        title="GVMC Convoy Launch",
        description=(
            f"A convoy is currently being hosted by {interaction.user.mention}. "
            f"Please react if you are intending to join. We ask you kindly review our "
            f"**[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)** before attending.\n\n"
            "If you are affected by the **Roblox Chat Ban**, feel free to talk in our "
            "[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)."
        ),
        color=0x87CEFA
    )
    embed.add_field(
        name="Most importantly",
        value="Enjoy your time in **Greenville Mafia Corporation** convoys! Assistance available in [assistance channel](https://discord.com/channels/1441901639739904125/1443980437184577556).",
        inline=False
    )
    embed.set_footer(icon_url=FOOTER_IMAGE, text="Greenville Mafia Corporation")
    msg = await interaction.channel.send(content=f"<@&{NOTIFY_ROLE}>", embed=embed)
    active_convoy_message = msg
    convoy_reactors = set()

    await msg.add_reaction("✅")
    await interaction.response.send_message("Convoy launched!", ephemeral=True)


# ===== /link slash command =====
@tree.command(name="link", description="Provide Roblox server link")
async def link(interaction: discord.Interaction, server_link: str):
    global active_convoy_message, convoy_reactors

    if not any(role.id in COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to run this.", ephemeral=True)
        return

    if not active_convoy_message:
        await interaction.response.send_message("No active convoy to link.", ephemeral=True)
        return

    # Only allow users who reacted with ✅ to join
    embed = discord.Embed(
        title="Convoy Release",
        description="The convoy link has been released! If you reacted, join via the button below.",
        color=0x87CEFA
    )
    embed.set_footer(icon_url=FOOTER_IMAGE, text="Greenville Mafia Corporation")
    view = discord.ui.View()
    button = discord.ui.Button(label="Link", url=server_link)
    view.add_item(button)
    await interaction.channel.send(embed=embed, view=view)
    await interaction.response.send_message("Convoy link sent.", ephemeral=True)


# ===== /end slash command =====
@tree.command(name="end", description="End the convoy session")
async def end(interaction: discord.Interaction):
    global active_convoy_message, convoy_reactors

    if not any(role.id in COMMAND_ROLES for role in interaction.user.roles):
        await interaction.response.send_message("You don't have permission to run this.", ephemeral=True)
        return

    embed = discord.Embed(
        title="Convoy Conclusion",
        description=(
            "We appreciate everyone who participated in the event. "
            "A 15 minute convoy cooldown is currently active. Keep an eye out for the next convoy!"
        ),
        color=0x87CEFA
    )
    embed.add_field(name="Feedback", value="Click the button below to rate & give feedback.", inline=False)
    embed.set_footer(icon_url=FOOTER_IMAGE, text="Greenville Mafia Corporation")
    view = discord.ui.View()

    # Button leads to a feedback form link (example URL, replace with actual form if needed)
    feedback_button = discord.ui.Button(label="Feedback", url="https://example.com/feedback-form")
    view.add_item(feedback_button)

    await interaction.channel.send(embed=embed, view=view)
    active_convoy_message = None
    convoy_reactors = set()
    await interaction.response.send_message("Convoy ended.", ephemeral=True)


# ===== Run Bot Async =====
async def main():
    token = os.getenv("TOKEN")
    async with bot:
        await bot.start(token)

if __name__ == "__main__":
    asyncio.run(main())
