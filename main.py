import discord
from discord.ext import commands
from discord import app_commands, ui
import datetime
import os
import sys
import json

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
ALLOWED_ROLES = [1474121009656500225, 1479832999435440178] # <-------- High Rank & Meet Launcher ---------
LOA_ROLE = 1474123995375992873
LOA_CHANNEL = 1485717423448653874
LOA_APPROVE_ROLES = [1474120141380911104, 1474116769458421973]
BLACKLIST_CHANNEL = 1485708172965580851
BLACKLIST_LOG_CHANNEL = 1487028216978739302
BLACKLIST_ROLE = 1474121009656500225
BLACKLIST_PING_ROLE = 1486271938631434363
BLACKLIST_FILE = "/mnt/disk/blacklist.json"  # <-- point it to your Render disk mount
BLACKLIST_MESSAGE_ID = 1486281089956974602  
GVMC_CONTRIBUTOR_ROLE = 1488794560740986970
GVMC_STATUS_CHANNEL = 1488795010475360347
GVMC_STATUS_TEXT = "/gvmc"

# Make sure the folder exists
os.makedirs(os.path.dirname(BLACKLIST_FILE), exist_ok=True)

FOOTER_ICON = "https://media.discordapp.net/attachments/1467783372469178442/1480467031571693710/image.png"
STARTUP_BANNER = "https://media.discordapp.net/attachments/1455902346440740894/1484092580613591140/Your_paragraph_text.png"
LINK_BANNER = "https://media.discordapp.net/attachments/1455902346440740894/1484093217744879636/Your_paragraph_text_1.png"
END_BANNER = "https://cdn.discordapp.com/attachments/1462071387685392425/1489794734791725297/Your_paragraph_text_6.png"
WELCOME_BANNER = "https://cdn.discordapp.com/attachments/1467783372469178442/1482361429188284606/Welcome_1.png"

bot_start_time = datetime.datetime.utcnow()

# -------- EVENTS --------
@bot.event
async def on_ready():
    await bot.tree.sync()
    await bot.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="Watching over 'Greenville Mafia Corporation'"
        )
    )
    bot.add_view(LOAView(0, 0, 0))
    bot.add_view(EndView())
    print(f"{bot.user} ready")

@bot.event
async def on_member_join(member):
    channel = bot.get_channel(WELCOME_CHANNEL)
    embed = discord.Embed(
        title="<a:welcome:1483008041413509141> Welcome to __**Greenville Mafia Corporation**__ <a:welcome:1483008041413509141>",
        description=(
            "<a:gvmc_heart:1480637190685069472> **Welcome to __Greenville Mafia Corporation!__**\n"
            "We are honored to have you here with us! Before you venture off into **GVMC**, please "
            "**[verify](https://discord.com/channels/1441901639739904125/1471452917163884738)** "
            "to gain full access to our server.\n\n"
            "<a:pulsatingheart:1480637910347940064> We host daily Convoys, Events, Occasional Giveaways "
            "and other fun surprises! We look forward to seeing you participate in the full life of "
            "__**Greenville Mafia Corporation**__. If you require any form of assistance, please do not "
            "hesitate to contact our lovely Staff Team "
            "**[here](https://discord.com/channels/1441901639739904125/1443980437184577556)**. "
            "<a:pulsatingheart:1480637910347940064>"
        ),
        color=0x87CEFA
    )
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)
    await channel.send(content=member.mention, embed=embed)

