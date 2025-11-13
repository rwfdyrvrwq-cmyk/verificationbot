import os
import time
import asyncio
from pathlib import Path
import discord
from discord import app_commands, ui
from discord.ext import commands
from dotenv import load_dotenv
import aiohttp
import re
from io import BytesIO
from PIL import Image, ImageFilter

load_dotenv()

from scraper import get_character_info_async
from wiki_scraper import scrape_wiki_page
from shop_scraper import scrape_shop_items
from scanner_client import get_char_data
from swf2png_client import SWF2PNGClient


intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
http_session = None
RENDER_OUTPUT_DIR = Path("renders")
swf_renderer = SWF2PNGClient()


def _polish_render(image_bytes: bytes) -> Image.Image:
    """Upscale, smooth, and center the render onto a 1080p canvas."""
    base = Image.open(BytesIO(image_bytes)).convert("RGBA")
    upscale_factor = 4
    upscaled = base.resize(
        (base.width * upscale_factor, base.height * upscale_factor),
        Image.LANCZOS)
    smoothed = upscaled.filter(ImageFilter.GaussianBlur(1.2)).filter(
        ImageFilter.DETAIL)
    canvas_size = (1920, 1080)
    base_scale = min(canvas_size[0] / smoothed.width,
                     canvas_size[1] / smoothed.height)
    scale = base_scale * 0.7
    new_size = (int(smoothed.width * scale), int(smoothed.height * scale))
    resized = smoothed.resize(new_size, Image.LANCZOS)
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    pos = ((canvas_size[0] - new_size[0]) // 2,
           (canvas_size[1] - new_size[1]) // 2)
    canvas.paste(resized, pos, resized)
    base.close()
    return canvas


def _save_gif(image: Image.Image, destination: Path) -> None:
    palette_img = image.convert("P", palette=Image.ADAPTIVE, colors=255)
    transparent_index = palette_img.getpixel((0, 0))
    palette_img.info["transparency"] = transparent_index
    palette_img.save(
        destination,
        format="GIF",
        transparency=transparent_index,
        optimize=True,
        save_all=False,
    )


async def generate_character_render(username: str, *, use_cosmetics: bool = False):
    """Return (Path, error_message) tuple for rendered character."""
    try:
        if not await swf_renderer.is_available():
            return None, "⚠️ Character renderer offline."
    except Exception as exc:
        print(f"Renderer availability check failed: {exc}")
        return None, "⚠️ Character renderer unavailable."

    try:
        result = await swf_renderer.render_character(
            username, use_cosmetics=use_cosmetics)
        polished = _polish_render(result.image_bytes)
        RENDER_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        suffix = "cos" if use_cosmetics else "gear"
        file_path = RENDER_OUTPUT_DIR / f"{username}_{suffix}_{int(time.time())}.gif"
        _save_gif(polished, file_path)
        polished.close()
        return file_path, None
    except Exception as exc:
        print(f"Renderer error for {username}: {exc}")
        return None, "⚠️ Failed to generate character render."


class FinishVerificationView(ui.View):
    def __init__(self, channel: discord.TextChannel, user: discord.Member, ign: str, has_mismatch: bool = False):
        super().__init__()
        self.channel = channel
        self.user = user
        self.ign = ign
        
        # Always add reject button for admin discretion
        self.add_item(RejectButton(channel, user))
    
    @ui.button(label="Finish Verification", style=discord.ButtonStyle.success)
    async def finish_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Only administrators can complete verification.", ephemeral=True)
                return
            
            nickname_changed = False
            try:
                await self.user.edit(nick=self.ign)
                nickname_changed = True
            except discord.Forbidden:
                await interaction.response.send_message(
                    f"⚠️ **Verification complete!** However, I don't have permission to change your nickname.\n\n"
                    f"**Please ask a server admin to:**\n"
                    f"1. Give my role the **Manage Nicknames** permission\n"
                    f"2. Move my role **above** your highest role in the server settings\n\n"
                    f"You can manually change your nickname to: `{self.ign}`\n"
                    f"This channel will be deleted in 5 seconds.",
                    ephemeral=True
                )
                await asyncio.sleep(5)
            except:
                pass
            
            if nickname_changed:
                await interaction.response.send_message(f"✅ Nickname changed to `{self.ign}` and verification complete!", ephemeral=True)
                
                try:
                    await self.user.send(f"✅ **Verification Approved!**\n\nYour verification has been approved by an administrator. Your nickname has been updated to `{self.ign}`.")
                except:
                    pass
                
                await asyncio.sleep(1)
            
            await self.channel.delete()
        except Exception as e:
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(f"❌ Error: {str(e)}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            except:
                pass


class RejectButton(ui.Button):
    def __init__(self, channel: discord.TextChannel, user: discord.Member):
        super().__init__(label="Reject Application", style=discord.ButtonStyle.danger)
        self.channel = channel
        self.user = user
    
    async def callback(self, interaction: discord.Interaction):
        try:
            if not interaction.user.guild_permissions.administrator:
                await interaction.response.send_message("❌ Only administrators can reject applications.", ephemeral=True)
                return
            
            await interaction.response.send_message("✅ Application rejected. Notifying user...", ephemeral=True)
            
            try:
                await self.user.send(
                    "❌ **Verification Rejected**\n\n"
                    "Your application has been rejected because the details you provided do not match with the records on your CharPage.\n\n"
                    "Please ensure:\n"
                    "• Your IGN (In-Game Name) is correct\n"
                    "• Your Guild name matches exactly (or is left blank if you have none)\n\n"
                    "You may submit a new verification request with the correct information."
                )
            except:
                await interaction.followup.send("⚠️ Could not send DM to user. They may have DMs disabled.", ephemeral=True)
            
            await asyncio.sleep(2)
            await self.channel.delete()
        except Exception as e:
            try:
                await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)
            except:
                pass


class VerificationModal(ui.Modal, title="Character Verification"):
    ign = ui.TextInput(label="Character IGN (In-Game Name)", placeholder="Enter your character name (used as ID)", required=True, max_length=100)
    guild = ui.TextInput(label="Guild (leave blank if none)", placeholder="Enter your guild or leave empty", required=False, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)

            user_ign = self.ign.value.strip()
            user_guild = self.guild.value.strip() if self.guild.value else ""

            char_id = user_ign

            if http_session is None:
                await interaction.followup.send("❌ Bot is still starting up. Please try again in a moment.", ephemeral=True)
                return

            info = await get_character_info_async(char_id, http_session)

            page_name = info.get("name", "").strip() if info.get("name") else ""
            page_guild = info.get("guild", "").strip() if info.get("guild") else ""

            def normalize(s: str) -> str:
                return " ".join(s.lower().split()) if s else ""

            name_match = normalize(user_ign) == normalize(page_name) if page_name else False
            guild_match = normalize(user_guild) == normalize(page_guild) if page_guild or user_guild else (not page_guild and not user_guild)

            has_mismatch = not (name_match and guild_match)
            
            embed = discord.Embed(title="Verification Result", color=discord.Color.green() if (name_match and guild_match) else discord.Color.orange())
            embed.add_field(name="Character IGN (used as ID)", value=char_id, inline=False)
            embed.add_field(name="IGN Check", value=f"{'✅ MATCH' if name_match else '❌ MISMATCH'}\nYou entered: `{user_ign}`\nPage shows: `{page_name}`", inline=False)
            embed.add_field(name="Guild Check", value=f"{'✅ MATCH' if guild_match else '❌ MISMATCH'}\nYou entered: `{user_guild if user_guild else '(empty)'}`\nPage shows: `{page_guild if page_guild else '(none)'}`", inline=False)
            
            if name_match and guild_match:
                embed.add_field(name="Status", value="✅ **Verification Successful!**", inline=False)
            else:
                embed.add_field(name="Status", value="⚠️ **Verification Pending** - Mismatches detected. Admin review required.", inline=False)
            
            embed.add_field(name="User", value=f"{interaction.user.mention} ({interaction.user.name})", inline=False)
            
            try:
                guild = interaction.guild
                if guild:
                    admin_overwrites = {}
                    if guild.owner:
                        admin_overwrites[guild.owner] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                    
                    admin_role = discord.utils.find(lambda r: r.permissions.administrator, guild.roles)
                    if admin_role:
                        admin_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                    
                    admin_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                    channel_name = f"verification-{interaction.user.name.lower().replace(' ', '-')}"
                    channel = await guild.create_text_channel(
                        channel_name,
                        overwrites=admin_overwrites,
                        topic=f"Verification record for {interaction.user.name} (IGN: {user_ign})"
                    )
                    finish_view = FinishVerificationView(channel, interaction.user, user_ign, has_mismatch)
                    await channel.send(embed=embed, view=finish_view)
                    
                    user_confirmation = discord.Embed(
                        title="⏳ Verification Submitted",
                        description="Please wait while the admins verify and approve your request.\n\nYou will be notified once an admin has reviewed your verification.",
                        color=discord.Color.blue()
                    )
                    await interaction.followup.send(embed=user_confirmation, ephemeral=True)
            except Exception as channel_err:
                error_embed = discord.Embed(
                    title="⚠️ Verification Result",
                    description="Verification matched but could not create admin channel. Please contact an admin.",
                    color=discord.Color.orange()
                )
                error_embed.add_field(name="Error", value=str(channel_err)[:200], inline=False)
                await interaction.followup.send(embed=error_embed, ephemeral=True)
            
        except Exception as e:
            error_msg = f"❌ Verification failed: {str(e)}"
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(error_msg[:2000], ephemeral=True)
                else:
                    await interaction.followup.send(error_msg[:2000], ephemeral=True)
            except:
                pass


class VerifyButton(ui.View):
    def __init__(self):
        super().__init__()

    @ui.button(label="Start Verification", style=discord.ButtonStyle.primary)
    async def verify_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            modal = VerificationModal()
            await interaction.response.send_modal(modal)
        except Exception as e:
            error_msg = f"❌ Failed to open verification form: {str(e)}"
            try:
                await interaction.response.send_message(error_msg, ephemeral=True)
            except:
                pass


class HelpOptionsView(ui.View):
    def __init__(self):
        super().__init__()

    @ui.button(label="Help?", style=discord.ButtonStyle.primary)
    async def help_button(self, interaction: discord.Interaction, button: ui.Button):
        try:
            dropdown_view = HelpDropdownView()
            await interaction.response.send_message("Select an option from the dropdown below:", view=dropdown_view, ephemeral=True)
        except Exception as e:
            try:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
            except:
                pass


class HelpDropdownView(ui.View):
    def __init__(self):
        super().__init__()
        self.add_item(HelpSelect())


class HelpSelect(ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Daily 4 Man", description="Daily 4 Man content"),
            discord.SelectOption(label="Daily 7 man", description="Daily 7 man content"),
            discord.SelectOption(label="Daily Temple Run", description="Daily Temple Run content"),
            discord.SelectOption(label="Weekly Ultras", description="Weekly Ultras content"),
            discord.SelectOption(label="Ultraspeaker", description="Ultraspeaker content"),
            discord.SelectOption(label="Grimchallenge", description="Grimchallenge content"),
            discord.SelectOption(label="Other", description="Other content"),
        ]
        super().__init__(placeholder="Choose an option...", options=options)

    async def callback(self, interaction: discord.Interaction):
        try:
            selected = self.values[0]
            await interaction.response.send_message(f"You selected: **{selected}**", ephemeral=True)
        except Exception as e:
            try:
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
            except:
                pass


# Wiki command helper classes
class WikiDisambiguationSelect(discord.ui.Select):
    """Dropdown select menu for disambiguation pages"""

    def __init__(self, related_items):
        options = []
        for item in related_items[:25]:  # Discord allows up to 25 options
            options.append(
                discord.SelectOption(label=item['name'][:100],
                                     description="Click to view details"[:100],
                                     value=item['name']))

        super().__init__(placeholder="Choose an item to view details...",
                         min_values=1,
                         max_values=1,
                         options=options)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

        item_name = self.values[0]
        wiki_data = await scrape_wiki_page(item_name)

        if not wiki_data:
            await interaction.followup.send(
                f"❌ Could not fetch details for {item_name}", ephemeral=True)
            return

        # Fetch merge requirements if shop is present
        shop = wiki_data.get('shop')
        if shop:
            shop_name = shop.split(' - ')[0].strip() if ' - ' in shop else shop
            shop_data = await scrape_shop_items(shop_name)
            if shop_data and shop_data.get('items'):
                # Find this specific item in the shop to get merge requirements
                for item in shop_data['items']:
                    if wiki_data['title'] in item.get('name', ''):
                        wiki_data['merge_requirements'] = item.get('price')
                        break

        embed = await create_wiki_embed(wiki_data)

        # Add interactive buttons for quest if present
        view = ItemDetailsView(wiki_data) if wiki_data.get('quest') else None

        if view:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)


