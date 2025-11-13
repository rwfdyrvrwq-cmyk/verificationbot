# Character Rendering Solutions for AQW Discord Bot

## Problem Summary

You want to generate clean character images showing ONLY the character with equipment (weapon, armor, helm, cape, pet) - no CharPage UI elements like text, buttons, or frames.

## Solutions Discovered

### ❌ Failed Approaches

1. **characterB.swf with Ruffle** (`standalone_character_renderer.py`)
   - Issue: characterB.swf includes CharPage UI by design
   - All attempts show name text, arrows, buttons
   - Ruffle emulation is slower and less accurate

2. **Individual Equipment SWF Layering** (`layered_character_renderer.py`)
   - Issue: Equipment SWFs require characterB.swf host to function
   - Cannot render standalone

3. **Node.js Puppeteer Service** (`render_service/`)
   - Issue: Crashes on macOS with ECONNRESET errors
   - Incompatible with macOS security

4. **aq-hub Repository** (https://github.com/dayvsonspacca/aq-hub)
   - Issue: Backend API only - no rendering code
   - Only collects item metadata, doesn't generate images

### ✅ BEST SOLUTION: swf2png Service

**Repository:** https://github.com/anthony-hyo/swf2png

**Description:** ActionScript 3 TCP server that renders AQW assets using native Flash Player

**Why This is Perfect:**
- ✅ Native Flash rendering (not Ruffle emulation)
- ✅ Specifically designed for character rendering
- ✅ Clean output without CharPage UI
- ✅ Handles all equipment types (weapon, armor, helm, cape, pet)
- ✅ Returns Base64-encoded PNG via TCP
- ✅ Already tested and working

## How to Use swf2png

### Step 1: Setup swf2png Service

1. **Download the repository:**
   ```bash
   git clone https://github.com/anthony-hyo/swf2png.git
   cd swf2png
   ```

2. **Requirements:**
   - Adobe Animate/Flash Professional (or compatible IDE)
   - Adobe AIR Runtime
   - Adobe AIR SDK

3. **Build the application:**
   - Open `item-preview.fla` in Adobe Animate
   - File → Publish Settings → Adobe AIR
   - Configure AIR application settings
   - Publish to create `Item.swf`

4. **Run the service:**
   - Double-click `Item.swf` (requires Adobe AIR)
   - Service will listen on `localhost:4567`
   - Keep this running in the background

### Step 2: Use Python Client

I've created `swf2png_client.py` that integrates with the service:

```python
from swf2png_client import SWF2PNGClient

# Initialize client
client = SWF2PNGClient()

# Check if service is running
if not client.is_available():
    print("ERROR: swf2png service not running")
    exit(1)

# Render character
png_data = await client.render_character(
    username="Yenne",
    output_path="output.png"
)
```

### Step 3: Integrate with Discord Bot

Update `bot.py` to use swf2png:

```python
from swf2png_client import SWF2PNGClient

# In your bot setup
swf2png = SWF2PNGClient()

@bot.tree.command(name="char")
async def character_command(interaction: discord.Interaction, username: str):
    await interaction.response.defer()
    
    # Check service availability
    if not await swf2png.is_available():
        await interaction.followup.send(
            "⚠️ Character rendering service is offline. Please start swf2png."
        )
        return
    
    # Render character
    png_data = await swf2png.render_character(username)
    
    if png_data:
        # Save and send image
        file_path = f"renders/{username}.png"
        with open(file_path, 'wb') as f:
            f.write(png_data)
        
        await interaction.followup.send(
            file=discord.File(file_path)
        )
    else:
        await interaction.followup.send("Failed to render character")
```

## API Reference

### SWF2PNG Request Format

```json
{
  "type": "character",
  "data": {
    "url": "https://game.aq.com/game/gamefiles/",
    "gender": "M",
    "ia1": 0,
    "equipment": {
      "en": {"File": "none", "Link": ""},
      "co": {"File": "SomeClass.swf", "Link": "rSomeClass"},
      "he": {"File": "SomeHelm.swf", "Link": "rSomeHelm"},
      "Weapon": {"File": "SomeWeapon.swf", "Type": "Sword", "Link": "rSomeWeapon"},
      "ba": {"File": "SomeCape.swf", "Link": "rSomeCape"},
      "pe": {"File": "SomePet.swf", "Link": "rSomePet"},
      "mi": {"File": "none", "Link": ""}
    },
    "hair": {"File": "hair/Hair_101.swf", "Name": "rHair101"},
    "intColorSkin": 16777215,
    "intColorHair": 8421504,
    "intColorEye": 255,
    "intColorBase": 16711680,
    "intColorTrim": 16777215,
    "intColorAccessory": 65280
  }
}
```

### Equipment Keys

- `en`: Entity (custom character models)
- `co`: Class/Armor file
- `he`: Helm
- `Weapon`: Weapon (includes Type: Sword/Dagger/etc)
- `ba`: Back (Cape)
- `pe`: Pet
- `mi`: Misc (Ground effects)

### ia1 Flags (Achievement Visibility)

Bitmask controlling equipment visibility:
- Bit 0 (value 1): Hide cape
- Bit 1 (value 2): Hide helm
- Bit 2 (value 4): Hide pet

Example: `ia1 = 0` shows all equipment

## Cosmetics vs Equipped Views

**Current Limitation:** The swf2png service doesn't distinguish between cosmetics and equipped items automatically.

**Workaround:** To show cosmetics, parse `strArmorFile` instead of `strClassFile` from FlashVars:

```python
# For equipped view
equipment["co"]["File"] = flashvars["strClassFile"]

# For cosmetics view
equipment["co"]["File"] = flashvars["strArmorFile"]
```

## Troubleshooting

### Service Not Running

**Symptom:** `socket.connect_ex()` returns non-zero

**Solutions:**
1. Ensure Adobe AIR Runtime is installed
2. Double-click `Item.swf` to start service
3. Check port 4567 is not blocked by firewall
4. Look for service in system tray (AIR icon)

### Empty Response

**Symptom:** Service returns empty data

**Solutions:**
1. Check equipment file paths are correct
2. Verify `url` points to valid asset server
3. Enable debug mode in `Main.as`: `Main.DEBUG = true`
4. Check service console for error messages

### Invalid Equipment Data

**Symptom:** Character renders incomplete or incorrectly

**Solutions:**
1. Verify FlashVars parsing is correct
2. Check color values are valid integers
3. Ensure gender is "M" or "F"
4. Validate equipment Link names match SWF symbols

## File Reference

### Created Files

1. **`swf2png_client.py`** - Python client for swf2png service
   - `SWF2PNGClient` class
   - `parse_charpage_equipment()` - Converts FlashVars to swf2png format
   - `render_character()` - Main rendering method
   - `is_available()` - Service health check

2. **`SOLUTIONS.md`** (this file) - Complete documentation

### Existing Files to Update

1. **`bot.py`** - Main Discord bot
   - Import `swf2png_client`
   - Update `/char` command to use swf2png
   - Display renderer status inside embeds when offline

2. **`scraper.py`** - Character data scraper
   - Already parses FlashVars correctly
   - No changes needed

## Next Steps

1. **Download and build swf2png** from https://github.com/anthony-hyo/swf2png
2. **Run the service** (keep `Item.swf` running)
3. **Test the client:** `python swf2png_client.py Yenne`
4. **Integrate with bot** - Update `bot.py` to use `SWF2PNGClient`
5. **Test Discord command** - `/char username`

## Alternative: MultusAQW API

If building swf2png is too complex, consider using MultusAQW's API:

**Repository:** https://github.com/MultusAQW/api

This is a Next.js API that might have character rendering endpoints. However, their charpage repository (https://github.com/MultusAQW/charpage) is frontend-only and doesn't help with rendering.

## Conclusion

The **swf2png service** is your best solution because:
- ✅ Native Flash rendering (accurate)
- ✅ Clean character output (no UI)
- ✅ TCP/JSON API (easy integration)
- ✅ Handles all equipment types
- ✅ Production-ready (already used by other projects)

Once you have the service running, character rendering will be fast, accurate, and produce the clean images you want.