@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member):
    try:
        role = after.guild.get_role(GVMC_CONTRIBUTOR_ROLE)
        channel = bot.get_channel(GVMC_STATUS_CHANNEL)

        if role is None or channel is None:
            return

        before_status = None
        after_status = None

        # Get custom status BEFORE change
        for activity in (before.activities or []):
            if isinstance(activity, discord.CustomActivity):
                before_status = activity.name

        # Get custom status AFTER change
        for activity in (after.activities or []):
            if isinstance(activity, discord.CustomActivity):
                after_status = activity.name

        # ---- USER ADDED /GVMC ----
        if after_status and GVMC_STATUS_TEXT.lower() in after_status.lower():
            if role not in after.roles:
                await after.add_roles(role)

                embed = discord.Embed(
                    title="Greenville Mafia Corporation | Server Contributor",
                    description=(
                        f"> <a:gvmc_heart:1480637190685069472> | Thank you {after.mention} for becoming an official **Greenville Mafia Corporation** contributor!\n"
                        f"> They have received the <@&{GVMC_CONTRIBUTOR_ROLE}> role which contains benefits such as image permissions and exclusive giveaways!\n\n"
                        f"> <a:Animated_Arrow_Bluelite:1484055930919190589> | Would you like to receive the <@&{GVMC_CONTRIBUTOR_ROLE}> role?\n"
                        "> Please put ``/gvmc`` as your status and you will receive all the perks & role."
                    ),
                    color=0x87CEFA
                )

                embed.set_footer(
                    text="Greenville Mafia Corporation",
                    icon_url=FOOTER_ICON
                )

                await channel.send(embed=embed)

        # ---- USER REMOVED /GVMC ----
        if before_status and GVMC_STATUS_TEXT.lower() in before_status.lower():
            if (not after_status) or (GVMC_STATUS_TEXT.lower() not in after_status.lower()):
                if role in after.roles:
                    await after.remove_roles(role)

    except Exception as e:
        print(f"GVMC status error: {e}")

# -------- SAY COMMAND --------
@bot.command()
async def say(ctx, *, message):
    await ctx.message.delete()
    await ctx.send(message)

@bot.tree.command(name="say", description="Make the bot say something")
@app_commands.describe(message="The message you want the bot to send")
async def slash_say(interaction: discord.Interaction, message: str):
    member = interaction.guild.get_member(interaction.user.id)
    if 1474121009656500225 not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    await interaction.channel.send(message)

# -------- REACTION TRACKING --------
@bot.event
async def on_raw_reaction_add(payload):
    global startup_reactors

    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:Tick:1480637335237427221>":
            startup_reactors.add(payload.user_id)

            # ONLY trigger if the reactor is the startup host
            if startup_host and payload.user_id == startup_host.id:
                channel = bot.get_channel(payload.channel_id)
                message = await channel.fetch_message(payload.message_id)

                embed = discord.Embed(
                    title="Event Setup",
                    description=(
                        "> The host is currently setting up the Event. Please remain patient as they get everything ready. "
                        "Ensure you have set all your privacy settings set to __**everyone**__.\n\n"
                        "> During this time, we recommend that you look over our "
                        "**[Event Guidelines](https://discord.com/channels/1441901639739904125/1481562585781239969)**. "
                        "After this step is completed, the host will release the link. "
                        "You will be pinged again if you have the **Convoy Ping** role."
                    ),
                    color=0x87CEFA
                )

                await message.reply(embed=embed)


@bot.event
async def on_raw_reaction_remove(payload):
    global startup_reactors

    if startup_active and startup_message and payload.message_id == startup_message.id:
        if str(payload.emoji) == "<:Tick:1480637335237427221>":
            startup_reactors.discard(payload.user_id)

# -------- BLACKLIST STORAGE --------
def load_blacklist():
    if not os.path.exists(BLACKLIST_FILE):
        print("blacklist.json not found, creating new file")
        with open(BLACKLIST_FILE, "w") as f:
            json.dump([], f)
        return []

    with open(BLACKLIST_FILE, "r") as f:
        data = json.load(f)
        print(f"Loaded blacklist with {len(data)} entries")
        return data


def save_blacklist(data):
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(data, f, indent=4)
    print(f"Saved blacklist with {len(data)} entries")

# -------- UPDATE BLACKLIST MESSAGE --------
async def update_blacklist_message(bot):
    channel = bot.get_channel(BLACKLIST_CHANNEL)
    if channel is None:
        return

    data = load_blacklist()

    description = (
        "All servers below are blacklisted from all **GVMC** fast-passing, partnerships and any other affiliations. "
        "For proof of a specific blacklist or appeal a blacklist, please open a "
        "**[support ticket](https://discord.com/channels/1441901639739904125/1443980437184577556)** today "
        "and a member of the **High Ranking** Team will provide assistance.\n\n"
    )

    for i, entry in enumerate(data, start=1):
        description += (
            f"**{entry['server_name']}**\n"
            f"**Server ID** | {entry['server_id']}\n"
            f"**Reason for Blacklist** | {entry['reason']}\n"
            f"**Additional Notes** | {entry['notes']}\n"
            f"**Blacklist Number** | {i}\n\n"
        )

    embed = discord.Embed(
        title="Blacklisted Servers",
        description=description,
        color=0x87CEFA
    )

    message = await channel.fetch_message(BLACKLIST_MESSAGE_ID)
    await message.edit(embed=embed)
        