class WikiDisambiguationView(discord.ui.View):
    """View with dropdown for disambiguation pages"""

    def __init__(self, related_items):
        super().__init__(timeout=180)
        self.add_item(WikiDisambiguationSelect(related_items))


class ItemDetailsView(discord.ui.View):
    """View with buttons for quest details"""

    def __init__(self, wiki_data):
        super().__init__(timeout=180)

        # Add quest button if quest is present
        quest = wiki_data.get('quest')
        if quest:
            # Extract quest name (remove "reward from" or similar prefixes), preserving case
            quest_name = quest
            if 'reward from' in quest.lower():
                # Find position case-insensitively, then extract with original casing
                idx = quest.lower().find('reward from')
                if idx != -1:
                    quest_name = quest[idx + len('reward from'):].strip()
            elif 'quest:' in quest.lower():
                # Find position case-insensitively, then extract with original casing
                idx = quest.lower().find('quest:')
                if idx != -1:
                    quest_name = quest[idx + len('quest:'):].strip()

            quest_button = discord.ui.Button(
                label=f"📜 {quest_name[:35]}",
                style=discord.ButtonStyle.success,
                custom_id=f"quest_{quest_name[:50]}")
            quest_button.callback = self.create_quest_callback(quest_name)
            self.add_item(quest_button)

    def create_quest_callback(self, quest_name: str):

        async def callback(interaction: discord.Interaction):
            await interaction.response.defer()

            quest_data = await scrape_wiki_page(quest_name)

            if not quest_data:
                await interaction.followup.send(
                    f"❌ Could not fetch details for {quest_name}",
                    ephemeral=True)
                return

            embed = discord.Embed(title=f"📜 {quest_data['title']}",
                                  url=quest_data['url'],
                                  color=discord.Color.gold())

            description = quest_data.get('description')
            if description:
                if len(description) > 400:
                    description = description[:397] + "..."
                embed.description = description

            location_info = quest_data.get('location')
            if location_info:
                embed.add_field(name="📍 Location",
                                value=location_info,
                                inline=False)

            requirements = quest_data.get('requirements', [])
            if requirements:
                req_text = '\n'.join([f"• {req}" for req in requirements[:5]])
                embed.add_field(name="❗ Requirements",
                                value=req_text,
                                inline=False)

            notes = quest_data.get('notes', [])
            if notes:
                notes_text = '\n'.join([
                    f"• {note[:150]}{'...' if len(note) > 150 else ''}"
                    for note in notes[:3]
                ])
                embed.add_field(name="📝 Notes", value=notes_text, inline=False)

            embed.set_footer(text="Source: AQW Wiki")

            await interaction.followup.send(embed=embed)

        return callback


