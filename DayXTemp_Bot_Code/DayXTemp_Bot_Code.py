import discord
from discord.ext import commands, tasks
import asyncio
import config  # Importiere die config.py-Datei
import sys
import os
import psutil
from datetime import datetime, timedelta

# Initialisiert alle sicherungs Dateien
intents = discord.Intents.all()
intents.voice_states = True

bot = commands.Bot(command_prefix="/", intents=intents)
private_channels = {}
ignored_channels = set()
automod_exceptions = set()
ignored_channels_file = "ignored_channels.txt"  # Dateiname für die gespeicherten ignorierten Kanäle
private_channels_file = "private_channels.txt"  # Dateiname für die gespeicherten privaten Kanäle
support_channel_file = "support_channel.txt"  # Dateiname für den Support-Kanal
automod_settings_file = "automod_settings.txt"  # Dateiname für die Spamschutz-Einstellungen
AUTO_MOD_CHANNELS_FILE = 'automod_channels.txt'
automod_exceptions_file = "automod_exceptions.txt"  # Dateiname für die Ausnahmeliste ersatz für automod_channels.txt

# Initialisiere die Variable für den Support-Kanal
support_channel_id = None
spam_protection_enabled = False  # Starte mit deaktiviertem Spamschutz


@bot.event
async def on_ready():
    print(f'Bot ist eingeloggt als {bot.user}')
    await load_ignored_channels()
    await load_private_channels()
    await load_support_channel()  # Lade den Support-Kanal beim Start
    await load_automod_exceptions()
    load_automod_settings()  # Lade den Status der automatischen Moderation beim Start

    check_empty_private_channels.start()  # Starte die Überprüfung der leeren privaten Kanäle alle 10 Sekunden

# Hier Beginnt die Automod Logik


async def load_automod_exceptions():
    global automod_exceptions
    try:
        with open(automod_exceptions_file, "r") as file:
            for line in file:
                channel_id = int(line.strip())
                automod_exceptions.add(channel_id)
        print("Automod-Ausnahmen erfolgreich geladen.")
    except FileNotFoundError:
        print(f"Datei {automod_exceptions_file} nicht gefunden. Es werden keine Automod-Ausnahmen geladen.")
    except Exception as e:
        print(f"Fehler beim Laden der Automod-Ausnahmen: {e}")


async def save_automod_exceptions():
    try:
        with open(automod_exceptions_file, "w") as file:
            for channel_id in automod_exceptions:
                file.write(f"{channel_id}\n")
        print("Automod-Ausnahmen erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Automod-Ausnahmen: {e}")