# -------- STARTUP COMMAND --------
@bot.tree.command(name="startup", description="Start a convoy session.")
@app_commands.describe(reactions="Number of reactions required to release link")
async def startup(interaction: discord.Interaction, reactions: int):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    global startup_active, startup_host, startup_message, startup_reactors, startup_time, required_reactions
    if startup_active:
        await interaction.response.send_message("A convoy session is already active.", ephemeral=True)
        return
    required_reactions = reactions
    startup_active = True
    startup_host = member
    startup_reactors = set()
    startup_time = datetime.datetime.utcnow()
    embed = discord.Embed(
        title="<:GVMC_trophy:1480637860590911610> Greenville Mafia Corporation Event Startup <:GVMC_trophy:1480637860590911610>",
        description=(
            f"<a:Animated_Arrow_Bluelite:1484055930919190589> | An Event is currently being started by {member.mention}. "
            "Before reacting, please ensure you have read all of our "
            "**[guidelines](https://discord.com/channels/1441901639739904125/1481562585781239969)** "
            "to ensure a smooth event for everyone. To confirm presence, please react with the <:Tick:1480637335237427221> below. "
            "We also ask that you have your privacy settings set to __**everyone**__ to ensure a trouble free event.\n\n"
            f"**Information**\n"
            f"<:dot:1480643720687915058> | The host has requested __**{required_reactions}**__ reactions. "
            "Once we reach the reaction count, the link will be released within this channel.\n"
            "<:dot:1480643720687915058> | Affected by **Roblox Chat Restriction**? Feel free to communicate with others or the host in our "
            "**[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)**\n\n"
            "<a:pulsatingheart:1480637910347940064> | Please wait for the **session release**. "
            "You will be notified within this channel when it has been **released**."
        ),
        color=0x87CEFA
    )
    embed.set_image(url=STARTUP_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)
    await interaction.response.send_message("Convoy started!", ephemeral=True)
    startup_message = await interaction.channel.send(
        content=f"<@&{NOTIFY_ROLE}>", embed=embed, allowed_mentions=discord.AllowedMentions(roles=True)
    )
    await startup_message.add_reaction("<:Tick:1480637335237427221>")

@bot.tree.command(name="blacklist", description="Blacklist a server")
@app_commands.describe(
    server_name="<a:Animated_Arrow_Bluelite:1484055930919190589> Server Name",
    server_id="<:dot:1480643720687915058> Server ID",
    reason="<:dot:1480643720687915058> Reason",
    notes="<:dot:1480643720687915058> Additional Notes"
)
async def blacklist(interaction: discord.Interaction, server_name: str, server_id: str, reason: str, notes: str):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    data = load_blacklist()

    data.append({
        "server_name": server_name,
        "server_id": server_id,
        "reason": reason,
        "notes": notes
    })

    save_blacklist(data)
    await update_blacklist_message(bot)

    # LOG EMBED
    log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL)

    embed = discord.Embed(
        title="Blacklist Added",
        description=(
            f"Added by: {interaction.user.mention}\n\n"
            f"**{server_name}**\n"
            f"Server ID: {server_id}\n"
            f"Reason: {reason}\n"
            f"Notes: {notes}"
        ),
        color=0x87CEFA
    )

    await log_channel.send(embed=embed)

    await interaction.response.send_message("Blacklist added.", ephemeral=True)