def create_wiki_link(item_name: str) -> str:
    """
    Create a wiki link for an item name
    
    Args:
        item_name: The item name to link
        
    Returns:
        Markdown formatted link to AQW wiki
    """
    # AQW Wiki URL format: lowercase with hyphens
    # Example: "Cultist Knife" → "cultist-knife"
    # Example: "King's Echo" → "king-s-echo" (apostrophes become hyphens)

    # Replace apostrophes with hyphens (possessive: "King's" → "King-s")
    slug = item_name.replace("'", "-")
    # Replace spaces with hyphens
    slug = slug.replace(' ', '-')
    # Remove any other special characters except hyphens and alphanumeric
    slug = re.sub(r'[^a-zA-Z0-9-]', '', slug)
    # Convert to lowercase
    slug = slug.lower()
    # Clean up multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Remove leading/trailing hyphens
    slug = slug.strip('-')

    wiki_url = f"http://aqwwiki.wikidot.com/{slug}"
    return f"[{item_name}]({wiki_url})"


def format_item_value(value):
    """Format an item value as clickable link or plain text"""
    if isinstance(value, dict) and 'text' in value:
        # Generate proper wiki link from the full item text instead of using HTML URL
        # (HTML URLs are often incomplete, e.g., "King" instead of "King's Echo")
        return create_wiki_link(value['text'])
    elif isinstance(value, str):
        return value
    return str(value)