@bot.command()
async def tempautomodlist(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(
            title="Liste der ignorierten Textkanäle (Spam-Schutz)",
            description="Hier sind die Textkanäle, die der Spam-Schutz nicht überwacht:",
            color=discord.Color.blue()
        )

        try:
            with open(automod_exceptions_file, "r") as file:
                channel_ids = [int(line.strip()) for line in file.readlines()]

            if channel_ids:
                for channel_id in channel_ids:
                    channel = bot.get_channel(channel_id)
                    if channel:
                        embed.add_field(name=channel.name, value=f"Kanal ID: {channel.id}", inline=False)
                    else:
                        embed.add_field(name=f"Kanal ID: {channel_id}", value="Kanal nicht gefunden", inline=False)

                await ctx.send(embed=embed)
            else:
                await ctx.send("Es wurden keine Textkanäle vom Spam-Schutz ausgenommen.")

        except FileNotFoundError:
            await ctx.send("Die Datei automod_exceptions.txt wurde nicht gefunden.")

        except Exception as e:
            await ctx.send(f"Fehler beim Laden der automatischen Moderationsausnahmen: {e}")

    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


@bot.command(name='tempautomod')
async def tempautomod(ctx):
    if await is_spam_protection_enabled():
        await ctx.send("Der Spamschutz ist **aktiv**.")
    else:
        await ctx.send("Der Spamschutz ist **deaktiviert**.")


# Befehl zum Hinzufügen eines Kanals zur Ausnahmeliste für Automod-Funktionen
@bot.command()
async def tempautomodadd(ctx):
    if ctx.author.guild_permissions.administrator:
        text_channels = [channel for channel in ctx.guild.text_channels if channel.id not in automod_exceptions]
        if not text_channels:
            embed = discord.Embed(title="Ausnahmen für Automoderation hinzufügen",
                                  description="Es gibt keine Textkanäle zum Hinzufügen.")
            await ctx.send(embed=embed)
        else:
            embeds = []
            embed = discord.Embed(title="Ausnahmen für Automoderation hinzufügen",
                                  description="Wähle die Kanäle aus, die von Spam ausgenommen werden sollen:")

            for index, channel in enumerate(text_channels):
                if index > 0 and index % 25 == 0:
                    embed.set_footer(text="Zum Auswählen, schreibe eine Kanalnummer, trenne für mehr. 'cancel' zum Abbrechen.")
                    embeds.append(embed)
                    embed = discord.Embed()

                embed.add_field(name=f"{index + 1}. {channel.name}", value=f"Kanal ID: {channel.id}", inline=False)

            if len(embed.fields) > 0:
                embed.set_footer(text="Zum Auswählen, schreibe eine Kanalnummer, trenne für mehr. 'cancel' zum Abbrechen.")
                embeds.append(embed)

            for e in embeds:
                await ctx.send(embed=e)

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            if msg.content.lower() == 'cancel':
                await ctx.send("Befehl abgebrochen.")
                return

            channel_indices = [int(index.strip()) - 1 for index in msg.content.split() if index.strip().isdigit()]
            for index in channel_indices:
                if 0 <= index < len(text_channels):
                    channel_id = text_channels[index].id
                    automod_exceptions.add(channel_id)
                    await ctx.send(f"Der Kanal '{text_channels[index].name}' wird von der Automoderation ausgenommen.")
                    # Speichern der Ausnahmeliste in einer Datei oder Datenbank
                    with open(automod_exceptions_file, "a") as file:
                        file.write(str(channel_id) + "\n")
                else:
                    await ctx.send("Ungültige Auswahl. Der Befehl wurde abgebrochen.")
        except asyncio.TimeoutError:
            await ctx.send("Abbruch, Zeitüberschreitung.")
        except ValueError:
            await ctx.send("Ungültige Eingabe. Bitte antworte mit den Nummern der Kanäle.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


@bot.command()
async def tempautomodremove(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(title="Ausnahmen für Automoderation entfernen",
                              description="Wähle die Kanäle aus, die nicht mehr von Spam ausgenommen werden sollen:")
        if not automod_exceptions:
            embed.add_field(name="Keine ausgenommenen Textkanäle", value="Es wurden keine Textkanäle ausgenommen.")
        else:
            for index, channel_id in enumerate(automod_exceptions):
                channel = discord.utils.get(ctx.guild.text_channels, id=channel_id)
                embed.add_field(name=f"{index + 1}. {channel.name}", value=f"Kanal ID: {channel.id}", inline=False)
            embed.set_footer(
                text="Zum Auswählen, schreibe eine Kanalnummer, trenne für mehr. 'cancel' zum Abbrechen.")
        await ctx.send(embed=embed)

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            if msg.content.lower() == 'cancel':
                await ctx.send("Befehl abgebrochen.")
                return

            channel_indices = [int(index.strip()) - 1 for index in msg.content.split() if index.strip().isdigit()]
            channels_to_unexempt = [channel_id for index, channel_id in enumerate(automod_exceptions) if index in channel_indices]

            for channel_id in channels_to_unexempt:
                channel = discord.utils.get(ctx.guild.text_channels, id=channel_id)
                automod_exceptions.remove(channel_id)
                await ctx.send(f"Der Kanal '{channel.name}' wird nicht mehr von der Automoderation ausgenommen.")
                # Entfernen der Ausnahme aus der Datei oder Datenbank
                with open(automod_exceptions_file, "r+") as file:
                    lines = file.readlines()
                    file.seek(0)
                    for line in lines:
                        if str(channel_id) not in line.strip():
                            file.write(line)
                    file.truncate()
        except asyncio.TimeoutError:
            await ctx.send("Zeitüberschreitung. Der Befehl wurde abgebrochen.")
        except ValueError:
            await ctx.send("Ungültige Eingabe. Bitte antworte mit den Nummern der Kanäle.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


def load_automod_settings():
    global spam_protection_enabled
    try:
        with open(automod_settings_file, "r") as file:
            settings = file.read().strip()
            spam_protection_enabled = settings == "True"
        print("Spamschutz-Einstellungen erfolgreich geladen.")
    except FileNotFoundError:
        print("Datei automod_settings.txt nicht gefunden. Standardwert (Spamschutz deaktiviert) wird verwendet.")
    except Exception as e:
        print(f"Fehler beim Laden der Spamschutz-Einstellungen: {e}")

# Speichern der Spamschutz-Einstellungen


def save_automod_settings():
    try:
        with open(automod_settings_file, "w") as file:
            file.write(str(spam_protection_enabled))
        print("Spamschutz-Einstellungen erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der Spamschutz-Einstellungen: {e}")

# Spamschutz Logik
# Definiere eine globale Variable für die letzte Nachricht pro Nutzer


last_message = {}


# Diese Funktion prüft, ob der Spamschutz aktiv ist
async def is_spam_protection_enabled():
    return spam_protection_enabled

# Diese Funktion wird verwendet, um den Spamschutz-Status umzuschalten


async def toggle_spam_protection(enable):
    global spam_protection_enabled
    spam_protection_enabled = enable


@bot.event
async def on_message(message):
    if message.author == bot.user:
        return  # Ignoriere Nachrichten des Bots selbst

    # Prüfe, ob der Spamschutz aktiv ist
    if spam_protection_enabled and message.channel.id not in automod_exceptions:

        now = datetime.now()
        if message.author.id in last_message:
            delta = now - last_message[message.author.id]
            if delta < timedelta(seconds=1):
                # Nachrichtenintervall zu kurz (hier 3 Sekunden), daher könnte es Spam sein
                await message.delete()

                # Nachricht an den Spammer senden
                dm_channel = message.author.dm_channel
                if dm_channel is None:
                    dm_channel = await message.author.create_dm()

                server_name = message.guild.name if message.guild else "einem Server"
                await dm_channel.send(f"{message.author.mention}, Spamme nicht! Du hast auf {server_name} gespammt.")

        # Speichere die Zeit der letzten Nachricht des Nutzers
        last_message[message.author.id] = now

    await bot.process_commands(message)  # Verarbeitet auch die restlichen Befehle


@bot.event
async def on_message_edit(before, after):
    if after.author.bot:
        return
    if after.channel.id in automod_exceptions:
        return  # Skip Automod for exempted channels

    # Prüfe, ob der Spamschutz aktiv ist
    if spam_protection_enabled and after.channel.id not in automod_exceptions:
        # Lösche bearbeitete Nachrichten mit Links
        if any(link in after.content for link in ['http://', 'https://', 'www.']):
            await after.delete()
            await after.channel.send(f"{after.author.mention}, Links sind in diesem Kanal nicht erlaubt.")
            return

        now = datetime.now()
        if after.author.id in last_message:
            delta = now - last_message[after.author.id]
            if delta < timedelta(seconds=1):
                # Nachrichtenintervall zu kurz (hier 1 Sekunde), daher könnte es Spam sein
                await after.delete()

                # Nachricht an den Spammer senden
                dm_channel = after.author.dm_channel
                if dm_channel is None:
                    dm_channel = await after.author.create_dm()

                server_name = after.guild.name if after.guild else "einem Server"
                await dm_channel.send(f"{after.author.mention}, Spamme nicht! Du hast auf {server_name} gespammt.")

        # Speichere die Zeit der letzten Nachricht des Nutzers
        last_message[after.author.id] = now

    await bot.process_commands(after)  # Verarbeitet auch die restlichen Befehle


@bot.command(name='tempautomodon')
@commands.has_permissions(administrator=True)
async def tempautomodon(ctx):
    global spam_protection_enabled
    if not spam_protection_enabled:
        spam_protection_enabled = True
        await ctx.send("Spamschutz wurde aktiviert.")
        save_automod_settings()
    else:
        await ctx.send("Spamschutz ist bereits aktiviert.")


@bot.command(name='tempautomodoff')
@commands.has_permissions(administrator=True)
async def tempautomodoff(ctx):
    global spam_protection_enabled
    if spam_protection_enabled:
        spam_protection_enabled = False
        await ctx.send("Spamschutz wurde deaktiviert.")
        save_automod_settings()
    else:
        await ctx.send("Spamschutz ist bereits deaktiviert.")


# Hier Beginnt die Support Logik
async def load_support_channel():
    global support_channel_id
    try:
        with open(support_channel_file, "r") as file:
            support_channel_id = int(file.read().strip())
        print("Support-Kanal erfolgreich geladen.")
    except FileNotFoundError:
        print("Datei support_channel.txt nicht gefunden. Es wurde kein Support-Kanal geladen.")
    except Exception as e:
        print(f"Fehler beim Laden des Support-Kanals: {e}")


async def save_support_channel():
    try:
        with open(support_channel_file, "w") as file:
            file.write(str(support_channel_id))
        print("Support-Kanal erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern des Support-Kanals: {e}")


# Support Befehle werden hier Regestriert
@bot.command(name='tempaddsup')
async def tempaddsup(ctx):
    if ctx.author.guild_permissions.administrator:
        category = ctx.channel.category
        if category:
            overwrites = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=True),
                ctx.author: discord.PermissionOverwrite(read_messages=True, send_messages=True)
            }
            global support_channel_id
            support_channel = await category.create_text_channel('📂𝗧𝗶𝗰𝗸𝗲𝘁-𝗲𝗿𝘀𝘁𝗲𝗹𝗹𝗲𝗻', overwrites=overwrites)

            # Nachricht mit Reaktion (Emote) für Ticketöffnung
            embed = discord.Embed(
                title="**Support-Kanal**",
                description="Reagiere auf das Brief Emoji 📧, um ein Support-Ticket zu öffnen.\n"
                            "Sobald ein Moderator oder ein Admin das Ticket sieht, wird er sich im geöffneten\n"
                            "Ticket, links in der Liste (Erkennbar durch Erwähnung deines Namen) bei dir melden.",
                color=0x00ff00
            )
            msg = await support_channel.send(embed=embed)
            await msg.add_reaction('📧')

            await ctx.send(f"Support-Kanal '{support_channel.name}' "
                           f"erfolgreich in der Kategorie '{category.name}' erstellt.")

            # Speichere den Support-Kanal in der Datei
            support_channel_id = support_channel.id
            await save_support_channel()
        else:
            await ctx.send("Dieser Befehl muss in einer Kategorie ausgeführt werden.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


@bot.command(name='tempremovesup')
async def tempremovesup(ctx):
    global support_channel_id
    if ctx.author.guild_permissions.administrator:
        if support_channel_id:
            support_channel = ctx.guild.get_channel(support_channel_id)
            if support_channel and support_channel.name == '📂𝗧𝗶𝗰𝗸𝗲𝘁-𝗲𝗿𝘀𝘁𝗲𝗹𝗹𝗲𝗻':
                await support_channel.delete()
                support_channel_id = None
                await save_support_channel()
                await ctx.send("Support-Kanal erfolgreich gelöscht.")
            else:
                await ctx.send("Der gespeicherte Support-Kanal existiert nicht mehr oder wurde umbenannt.")
        else:
            await ctx.send("Es wurde noch kein Support-Kanal erstellt.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


# Ticket-system Logik
@bot.event
async def on_raw_reaction_add(payload):
    if str(payload.emoji) == '📧':
        guild = bot.get_guild(payload.guild_id)
        member = guild.get_member(payload.user_id)
        if member.bot:
            return

        # Check if the command was used in a specific category
        category_channel = None
        if payload.channel_id == support_channel_id:
            category_channel = guild.get_channel(payload.channel_id)
        else:
            # Implement logic to find the category where the command was used
            message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
            if message.content.startswith('/tempaddsup'):
                # Assuming /tempaddsup is the command used to initiate ticket creation
                category_channel = message.channel.category

        if not category_channel:
            return

        # Check if a channel for this user already exists in the category
        for channel in category_channel.category.text_channels:
            if channel.name == f"ticket-{member.display_name.lower()}":
                await member.send(f"Du hast bereits ein offenes Ticket: {channel.mention}")
                return

        # Create a new text channel for the support ticket in the same category
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            member: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ticket_channel = await category_channel.category.create_text_channel(
            f"ticket-{member.display_name.lower()}", overwrites=overwrites)

        # Embed for the new ticket creation message
        embed = discord.Embed(
            title="Support-Ticket erstellt",
            description=(
                f"**{member.mention}, Dein Support-Ticket wurde erstellt.**\n "
                f"Es wird sich bald jemand um dich Kümmern.\n "
                f"Bitte beschreibe dein Anliegen in der Zwischenzeit.\n"
                f"Reagiere mit 🔒, um das Ticket zu schließen."
            ),
            color=0x00ff00
        )
        close_message = await ticket_channel.send(embed=embed)
        await close_message.add_reaction('🔒')

        # Remove the initial reaction on the original message
        original_message = await bot.get_channel(payload.channel_id).fetch_message(payload.message_id)
        await original_message.remove_reaction('📧', member)

        # Store the closing emoji's message ID in the channel's topic
        await ticket_channel.edit(topic=str(close_message.id))

        # Inform the user via DM
        await member.send(f"Danke das du DayXTemp nutzt. Dein Support-Ticket wurde erstellt: {ticket_channel.mention}")

    elif str(payload.emoji) == '🔒':
        guild = bot.get_guild(payload.guild_id)
        channel = guild.get_channel(payload.channel_id)
        member = guild.get_member(payload.user_id)
        if channel and channel.topic and channel.topic.isdigit():
            close_message_id = int(channel.topic)
            if payload.message_id == close_message_id:
                await channel.send("Dieses Ticket wird geschlossen...")
                await asyncio.sleep(3)  # Wait for 3 seconds before deleting the channel
                await channel.delete()


# Inititialisiert die Sicherungsdateien der Ignoierten Kanäle
async def load_ignored_channels():
    global ignored_channels
    try:
        with open(ignored_channels_file, "r") as file:
            for line in file:
                line = line.strip()
                if line:
                    channel_id = int(line)
                    ignored_channels.add(channel_id)
        print("Ignorierte Kanäle erfolgreich geladen.")
    except FileNotFoundError:
        print("Datei ignored_channels.txt nicht gefunden. Es werden keine Kanäle geladen.")
    except Exception as e:
        print(f"Fehler beim Laden der ignorierten Kanäle: {e}")


async def load_private_channels():
    global private_channels
    try:
        with open(private_channels_file, "r") as file:
            for line in file:
                line = line.strip()
                if line:
                    member_id, channel_id = map(int, line.split(":"))
                    channel = await bot.fetch_channel(channel_id)
                    if channel:
                        private_channels[member_id] = channel
                    else:
                        print(f"Kanal mit ID {channel_id} existiert nicht mehr.")
        print("Private Kanäle erfolgreich geladen.")
    except FileNotFoundError:
        print("Datei private_channels.txt nicht gefunden. Es werden keine privaten Kanäle geladen.")
    except Exception as e:
        print(f"Fehler beim Laden der privaten Kanäle: {e}")


async def save_private_channels():
    try:
        with open(private_channels_file, "w") as file:
            for member_id, channel in private_channels.items():
                file.write(f"{member_id}:{channel.id}\n")
        print("Private Kanäle erfolgreich gespeichert.")
    except Exception as e:
        print(f"Fehler beim Speichern der privaten Kanäle: {e}")


# Die überwachungs-Schleife der leeren Kanäle
@tasks.loop(seconds=30)  # Schleife, die alle 30 Sekunden ausgeführt wird
async def check_empty_private_channels():
    to_delete = []
    for member_id, channel in private_channels.items():
        if len(channel.members) == 0:
            to_delete.append(member_id)
    for member_id in to_delete:
        await delete_private_channel(member_id)
    await save_private_channels()


# Definiere eine globale Variable oder eine Klasse, um den Zustand zu verfolgen
user_limit_asked = {}


# Temporäre Kanäle Logik
@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot or (before.channel and before.channel.id in ignored_channels) or (
            after.channel and after.channel.id in ignored_channels):
        return

    before_channel = before.channel
    after_channel = after.channel

    # Reload channels to ensure they are up-to-date
    if before_channel:
        before_channel = await bot.fetch_channel(before_channel.id)
    if after_channel:
        after_channel = await bot.fetch_channel(after_channel.id)

    if before_channel != after_channel:
        # Check if the member was the last one in a private channel
        if before_channel and before_channel.id in private_channels:
            if len(before_channel.members) == 0:
                await delete_private_channel(member.id)
                await save_private_channels()
                return

        # Logic for creating private channels
        if after_channel is not None and len(after_channel.members) == 1:
            if member.id not in private_channels:
                private_channels[member.id] = await create_private_channel(member, after_channel)
                await save_private_channels()

            # Move member to their private channel first
            await member.move_to(private_channels.get(member.id, None))

            # Check if we already asked about user limit
            if member.id not in user_limit_asked or not user_limit_asked[member.id]:
                user_limit_asked[member.id] = True

                # Wait for them to join and then ask about user limit
                await asyncio.sleep(5)  # Wait for 5 seconds before asking about user limit
                await welcome_private_channel(member, private_channels.get(member.id, None))

        elif before_channel is not None:
            if member.id in private_channels:
                if len(before_channel.members) == 0:
                    await delete_private_channel(member.id)
                    await save_private_channels()
                elif member.id == list(private_channels.keys())[0]:
                    for channel_member in before_channel.members:
                        if channel_member != member:
                            await move_creator(member.id, channel_member)
                            await save_private_channels()
                            break


async def move_creator(creator_id, new_member):
    private_channel = private_channels.pop(creator_id)
    await private_channel.set_permissions(new_member, connect=True, manage_channels=True, manage_permissions=True)
    private_channels[new_member.id] = private_channel
    await save_private_channels()


async def delete_private_channel(member_id):
    if member_id in private_channels:
        private_channel = private_channels.pop(member_id)
        await private_channel.delete()
        await save_private_channels()


async def create_private_channel(member, original_channel):
    overwrites = {target: perm for target, perm in original_channel.overwrites.items()}
    private_channel_name = f'{member.display_name}s Party'
    channel = await original_channel.category.create_voice_channel(private_channel_name, overwrites=overwrites)
    return channel


# Nutzerlimitierung Logik
async def welcome_private_channel(member, channel):
    try:
        await channel.send(f"Willkommen in deinem privaten Sprachkanal, {member.mention}. "
                           f"Möchtest du die Nutzerzahl deines privaten Kanals limitieren? "
                           f"Sollte dies der Fall sein, antworte mit ja.")

        def check(message):
            return message.author == member and message.channel == channel

        try:
            msg = await bot.wait_for("message", timeout=30, check=check)
            if msg.content.lower().strip() == 'ja':
                await channel.send("Wie viele Benutzer sollen maximal in deinem Kanal sein? "
                                   "Beachte bitte, dass du maximal 99 einstellen kannst.")

                try:
                    max_users_msg = await bot.wait_for("message", timeout=30, check=check)
                    max_users = int(max_users_msg.content.strip())

                    if max_users <= 0:
                        await channel.send("Ungültige Eingabe. Die maximale Nutzerzahl muss größer als 0 sein.")
                    else:
                        await channel.edit(user_limit=max_users)
                        await channel.send(f"Die maximale Nutzerzahl dieses Kanals wurde auf {max_users} gesetzt.")

                except asyncio.TimeoutError:
                    await channel.send("Zeitüberschreitung. "
                                       "Die Einstellung der maximalen Nutzerzahl wurde abgebrochen.")

                except ValueError:
                    await channel.send("Ungültige Eingabe. Bitte antworte mit einer Zahl.")

            else:
                await channel.send("Keine Nutzerzahlbeschränkung gewünscht. "
                                   "Der Kanal bleibt offen für alle Mitglieder.")

        except asyncio.TimeoutError:
            await channel.send("Zeitüberschreitung. Die Abfrage wurde abgebrochen.")

        finally:
            # Reset user_limit_asked after handling the user's response
            user_limit_asked[member.id] = False

    except discord.errors.Forbidden:
        print(f"Der Bot hat keine Berechtigung, eine Nachricht in den Kanal {channel.name} zu senden.")


# Befehl Regestrierung
@bot.command()
async def tempignore(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(title="Ignorierte Sprachkanäle",
                              description="Wähle die Kanäle aus, die der Bot temporär ignorieren soll:")
        voice_channels = [channel for channel in ctx.guild.voice_channels if channel.id not in ignored_channels]
        if not voice_channels:
            embed.add_field(name="Keine verfügbaren Sprachkanäle", value="Es gibt keine Sprachkanäle zum Ignorieren.")
        else:
            for index, channel in enumerate(voice_channels):
                embed.add_field(name=f"{index + 1}. {channel.name}", value=f"Kanal ID: {channel.id}", inline=False)
            embed.set_footer(
                text="Zum Auswählen, schreibe eine Kanalnummer, trenne für mehr. 'cancel' zum Abbrechen.")
        await ctx.send(embed=embed)

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            if msg.content.lower() == 'cancel':
                await ctx.send("Befehl abgebrochen.")
                return

            channel_indices = [int(index.strip()) - 1 for index in msg.content.split() if index.strip().isdigit()]
            for index in channel_indices:
                if 0 <= index < len(voice_channels):
                    channel_id = voice_channels[index].id
                    ignored_channels.add(channel_id)
                    await ctx.send(f"Der Kanal '{voice_channels[index].name}' wird temporär ignoriert.")
                    # Verweigere Mitgliedern die Erlaubnis, den ignorierten Kanal zu betreten
                    channel = discord.utils.get(ctx.guild.voice_channels, id=channel_id)
                    await channel.set_permissions(ctx.guild.default_role, connect=False)
                    # Schreibe den Kanal in die Textdatei
                    with open(ignored_channels_file, "a") as file:
                        file.write(str(channel_id) + "\n")
                else:
                    await ctx.send("Ungültige Auswahl. Der Befehl wurde abgebrochen.")
        except asyncio.TimeoutError:
            await ctx.send("Abbruch, Zeitüberschreitung.")
        except ValueError:
            await ctx.send("Ungültige Eingabe. Bitte antworte mit den Nummern der Kanäle.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


@bot.command()
async def tempunignore(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(title="Ignorierte Sprachkanäle",
                              description="Wähle die Kanäle aus, die du nicht mehr ignorieren möchtest:")
        if not ignored_channels:
            embed.add_field(name="Keine ignorierten Sprachkanäle", value="Es wurden keine Sprachkanäle ignoriert.")
        else:
            for index, channel_id in enumerate(ignored_channels):
                channel = discord.utils.get(ctx.guild.voice_channels, id=channel_id)
                embed.add_field(name=f"{index + 1}. {channel.name}", value=f"Kanal ID: {channel.id}", inline=False)
            embed.set_footer(
                text="Zum Auswählen, schreibe eine Kanalnummer, trenne für mehr. 'cancel' zum Abbrechen.")
        await ctx.send(embed=embed)

        def check(message):
            return message.author == ctx.author and message.channel == ctx.channel

        try:
            msg = await bot.wait_for("message", timeout=60, check=check)
            if msg.content.lower() == 'cancel':
                await ctx.send("Befehl abgebrochen.")
                return

            channel_indices = [int(index.strip()) - 1 for index in msg.content.split() if index.strip().isdigit()]
            channels_to_unignore = [channel_id for index, channel_id in enumerate(ignored_channels) if
                                    index in channel_indices]

            for channel_id in channels_to_unignore:
                channel = discord.utils.get(ctx.guild.voice_channels, id=channel_id)
                ignored_channels.remove(channel_id)
                await ctx.send(f"Der Kanal '{channel.name}' wird nicht mehr ignoriert.")
                # Entferne die Erlaubnis für Mitglieder, den nicht mehr ignorierten Kanal zu betreten
                await channel.set_permissions(ctx.guild.default_role, connect=None)
                # Entferne den Kanal aus der Textdatei
                with open(ignored_channels_file, "r+") as file:
                    lines = file.readlines()
                    file.seek(0)
                    for line in lines:
                        if str(channel_id) not in line.strip():
                            file.write(line)
                    file.truncate()
        except asyncio.TimeoutError:
            await ctx.send("Zeitüberschreitung. Der Befehl wurde abgebrochen.")
        except ValueError:
            await ctx.send("Ungültige Eingabe. Bitte antworte mit den Nummern der Kanäle.")
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


@bot.command()
async def templist(ctx):
    if ctx.author.guild_permissions.administrator:
        embed = discord.Embed(title="Liste der ignorierten Sprachkanäle",
                              description="Hier sind die aktuell ignorierten Sprachkanäle:")
        if not ignored_channels:
            embed.add_field(name="Keine ignorierten Sprachkanäle", value="Es wurden keine Sprachkanäle ignoriert.")
        else:
            for channel_id in ignored_channels:
                channel = discord.utils.get(ctx.guild.voice_channels, id=channel_id)
                embed.add_field(name=channel.name, value=f"Kanal ID: {channel.id}", inline=False)
        await ctx.send(embed=embed)
    else:
        await ctx.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


# Info Befehle Logik
@bot.command(name='temphelp')
async def temphelp(context):
    embed = discord.Embed(
        title="Übersicht der Bot Befehle",
        description=(
            "- **Unter /tempinfo bekommst du weitere Informationen.**\n\n"
            "- **/tempignore** \n Füge Kanäle hinzu die nicht vom Bot beeinflusst werden sollen.\n\n"
            "- **/tempunignore** \n Löscht Kanäle von der Liste der ignorierten Kanäle.\n\n"
            "- **/templist** \n Zeigt alle aktuell ignorierten Kanäle.\n\n"
            "- **/tempinfo** \n Dieser Befehl zeigt dir, wie du den Bot einrichten kannst.\n\n"
            "- **/tempaddsup** \n Erstellt einen Support-Kanal in der Kategorie des Aufrufs.\n\n"
            "- **/tempremovesup** \n Löscht den erstellten Support-Kanal.\n\n"
            "- **/tempautomod** \n Prüft ob der Automod Spamschutz gerade aktiv ist.\n\n"
            "- **/tempautomodon** \n Aktiviert den Automod Spamschutz.\n\n"
            "- **/tempautomodoff** \n Deaktiviert den Automod Spamschutz.\n\n"
            "- **/tempautomodadd** \n fügt Textkanäle einer Ausnahmeliste für den Automod hinzu.\n\n"
            "- **/tempautomodremove** \n Enternt hinzugefügte Ausnahme-Kanäle.\n\n"
            "- **/tempautomodlist** \n Zeigt alle textkanäle an die sich in der Ausnahmeliste befinden.\n\n"
        ),
        color=0x00ff00  # You can choose a color you like
    )
    await context.send(embed=embed)


@bot.command(name='tempinfo')
async def tempinfo(context):
    embed = discord.Embed(
        title="Vielen Dank, dass Sie unseren DayXTemp Bot verwenden.",
        description=(
            "**Erste Schritte:**\n\n"
            "- **Automatische Umwandlung:**\n"
            "  Nach dem Hinzufügen des Bots zu Ihrem Discord-Server "
            "  werden alle Sprachkanäle automatisch in temporäre Kanäle umgewandelt.\n"
            "  Möchten Sie bestimmte Kanäle nicht als temporäre Kanäle nutzen, "
            "  fügen Sie diese mit dem Befehl /tempignore der Ignorierliste hinzu.\n\n"
            "- **Support Funktion:**\n"
            "  Mit diesen Bot kannst du auch ein Ticketsystem erstellen."
            "  Erstelle eine Support Kategorie der einen Text-Kanal beinhaltet, (z.B ´Commands´),"
            "  den nur Administrator oder der Leader selbst sehen kann."
            "  Wende in diesen Kanal dann den Befehl /tempaddsup an um ein"
            "  Text-Kanal zu erstellen der das Ticketsystem beinhaltet."
            "  Das Ticketsystem Funktioniert dann innerhalb der Support Kategorie.\n\n"
            "- **Nutzerlimitierung:**\n"
            "  Wenn ein Nutzer einen Privaten Kanal erstellt,"
            "  hat er die möglichkeit in dessen Chat,"
            "  (Rechts das Chatsymbol vom Privatkanal) mit dem bot zu interagieren."
            "  Dort kann jeder Member über die Slotzahl "
            "  seines Privaten Kanal´s entscheiden.\n\n"
            "- **Kanal-Löschung:**\n"
            "  Sollte ein temporärer Kanal nicht sofort gelöscht werden, "
            "  wenn alle Benutzer ihn verlassen haben, warten Sie bitte 30 Sekunden.\n"
            "  Der Bot überprüft regelmäßig die leeren Kanäle und löscht sie beim zweiten Durchlauf.\n\n"
            "- **Spamschutz**\n"
            "  Natürlich unterstützt der Bot dich auch bei der Moderation.\n"
            "  Mit dem Befehl /tempautomodon kannst du den Spamschutz aktivieren.\n"
            "  Mit /tempautomodoff kannst du ihn wieder deaktivieren.\n"
            "  Der Spamschutz ist grundsätzlich in allen Textkanälen aktiv,\n"
            "  es sei denn du möchtest in ein paar Kanälen eine Ausnahme hinzufügen.\n"
            "  Sollte dies der Fall sein, nutze den befehl /tempautomodadd. Damit kannst du\n"
            "  Kanäle einer Ausnahmeliste hinzufügen.\n "
            " Mit /tempautomodremove kannst du sie wieder entfernen.\n"
            "  Mit /temautomodlist kannst du sehen\n"
            "  welche Kanäle sich in der Ausnahmeliste befinden.\n"
            "- **Support:** https://discord.gg/8XXmdavvqc\n\n"
            "- **Entwickelt von Lets Chico** https://www.youtube.com/c/LetsChico"
        ),
        color=0x00ff00  # Farbauswahl
    )
    await context.send(embed=embed)


@bot.command(name='temprestart')
async def temprestart(context):
    if context.author.guild_permissions.administrator:
        await context.send("Bot wird neu gestartet...")
        await save_private_channels()  # Speicher private Kanäle vor dem Neustart
        process = psutil.Process(os.getpid())
        for handler in process.open_files() + process.connections():
            os.close(handler.fd)
        python = sys.executable
        os.execl(python, python, *sys.argv)
    else:
        await context.send("Du hast nicht die erforderlichen Berechtigungen, um diesen Befehl auszuführen.")


# Error
@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        await ctx.send("Dieser Befehl existiert nicht.")
    else:
        # Standardbehandlung für andere Fehler
        raise error

bot.run(config.BOT_TOKEN)  # Starte den Bot mit dem Token aus der config.py-Datei