# -------- DELETE BLACKLIST --------
@bot.tree.command(name="delblacklist", description="Delete a blacklist entry")
@app_commands.describe(number="Blacklist Number")
async def delblacklist(interaction: discord.Interaction, number: int):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    data = load_blacklist()

    if number < 1 or number > len(data):
        await interaction.response.send_message("Invalid blacklist number.", ephemeral=True)
        return

    removed = data.pop(number - 1)
    save_blacklist(data)

    await update_blacklist_message(bot)

    log_channel = bot.get_channel(BLACKLIST_LOG_CHANNEL)

    embed = discord.Embed(
        title="Blacklist Removed",
        description=(
            f"Deleted by: {interaction.user.mention}\n"
            f"Blacklist Number: {number}\n\n"
            f"**{removed['server_name']}**\n"
            f"Server ID: {removed['server_id']}\n"
            f"Reason: {removed['reason']}\n"
            f"Notes: {removed['notes']}"
        ),
        color=0xFF0000
    )

    await log_channel.send(f"<@&{BLACKLIST_PING_ROLE}>", embed=embed)
    await interaction.response.send_message("Blacklist removed.", ephemeral=True)

# -------- BLACKLIST START COMMAND --------
@bot.tree.command(name="setupblacklist", description="Setup blacklist message")
async def setupblacklist(interaction: discord.Interaction):
    member = interaction.guild.get_member(interaction.user.id)

    if BLACKLIST_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("No permission.", ephemeral=True)
        return

    channel = bot.get_channel(BLACKLIST_CHANNEL)

    embed = discord.Embed(
        title="Blacklisted Servers",
        description=(
            "All servers below are blacklisted from all **GVMC** fast-passing, partnerships and any other affiliations. "
            "For proof of a specific blacklist or appeal a blacklist, please open a support ticket.\n\n"
            "No blacklisted servers."
        ),
        color=0x87CEFA
    )

    msg = await channel.send(embed=embed)

    await interaction.response.send_message(
        f"Blacklist message created. Message ID: {msg.id}",
        ephemeral=True
    )
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
        if interaction.user.id not in startup_reactors:
            await interaction.response.send_message("You must react to the startup message first.", ephemeral=True)
            return
        embed = discord.Embed(title="Private Server Link", description=f"> Click **[here]({self.url})** to join the private server.", color=0x87CEFA)
        await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="link", description="Release the private server link")
async def link(interaction: discord.Interaction, url: str):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return
    global link_message
    if not startup_active:
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return
    if member != startup_host:
        await interaction.response.send_message("Only the host can release the link.", ephemeral=True)
        return
    embed = discord.Embed(
        title="SESSION RELEASE",
        description=(
            f"> {member.mention} has released the session link.\n"
            "Please read all **[convoy rules](https://discord.com/channels/1441901639739904125/1481562585781239969)**.\n"
            "Respect hosts, members & staff. Ping host in **[convoy chat](https://discord.com/channels/1441901639739904125/1474109435751305286)** if needed."
        ),
        color=0x87CEFA
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_image(url=LINK_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)
    view = LinkView(url)
    await interaction.response.send_message("Link released!", ephemeral=True)
    link_message = await interaction.channel.send(content=f"<@&{NOTIFY_ROLE}>", embed=embed, view=view, allowed_mentions=discord.AllowedMentions(roles=True))

# -------- LOA SYSTEM AND MODALS --------
class DenyModal(ui.Modal, title="Deny LOA"):
    reason = ui.TextInput(label="Reason for denial", style=discord.TextStyle.paragraph)
    def __init__(self, target_user: discord.User):
        super().__init__()
        self.target_user = target_user
    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="LOA Denied",
            description=(
                f"Dear {self.target_user.mention},\n\n"
                f"Your LOA has been **Denied** for the following reason | {self.reason.value} |.\n\n"
                "If this is a misunderstanding, please contact management. "
                "Please do not submit another LOA until you have discussed with Management."
            ),
            color=0x87CEFA
        )
        try: await self.target_user.send(embed=embed)
        except: pass
        await interaction.response.send_message("LOA denied.", ephemeral=True)