async def create_wiki_embed(wiki_data):
    """Create a Discord embed from wiki data"""
    title = wiki_data.get('title', 'Unknown')
    url = wiki_data.get('url', '')

    embed = discord.Embed(title=f"📖 {title}",
                          url=url,
                          color=discord.Color.blue())

    description = wiki_data.get('description')
    if description:
        if len(description) > 400:
            description = description[:397] + "..."
        embed.description = description

    item_type = wiki_data.get('type')
    if item_type:
        embed.add_field(name="🏷️ Type", value=item_type, inline=True)

    level = wiki_data.get('level')
    if level:
        embed.add_field(name="⭐ Level Required", value=level, inline=True)

    rarity = wiki_data.get('rarity')
    if rarity:
        embed.add_field(name="💎 Rarity", value=rarity, inline=True)

    damage = wiki_data.get('damage')
    if damage:
        embed.add_field(name="⚔️ Damage/Stats", value=damage, inline=True)

    how_to_get = []

    # Show locations list if available (for misc items)
    locations_list = wiki_data.get('locations_list', [])
    if locations_list:
        location_links = [create_wiki_link(loc) for loc in locations_list[:10]]
        locations_display = ' • '.join(location_links)
        # Ensure locations don't exceed reasonable length
        if len(locations_display) > 900:
            locations_display = locations_display[:897] + "..."
        how_to_get.append(f"📍 **Locations:** {locations_display}")

    # Show merge text if available (for misc items)
    merge_text = wiki_data.get('merge_text')
    if merge_text:
        # Truncate merge text to prevent Discord embed limit (1024 chars per field)
        # Reserve space for other content in the field
        max_merge_length = 500
        if len(merge_text) > max_merge_length:
            merge_text = merge_text[:max_merge_length - 3] + "..."
        how_to_get.append(f"\n🔨 **Merge:** {merge_text}")

    shop = wiki_data.get('shop')
    if shop:
        shop_parts = shop.split(' - ')
        if len(shop_parts) > 1:
            shop_name = shop_parts[0].strip()
            location_name = shop_parts[1].strip()
            shop_name_link = create_wiki_link(shop_name)
            location_link = create_wiki_link(location_name)
            how_to_get.append(
                f"🏪 **Shop:** {shop_name_link} - {location_link}")
        else:
            shop_link = create_wiki_link(shop)
            how_to_get.append(f"🏪 **Shop:** {shop_link}")

    location = wiki_data.get('location')
    if location and location != shop and not locations_list:
        if len(location) > 150:
            location_display = location[:147] + "..."
        else:
            location_display = location

        location_parts = location_display.split(' - ')
        if len(location_parts) > 1:
            location_name = location_parts[-1].strip()
            location_link = create_wiki_link(location_name)
            location_prefix = ' - '.join(location_parts[:-1])
            location_display = f"{location_prefix} - {location_link}"
        else:
            location_display = create_wiki_link(location_display)

        how_to_get.append(f"\n📍 **Location:** {location_display}")

    quest = wiki_data.get('quest')
    if quest:
        # Extract quest name from ORIGINAL (non-truncated) string, preserving case
        quest_name = quest
        prefix = ""

        if 'reward from' in quest.lower():
            # Find position case-insensitively, then extract with original casing
            idx = quest.lower().find('reward from')
            if idx != -1:
                quest_name = quest[idx + len('reward from'):].strip()
                prefix = "Reward from "
        elif 'quest:' in quest.lower():
            # Find position case-insensitively, then extract with original casing
            idx = quest.lower().find('quest:')
            if idx != -1:
                quest_name = quest[idx + len('quest:'):].strip()
                prefix = ""

        # Create wiki link from full quest name
        quest_link = create_wiki_link(quest_name)

        # Truncate for display only AFTER extracting the name
        if len(quest) > 150:
            quest_display = quest[:147] + "..."
        else:
            quest_display = quest

        # Build the display text
        if prefix:
            how_to_get.append(f"\n📜 **Quest/Reward:** {prefix}{quest_link}")
        else:
            how_to_get.append(f"\n📜 **Quest/Reward:** {quest_link}")

    requirements = wiki_data.get('requirements', [])
    if requirements:
        req_text = '\n'.join([f"❗ {req}" for req in requirements[:3]])
        how_to_get.append(f"\n**Requirements:**\n{req_text}")

    if how_to_get:
        embed.add_field(name="📦 How to Obtain",
                        value='\n'.join(how_to_get),
                        inline=False)

    price = wiki_data.get('price')
    sellback = wiki_data.get('sellback')
    if price or sellback:
        pricing = []
        if price:
            pricing.append(f"💰 **Price:** {price}")
        if sellback:
            pricing.append(f"💵 **Sellback:** {sellback}")

        embed.add_field(name="💲 Pricing",
                        value='\n'.join(pricing),
                        inline=True)

    # Add merge requirements if available
    merge_requirements = wiki_data.get('merge_requirements')
    if merge_requirements:
        # Only show merge requirements if this is actually merge materials (not regular currency)
        # Regular currency examples: "0 AC", "50,000 Gold", "N/A"
        # Merge materials: "Roentgenium of Nulgathx15,Void Crystal Ax1,..."

        # Check if it's regular currency vs merge materials
        # Merge materials have pattern: "ItemNamexQuantity" (e.g., "Roentgenium of Nulgathx15")
        # Currency: "0 AC", "50,000 Gold", "N/A"
        merge_upper = merge_requirements.upper()

        # Check if it has merge material patterns (lowercase 'x' between item name and number)
        has_merge_pattern = False
        for part in merge_requirements.split(','):
            part = part.strip()
            if 'x' in part.lower():
                # Check if there's a number after 'x'
                x_parts = part.lower().rsplit('x', 1)
                if len(x_parts) == 2 and x_parts[1].strip().isdigit():
                    has_merge_pattern = True
                    break

        # If no merge pattern found, check if it's currency
        is_currency = (not has_merge_pattern
                       and (merge_upper in ['N/A', 'NA', 'NONE']
                            or 'AC' in merge_upper or 'GOLD' in merge_upper))

        if not is_currency:
            # Parse merge requirements (format: "Item1x5,Item2x10,Item3x1")
            items = merge_requirements.split(',')
            merge_list = []
            for item in items[:10]:  # Show up to 10 items
                item = item.strip()
                if item:
                    # Try to extract item name and quantity
                    if 'x' in item:
                        parts = item.rsplit('x', 1)
                        if len(parts) == 2:
                            item_name = parts[0].strip()
                            quantity = parts[1].strip()
                            # Verify quantity is numeric (to avoid false positives)
                            if quantity.isdigit():
                                # Create wiki link for the item
                                item_link = create_wiki_link(item_name)
                                merge_list.append(f"• {item_link} x{quantity}")
                            else:
                                merge_list.append(f"• {item}")
                        else:
                            merge_list.append(f"• {item}")
                    else:
                        merge_list.append(f"• {item}")

            if merge_list:
                embed.add_field(name="🔨 Merge Requirements",
                                value='\n'.join(merge_list),
                                inline=False)

    notes = wiki_data.get('notes', [])
    if notes:
        notes_text = '\n'.join([
            f"• {note[:120]}{'...' if len(note) > 120 else ''}"
            for note in notes[:3]
        ])
        embed.add_field(name="📝 Notes", value=notes_text, inline=False)

    embed.set_footer(text="Source: AQW Wiki • Click title to view full page")

    return embed


