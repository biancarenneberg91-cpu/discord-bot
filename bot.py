import discord
from discord.ext import commands
import json
import os
import datetime

# ─────────────────────────────────────────────
#  KONFIGURATION
# ─────────────────────────────────────────────
TOKEN = os.environ.get("DISCORD_TOKEN")  # Railway Umgebungsvariable
PREFIX = "!"
DATA_FILE = "data.json"

# ─────────────────────────────────────────────
#  BOT SETUP
# ─────────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix=PREFIX, intents=intents)

# ─────────────────────────────────────────────
#  ANTI-SPAM TRACKER
# ─────────────────────────────────────────────
spam_tracker = {}

# ─────────────────────────────────────────────
#  DATEN LADEN / SPEICHERN
# ─────────────────────────────────────────────
def lade_daten():
    if not os.path.exists(DATA_FILE):
        speichere_daten({
            "warnings": {},
            "dienstgrade": {},
            "dienstzeiten": {},
            "einsaetze": 0,
            "tickets": 0
        })
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def speichere_daten(daten):
    with open(DATA_FILE, "w") as f:
        json.dump(daten, f, indent=4)

# ─────────────────────────────────────────────
#  EVENTS
# ─────────────────────────────────────────────
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Bot eingeloggt als {bot.user} (ID: {bot.user.id})")
    print(f"📡 Verbunden mit {len(bot.guilds)} Server(n)")

@bot.event
async def on_member_join(member):
    """Automatische Begrüßung bei Neuzugang"""
    kanal = member.guild.system_channel
    if kanal:
        embed = discord.Embed(
            title="👋 Willkommen!",
            description=f"Willkommen auf **{member.guild.name}**, {member.mention}!\n\nSchau dich um und lies die Regeln.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Mitglied #{member.guild.member_count}")
        await kanal.send(embed=embed)

@bot.event
async def on_message(message):
    """Anti-Spam Überwachung"""
    if message.author.bot:
        return

    uid = message.author.id
    spam_tracker.setdefault(uid, {"count": 0, "last": datetime.datetime.utcnow()})

    now = datetime.datetime.utcnow()
    diff = (now - spam_tracker[uid]["last"]).total_seconds()

    # Zähler zurücksetzen nach 5 Sekunden
    if diff > 5:
        spam_tracker[uid] = {"count": 0, "last": now}

    spam_tracker[uid]["count"] += 1
    spam_tracker[uid]["last"] = now

    if spam_tracker[uid]["count"] >= 6:
        try:
            timeout_until = discord.utils.utcnow() + datetime.timedelta(minutes=5)
            await message.author.timeout(timeout_until, reason="Spam")
            await message.channel.send(
                f"🚫 {message.author.mention} wurde wegen Spam für **5 Minuten** getimeoutet."
            )
        except Exception as e:
            print(f"Timeout-Fehler: {e}")
        spam_tracker[uid]["count"] = 0

    await bot.process_commands(message)

@bot.event
async def on_member_ban(guild, user):
    """Log bei Ban"""
    log_kanal = discord.utils.get(guild.text_channels, name="mod-logs")
    if log_kanal:
        embed = discord.Embed(
            title="🔨 Mitglied gebannt",
            description=f"**{user}** wurde vom Server gebannt.",
            color=discord.Color.red(),
            timestamp=datetime.datetime.utcnow()
        )
        await log_kanal.send(embed=embed)