class LOAView(ui.View):
    def __init__(self, user_id: int, start_ts: int, end_ts: int):
        super().__init__(timeout=None)
        self.user_id = user_id
        self.start_ts = start_ts
        self.end_ts = end_ts
        self.handled = False
    def has_permission(self, member):
        return any(role.id in LOA_APPROVE_ROLES for role in member.roles)
    def disable_all(self):
        for item in self.children: item.disabled = True
    @ui.button(label="Approve", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: ui.Button):
        if not self.has_permission(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        if self.handled:
            await interaction.response.send_message("This LOA has already been handled.", ephemeral=True)
            return
        self.handled = True
        user = await interaction.client.fetch_user(self.user_id)
        embed = discord.Embed(
            title="LOA Approved",
            description=(
                f"Dear {user.mention},\n\n"
                f"Your LOA has been **approved** by {interaction.user.mention}.\n\n"
                f"**LOA Information**\n"
                f"<:dot:1480643720687915058> Start Date | <t:{self.start_ts}:f>\n"
                f"<:dot:1480643720687915058> End Date | <t:{self.end_ts}:f>\n\n"
                "You are exempt from **Staff Quota** during this period.\n\n"
                "After your LOA ends, activity is expected. You may not submit another LOA for 28 days.\n\n"
                "Kind Regards,\nGreenville Mafia Corporation,\nManagement."
            ),
            color=0x87CEFA
        )
        try: await user.send(embed=embed)
        except: pass
        self.disable_all()
        await interaction.message.edit(view=self)
        await interaction.response.send_message("LOA approved.", ephemeral=True)
    @ui.button(label="Deny", style=discord.ButtonStyle.danger)
    async def deny(self, interaction: discord.Interaction, button: ui.Button):
        if not self.has_permission(interaction.user):
            await interaction.response.send_message("No permission.", ephemeral=True)
            return
        if self.handled:
            await interaction.response.send_message("This LOA has already been handled.", ephemeral=True)
            return
        self.handled = True
        user = await interaction.client.fetch_user(self.user_id)
        await interaction.response.send_modal(DenyModal(user))
        self.disable_all()
        await interaction.message.edit(view=self)

# -------- END COMMANDS --------
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
    def __init__(self):
        super().__init__(timeout=None)

    @ui.button(
        label="Provide Feedback",
        style=discord.ButtonStyle.secondary,
        custom_id="feedback_button"
    )
    async def feedback(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(FeedbackModal())

@bot.tree.command(name="end", description="End the current convoy")
@app_commands.describe(host_note="Host note for the convoy")
async def end(interaction: discord.Interaction, host_note: str):
    member = interaction.guild.get_member(interaction.user.id)
    if not any(role.id in ALLOWED_ROLES for role in member.roles):
        await interaction.response.send_message("You are not authorized to use this command.", ephemeral=True)
        return
    global startup_active, startup_message, link_message, startup_time, startup_host, startup_reactors
    if not startup_active:
        await interaction.response.send_message("No active convoy.", ephemeral=True)
        return
    end_time = datetime.datetime.utcnow()
    duration = end_time - startup_time
    if startup_message:
        try: await startup_message.delete()
        except: pass
    if link_message:
        try: await link_message.delete()
        except: pass
    embed = discord.Embed(
        title=" <:Gvmc_crown:1480630263456464957> Greenville Mafia Corporation Conclusion <:Gvmc_crown:1480630263456464957>",
        description=(
            f"<a:Animated_Arrow_Bluelite:1484055930919190589> | The Event that was hosted by {member.mention} has concluded. "
            "We appreciate those who were actively involved & participating in this event. "
            "We hope to see you in more of our events in the future as there are **many** more to come!\n\n"
            f"**Event Information**\n"
            f"<:dot:1480643720687915058> Event End Time | <t:{int(end_time.timestamp())}:f>\n"
            f"<:dot:1480643720687915058> Event Duration | {str(duration).split('.')[0]}\n\n"
            f"<:announcement:1480640464737800253> Additional Notes | {host_note}\n\n"
            "<a:gvmc_heart:1480637190685069472> | Want to help improve our Events? Give us feedback by clicking the feedback button below!"

        ),
        color=0x87CEFA
    )
    embed.set_image(url=END_BANNER)
    embed.set_footer(text="Greenville Mafia Corporation", icon_url=FOOTER_ICON)
    view = EndView()
    await interaction.response.send_message("Convoy ended!", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)
    log_channel = bot.get_channel(SESSION_LOG_CHANNEL)
    log_embed = discord.Embed(
        title="Session Logged",
        description=f"Host: {member.mention}\nDuration: {str(duration).split('.')[0]}\nHost Note: {host_note}",
        color=0x87CEFA
    )
    await log_channel.send(embed=log_embed)
    startup_active = False
    startup_host = None
    startup_message = None
    link_message = None
    startup_reactors = set()
    startup_time = None

# -------- LOA COMMAND CONTINUED --------
@bot.tree.command(name="loa", description="Submit a Leave of Absence")
@app_commands.describe(
    reason="Reason for LOA",
    start_date="Start date (YYYY-MM-DD)",
    end_date="End date (YYYY-MM-DD)",
    rank="Your rank",
    notes="Additional notes"
)
async def loa(interaction: discord.Interaction, reason: str, start_date: str, end_date: str, rank: str, notes: str):
    member = interaction.guild.get_member(interaction.user.id)

    if LOA_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("You are not authorized.", ephemeral=True)
        return

    try:
        start_dt = datetime.datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.datetime.strptime(end_date, "%Y-%m-%d")
    except:
        await interaction.response.send_message("Invalid date format. Use YYYY-MM-DD.", ephemeral=True)
        return

    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())

    # Defer the response to avoid "did not respond"
    await interaction.response.defer()

    # confirmation embed
    confirm_embed = discord.Embed(
        title="LOA Submission",
        description=(
            "> <a:Animated_Arrow_Bluelite:1484055930919190589> Your LOA has been submitted. Our Management team will review it shortly.\n\n"
            "> Please look out for a **Direct Message** confirming your submission and another when we have approved or denied your submission.\n\n"
            "> If there are any issues, contact management."

            "**If you do not get a DM response within 1 day, please create a ticket.**"
        ),
        color=0x87CEFA
    )

    # Send confirmation via followup
    await interaction.followup.send(embed=confirm_embed)

    # send to staff channel
    channel = bot.get_channel(LOA_CHANNEL)
    if channel:
        try:
            embed = discord.Embed(
                title="LOA Request",
                description=(
                    f"User requesting | {member.mention}\n"
                    f"<:dot:1480643720687915058> Start Date | <t:{start_ts}:f>\n"
                    f"<:dot:1480643720687915058> End Date | <t:{end_ts}:f>\n"
                    f"<:dot:1480643720687915058> Reason | {reason}\n"
                    f"<:dot:1480643720687915058> Rank | {rank}\n"
                    f"<:dot:1480643720687915058> Additional Notes | {notes}\n\n"
                    "Please use the buttons below to approve/deny this LOA."
                ),
                color=0x87CEFA
            )

            view = LOAView(member.id, start_ts, end_ts)
            await channel.send(embed=embed, view=view)
        except Exception as e:
            print("Failed to send LOA to staff channel:", e)

# -------- INFO COMMAND --------
@bot.tree.command(name="botinfo", description="View the Bot's information")
async def info(interaction: discord.Interaction):
    uptime = datetime.datetime.utcnow() - bot_start_time
    api_ping = round(bot.latency * 1000)
    embed = discord.Embed(
        title="BOT INFO",
        description=(
            f"> Developer: Reuben2k11\n"
            f"> Prefix: >\n"
            f"> Uptime: {str(uptime).split('.')[0]}\n"
            f"> Ping: {api_ping}ms\n"
            f"> Discord.py Version: {discord.__version__}\n"
            f"> Status: Online"
        ),
        color=0x87CEFA
    )
    await interaction.response.send_message(embed=embed)

# -------- MEMBERCOUNT COMMAND --------
@bot.tree.command(name="membercount", description="Show total member count")
async def membercount(interaction: discord.Interaction):
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True
        )
        return
    count = guild.member_count
    embed = discord.Embed(
        title="**Members**",
        description=f"{count}",
        color=0x87CEFA
    )
    embed.timestamp = datetime.datetime.utcnow()
    await interaction.response.send_message(embed=embed)

# -------- KILL COMMAND --------
@bot.tree.command(name="botreset", description="Restart the Bot")
async def kill(interaction: discord.Interaction):
    member = interaction.guild.get_member(interaction.user.id)
    if KILL_ROLE not in [role.id for role in member.roles]:
        await interaction.response.send_message("Only the Bot Developer is authorized to use this command.", ephemeral=True)
        return
    await interaction.response.send_message("The bot has restarted.", ephemeral=True)
    sys.exit()

# -------- RUN BOT --------
bot.run(TOKEN)