@bot.event
async def on_ready():
    global http_session
    try:
        if http_session is None:
            http_session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=10),
                connector=aiohttp.TCPConnector(limit=10, ttl_dns_cache=300)
            )
        
        guild_id = os.getenv("GUILD_ID")
        print(f"Bot logged in as {bot.user.name} (ID: {bot.user.id})", flush=True)
        
        try:
            if guild_id:
                guild_obj = discord.Object(id=int(guild_id))
                # Sync commands to the specific guild for faster updates
                bot.tree.copy_global_to(guild=guild_obj)
                synced = await bot.tree.sync(guild=guild_obj)
                print(f"✓ Synced {len(synced)} commands to guild {guild_id}", flush=True)
            else:
                # Fallback to global sync if no guild ID is provided
                synced = await bot.tree.sync()
                print(f"✓ Synced {len(synced)} commands globally (may take up to 1 hour)", flush=True)
                
            print(f"Registered commands: {[cmd.name for cmd in synced]}", flush=True)

        except Exception as e:
            print(f"Failed to sync commands: {e}", flush=True)
            import traceback
            traceback.print_exc()
    except Exception as e:
        print(f"Error in on_ready: {e}", flush=True)


@bot.tree.command(name="verify")
async def verify(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🔐 Account Verification",
        description="Verify AQW account",
        color=discord.Color.blue()
    )
    embed.add_field(name="How to verify", value="1. Click the **Start Verification** button below\n2. Enter your IGN (In-Game Name)\n3. Enter your Guild (or leave blank if you have none)", inline=False)

    view = VerifyButton()
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