# ─────────────────────────────────────────────
#  SLASH COMMANDS – MODERATION
# ─────────────────────────────────────────────
@bot.tree.command(name="warn", description="Mitglied verwarnen")
@discord.app_commands.describe(mitglied="Das Mitglied", grund="Grund der Verwarnung")
@discord.app_commands.checks.has_permissions(manage_messages=True)
async def warn(interaction: discord.Interaction, mitglied: discord.Member, grund: str = "Kein Grund angegeben"):
    daten = lade_daten()
    uid = str(mitglied.id)
    daten["warnings"].setdefault(uid, [])
    daten["warnings"][uid].append({
        "grund": grund,
        "datum": str(datetime.datetime.utcnow()),
        "mod": str(interaction.user)
    })
    speichere_daten(daten)

    anzahl = len(daten["warnings"][uid])
    embed = discord.Embed(
        title="⚠️ Verwarnung",
        color=discord.Color.orange()
    )
    embed.add_field(name="Mitglied", value=mitglied.mention)
    embed.add_field(name="Grund", value=grund)
    embed.add_field(name="Verwarnungen gesamt", value=str(anzahl))
    embed.set_footer(text=f"Mod: {interaction.user}")
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="warnings", description="Verwarnungen eines Mitglieds anzeigen")
@discord.app_commands.describe(mitglied="Das Mitglied")
async def warnings(interaction: discord.Interaction, mitglied: discord.Member):
    daten = lade_daten()
    uid = str(mitglied.id)
    warns = daten["warnings"].get(uid, [])

    embed = discord.Embed(
        title=f"⚠️ Verwarnungen von {mitglied.display_name}",
        color=discord.Color.orange()
    )
    if not warns:
        embed.description = "Keine Verwarnungen."
    else:
        for i, w in enumerate(warns, 1):
            embed.add_field(
                name=f"#{i} – {w['datum'][:10]}",
                value=f"**Grund:** {w['grund']}\n**Mod:** {w['mod']}",
                inline=False
            )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="kick", description="Mitglied kicken")
@discord.app_commands.describe(mitglied="Das Mitglied", grund="Grund")
@discord.app_commands.checks.has_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, mitglied: discord.Member, grund: str = "Kein Grund"):
    await mitglied.kick(reason=grund)
    embed = discord.Embed(
        title="👢 Mitglied gekickt",
        description=f"{mitglied.mention} wurde gekickt.\n**Grund:** {grund}",
        color=discord.Color.red()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ban", description="Mitglied bannen")
@discord.app_commands.describe(mitglied="Das Mitglied", grund="Grund")
@discord.app_commands.checks.has_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, mitglied: discord.Member, grund: str = "Kein Grund"):
    await mitglied.ban(reason=grund)
    embed = discord.Embed(
        title="🔨 Mitglied gebannt",
        description=f"{mitglied.mention} wurde gebannt.\n**Grund:** {grund}",
        color=discord.Color.dark_red()
    )
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="timeout", description="Mitglied timeouten")
@discord.app_commands.describe(mitglied="Das Mitglied", minuten="Dauer in Minuten", grund="Grund")
@discord.app_commands.checks.has_permissions(moderate_members=True)
async def timeout_cmd(interaction: discord.Interaction, mitglied: discord.Member, minuten: int = 10, grund: str = "Kein Grund"):
    bis = discord.utils.utcnow() + datetime.timedelta(minutes=minuten)
    await mitglied.timeout(bis, reason=grund)
    embed = discord.Embed(
        title="⏱️ Timeout",
        description=f"{mitglied.mention} für **{minuten} Minuten** getimeoutet.\n**Grund:** {grund}",
        color=discord.Color.orange()
    )
    await interaction.response.send_message(embed=embed)

# ─────────────────────────────────────────────
#  SLASH COMMANDS – TICKETSYSTEM
# ─────────────────────────────────────────────
@bot.tree.command(name="ticket", description="Support-Ticket erstellen")
async def ticket(interaction: discord.Interaction):
    guild = interaction.guild

    # Prüfen ob bereits ein Ticket offen ist
    existing = discord.utils.get(guild.text_channels, name=f"ticket-{interaction.user.name.lower()}")
    if existing:
        await interaction.response.send_message(
            f"❌ Du hast bereits ein offenes Ticket: {existing.mention}",
            ephemeral=True
        )
        return

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
    }

    # Moderatoren-Rolle Zugriff geben falls vorhanden
    mod_rolle = discord.utils.get(guild.roles, name="Moderator")
    if mod_rolle:
        overwrites[mod_rolle] = discord.PermissionOverwrite(view_channel=True, send_messages=True)

    kanal = await guild.create_text_channel(
        f"ticket-{interaction.user.name.lower()}",
        overwrites=overwrites,
        topic=f"Ticket von {interaction.user}"
    )

    daten = lade_daten()
    daten["tickets"] += 1
    speichere_daten(daten)

    embed = discord.Embed(
        title="🎫 Ticket geöffnet",
        description=f"Hallo {interaction.user.mention}!\nBeschreibe dein Anliegen und ein Moderator wird sich kümmern.\n\nZum Schließen: `/close`",
        color=discord.Color.blue()
    )
    await kanal.send(embed=embed)
    await interaction.response.send_message(
        f"✅ Ticket erstellt: {kanal.mention}",
        ephemeral=True
    )