@bot.tree.command(name="serverinfo")
@app_commands.default_permissions(administrator=True)
async def serverinfo_command(interaction: discord.Interaction):
    """Shows server information including the Guild ID"""
    embed = discord.Embed(
        title="📊 Server Information",
        color=discord.Color.blue()
    )
    embed.add_field(name="Server Name", value=interaction.guild.name, inline=False)
    embed.add_field(name="Guild ID", value=f"`{interaction.guild.id}`", inline=False)
    embed.add_field(name="Member Count", value=interaction.guild.member_count, inline=False)
    embed.set_footer(text="Copy the Guild ID and add it to your .env file")
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="deployhelper")
@app_commands.default_permissions(administrator=True)
async def deployhelper_command(interaction: discord.Interaction):
    try:
        await interaction.response.defer(ephemeral=False)
        embed = discord.Embed(
            description="​",
            color=discord.Color.blue()
        )
        
        view = HelpOptionsView()
        await interaction.followup.send(embed=embed, view=view)
    except Exception as e:
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"Error: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"Error: {str(e)}", ephemeral=True)
        except:
            pass


@bot.tree.command(
    name='char',
    description='Fetch character details from their AQ.com page.')
@app_commands.describe(username='Character username to look up')
async def char(interaction: discord.Interaction, username: str):
    await interaction.response.defer()

    try:
        # Get character data from the new scraper service
        char_data = await get_char_data(username)

        # Handle errors from the service
        if not char_data or 'error' in char_data:
            error_message = char_data.get('error', 'An unknown error occurred.')
            await interaction.followup.send(
                f'❌ **Could not fetch character data for `{username}`.**\n\n'
                f'**Reason:** {error_message}\n'
                f'Please check the character name or try again later.'
            )
            return

        # Create embed with character information
        char_name = char_data.get('name', username)
        level = char_data.get('level', 'N/A')
        
        embed = discord.Embed(
            title=f"Character Info: {char_name}",
            description=f"**Level {level}**",
            url=f"https://www.aq.com/character.asp?id={username}",
            color=discord.Color.blue()
        )

        # Build the equipment list
        equipment_text = []
        item_slots = ["Class", "Armor", "Helm", "Cape", "Weapon", "Pet"]
        for slot in item_slots:
            item_name = char_data.get(slot.lower())
            if item_name and item_name != "N/A":
                item_link = create_wiki_link(item_name)
                equipment_text.append(f"**{slot}:** {item_link}")
            else:
                equipment_text.append(f"**{slot}:** *None*")

        if equipment_text:
            embed.add_field(
                name="Equipped Items",
                value='\n'.join(equipment_text),
                inline=True
            )

        # Build the cosmetic items list
        cosmetic_text = []
        cosmetic_slots = [
            ("co_helm", "Helm"), 
            ("co_cape", "Cape"), 
            ("co_weapon", "Weapon"), 
            ("co_pet", "Pet")
        ]
        has_cosmetics = False
        for key, display_name in cosmetic_slots:
            item_name = char_data.get(key)
            if item_name and item_name != "N/A":
                has_cosmetics = True
                item_link = create_wiki_link(item_name)
                cosmetic_text.append(f"**{display_name}:** {item_link}")
            else:
                cosmetic_text.append(f"**{display_name}:** *None*")
        
        if has_cosmetics:
            embed.add_field(
                name="Cosmetic Items",
                value='\n'.join(cosmetic_text),
                inline=True
            )
        
        embed.set_footer(text="Click the item names to see details on the AQW Wiki.")
        embed.set_thumbnail(url="https://www.aq.com/images/avatars/1/default_avatar.png") # Generic thumbnail

        render_file, render_error = await generate_character_render(username)
        if render_error and not render_file:
            embed.add_field(name="Renderer Status", value=render_error, inline=False)

        await interaction.followup.send(embed=embed)

        if render_file:
            attachment_name = render_file.name
            file_to_send = discord.File(render_file, filename=attachment_name)
            await interaction.followup.send(file=file_to_send)

    except Exception as e:
        print(f'Error in /char command: {e}')
        import traceback
        traceback.print_exc()
        await interaction.followup.send(
            f'An unexpected error occurred while processing the `/char` command: {str(e)}')