@bot.tree.command(name="close", description="Ticket schließen")
async def close(interaction: discord.Interaction):
    if not interaction.channel.name.startswith("ticket-"):
        await interaction.response.send_message(
            "❌ Dieser Befehl funktioniert nur in einem Ticket-Kanal.",
            ephemeral=True
        )
        return

    await interaction.response.send_message("🔒 Ticket wird in 3 Sekunden geschlossen...")
    await discord.utils.sleep_until(discord.utils.utcnow() + datetime.timedelta(seconds=3))
    await interaction.channel.delete()

# ─────────────────────────────────────────────
#  SLASH COMMANDS – EINSATZ (RP)
# ─────────────────────────────────────────────
@bot.tree.command(name="einsatz", description="Einsatz ausrufen")
@discord.app_commands.describe(beschreibung="Einsatzbeschreibung", ort="Einsatzort")
async def einsatz(interaction: discord.Interaction, beschreibung: str, ort: str = "Unbekannt"):
    daten = lade_daten()
    daten["einsaetze"] += 1
    speichere_daten(daten)

    embed = discord.Embed(
        title="🚨 EINSATZ AUSGERUFEN",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="📍 Ort", value=ort, inline=True)
    embed.add_field(name="📋 Beschreibung", value=beschreibung, inline=False)
    embed.add_field(name="👮 Ausgerufen von", value=interaction.user.mention, inline=True)
    embed.add_field(name="🚁 Einsatz #", value=str(daten["einsaetze"]), inline=True)
    embed.set_footer(text="Alle verfügbaren Einheiten reagieren!")

    await interaction.response.send_message(content="@everyone", embed=embed)

# ─────────────────────────────────────────────
#  SLASH COMMANDS – DIENSTGRADE
# ─────────────────────────────────────────────
DIENSTGRADE = [
    "Rekrut", "Gefreiter", "Unteroffizier",
    "Feldwebel", "Leutnant", "Hauptmann",
    "Major", "Oberst", "General"
]

@bot.tree.command(name="befördern", description="Mitglied befördern")
@discord.app_commands.describe(mitglied="Das Mitglied")
@discord.app_commands.checks.has_permissions(manage_roles=True)
async def befoerdern(interaction: discord.Interaction, mitglied: discord.Member):
    daten = lade_daten()
    uid = str(mitglied.id)
    aktuell = daten["dienstgrade"].get(uid, 0)

    if aktuell >= len(DIENSTGRADE) - 1:
        await interaction.response.send_message(
            f"⭐ {mitglied.mention} hat bereits den höchsten Rang: **{DIENSTGRADE[aktuell]}**",
            ephemeral=True
        )
        return

    neuer_rang = aktuell + 1
    daten["dienstgrade"][uid] = neuer_rang
    speichere_daten(daten)

    embed = discord.Embed(
        title="🎖️ Beförderung!",
        description=f"{mitglied.mention} wurde befördert!",
        color=discord.Color.gold()
    )
    embed.add_field(name="Vorher", value=DIENSTGRADE[aktuell])
    embed.add_field(name="Jetzt", value=DIENSTGRADE[neuer_rang])
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rang", description="Deinen aktuellen Rang anzeigen")
@discord.app_commands.describe(mitglied="Mitglied (optional)")
async def rang(interaction: discord.Interaction, mitglied: discord.Member = None):
    ziel = mitglied or interaction.user
    daten = lade_daten()
    uid = str(ziel.id)
    rang_index = daten["dienstgrade"].get(uid, 0)

    embed = discord.Embed(
        title="🎖️ Dienstgrad",
        description=f"{ziel.mention} hat den Rang **{DIENSTGRADE[rang_index]}**",
        color=discord.Color.blue()
    )
    await interaction.response.send_message(embed=embed)