@bot.tree.command(
    name='char_test',
    description='[TEST] Fetch character details from their AQ.com page.')
@app_commands.describe(username='Character username to look up')
async def char_test(interaction: discord.Interaction, username: str):
    await interaction.response.send_message("This is the NEWEST test command. If you see this, the zombie process is dead.", ephemeral=True)


@bot.tree.command(
    name='wiki',
    description='Get detailed information about an item from the AQW Wiki')
@app_commands.describe(
    query='Item name, class, or page (e.g., "Void Highlord", "Malgor\'s Blade")'
)
async def wiki(interaction: discord.Interaction, query: str):
    await interaction.response.defer()

    try:
        # Scrape wiki page for details
        wiki_data = await scrape_wiki_page(query)

        if not wiki_data:
            # Page not found, provide simple link
            wiki_link = create_wiki_link(query)
            url_match = re.search(r'\(([^)]+)\)', wiki_link)
            wiki_url = url_match.group(
                1) if url_match else f"http://aqwwiki.wikidot.com"

            embed = discord.Embed(
                title=f"❌ Page Not Found: {query}",
                description=
                f"Could not find a wiki page for '{query}'.\n\nTry searching manually: {wiki_link}",
                color=discord.Color.orange())
            await interaction.followup.send(embed=embed)
            return

        # Check if this is a disambiguation page with related items
        related_items = wiki_data.get('related_items', [])
        if related_items:
            # Create disambiguation embed
            title = wiki_data.get('title', query)
            url = wiki_data.get('url', '')

            embed = discord.Embed(title=f"📖 {title}",
                                  url=url,
                                  color=discord.Color.blue())

            description = wiki_data.get('description')
            if description:
                if len(description) > 200:
                    description = description[:197] + "..."
                embed.description = description

            # Show related items list in the embed
            related_list = []
            for item in related_items[:10]:
                related_list.append(f"• {item['name']}")

            embed.add_field(name="📋 Multiple items found:",
                            value='\n'.join(related_list),
                            inline=False)

            embed.set_footer(
                text="Use the dropdown menu below to view item details")

            view = WikiDisambiguationView(related_items)
            await interaction.followup.send(embed=embed, view=view)
            return

        # Fetch merge requirements if shop is present
        shop = wiki_data.get('shop')
        if shop:
            shop_name = shop.split(' - ')[0].strip() if ' - ' in shop else shop
            shop_data = await scrape_shop_items(shop_name)
            if shop_data and shop_data.get('items'):
                # Find this specific item in the shop to get merge requirements
                for item in shop_data['items']:
                    if wiki_data['title'] in item.get('name', ''):
                        wiki_data['merge_requirements'] = item.get('price')
                        break

        # Create embed
        embed = await create_wiki_embed(wiki_data)

        # Add interactive buttons for quest if present
        view = ItemDetailsView(wiki_data) if wiki_data.get('quest') else None

        if view:
            await interaction.followup.send(embed=embed, view=view)
        else:
            await interaction.followup.send(embed=embed)

    except Exception as e:
        print(f'Error fetching wiki data: {e}')
        import traceback
        traceback.print_exc()

        await interaction.followup.send(
            f'An error occurred while fetching wiki data: {str(e)}')


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        return
    bot.run(token)


if __name__ == "__main__":
    main()