# ─────────────────────────────────────────────
#  SLASH COMMANDS – STATISTIKEN
# ─────────────────────────────────────────────
@bot.tree.command(name="stats", description="Server-Statistiken anzeigen")
async def stats(interaction: discord.Interaction):
    daten = lade_daten()
    guild = interaction.guild

    embed = discord.Embed(
        title="📊 Server-Statistiken",
        color=discord.Color.gold(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="👥 Mitglieder", value=str(guild.member_count), inline=True)
    embed.add_field(name="🎫 Tickets gesamt", value=str(daten["tickets"]), inline=True)
    embed.add_field(name="🚨 Einsätze gesamt", value=str(daten["einsaetze"]), inline=True)
    embed.add_field(name="⚠️ Verwarnungen", value=str(sum(len(v) for v in daten["warnings"].values())), inline=True)
    embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="Serverinformationen anzeigen")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(
        title=f"ℹ️ {guild.name}",
        color=discord.Color.blue(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.add_field(name="👑 Owner", value=guild.owner.mention if guild.owner else "Unbekannt")
    embed.add_field(name="👥 Mitglieder", value=str(guild.member_count))
    embed.add_field(name="📅 Erstellt am", value=guild.created_at.strftime("%d.%m.%Y"))
    embed.add_field(name="💬 Kanäle", value=str(len(guild.text_channels)))
    embed.add_field(name="🎙️ Sprachkanäle", value=str(len(guild.voice_channels)))
    embed.add_field(name="🎭 Rollen", value=str(len(guild.roles)))
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    await interaction.response.send_message(embed=embed)

# ─────────────────────────────────────────────
#  SLASH COMMANDS – UTILITY
# ─────────────────────────────────────────────
@bot.tree.command(name="ping", description="Bot-Latenz anzeigen")
async def ping(interaction: discord.Interaction):
    latenz = round(bot.latency * 1000)
    farbe = discord.Color.green() if latenz < 100 else discord.Color.orange() if latenz < 200 else discord.Color.red()
    embed = discord.Embed(title="🏓 Pong!", description=f"Latenz: **{latenz}ms**", color=farbe)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="hilfe", description="Alle Befehle anzeigen")
async def hilfe(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📖 Bot-Befehle",
        color=discord.Color.blurple()
    )
    embed.add_field(name="🛡️ Moderation", value="`/warn` `/warnings` `/kick` `/ban` `/timeout`", inline=False)
    embed.add_field(name="🎫 Tickets", value="`/ticket` `/close`", inline=False)
    embed.add_field(name="🚨 Einsatz (RP)", value="`/einsatz`", inline=False)
    embed.add_field(name="🎖️ Dienstgrade", value="`/befördern` `/rang`", inline=False)
    embed.add_field(name="📊 Statistiken", value="`/stats` `/serverinfo`", inline=False)
    embed.add_field(name="⚙️ Utility", value="`/ping` `/hilfe`", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ─────────────────────────────────────────────
#  ERROR HANDLER
# ─────────────────────────────────────────────
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
    if isinstance(error, discord.app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ Du hast keine Berechtigung für diesen Befehl.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            f"❌ Fehler: `{error}`",
            ephemeral=True
        )
        print(f"Fehler: {error}")

# ─────────────────────────────────────────────
#  START
# ─────────────────────────────────────────────
if __name__ == "__main__":
    if not TOKEN:
        print("❌ DISCORD_TOKEN nicht gesetzt! Bitte als Umgebungsvariable setzen.")
    else:
        bot.run(TOKEN)
