# AQW Discord Verification Bot

A comprehensive Discord bot for AdventureQuest Worlds (AQW) that provides character verification, detailed character lookups with equipment rendering, wiki searches, and shop information.

## Features

### `/verify` - Character Verification
- Verifies character ownership by comparing user input with CharPage data
- User provides IGN (In-Game Name) and optional Guild
- Creates admin-only verification channel with results
- Automatically updates Discord nickname to IGN on approval
- Handles permission errors gracefully

### `/char` - Character Lookup
- Generates a clean, Flash-accurate render using the native swf2png service
- Sends the render immediately after the character embed so the image is always displayed below the stats
- Shows comprehensive character information:
  - Level, class, faction, guild
  - All equipped items (weapon, armor, helm, cape, pet, misc)
  - All cosmetic items with wiki links
- Renders are saved to `renders/` (auto-created and gitignored)
- Gracefully reports renderer downtime inside the embed if swf2png is offline (see [SOLUTIONS.md](SOLUTIONS.md))

### `/wiki` - Item Search
- Searches AQW Wiki (aqwwiki.wikidot.com)
- Shows detailed item information with images
- Direct wiki links for more details

### `/shop` - Shop Information
- Looks up shop locations and contents
- Shows available items and acquisition methods

### `/deployhelper` - Deployment Assistant (Admin Only)
- Quick-access dropdown menu for common deployments:
  - Daily 4 Man, Daily 7 Man, Temple Run
  - Weekly Ultras, Ultraspeaker, Grimchallenge
- All interactions are ephemeral (private)

## Technical Architecture

### Character Rendering Pipeline
- **swf2png Service** (Native Flash)
  - ActionScript 3 TCP server on localhost:4567
  - Produces cleaned PNG/GIF renders with no CharPage UI
  - See [SOLUTIONS.md](SOLUTIONS.md) for setup instructions
  - Bot notifies the user if the renderer is unreachable instead of silently failing

### Standalone Character Renderer
Need a quick render without running the bot? Use the bundled client for the swf2png
service:

```bash
# Ensure the swf2png Item.swf service is running (see SOLUTIONS.md)
python swf2png_client.py Yenne -o renders/yen.png

# Cosmetic view or GIF output
python swf2png_client.py Yenne --cosmetics --format gif -o renders/yen_cos.gif
```

The client automatically pulls FlashVars from the official CharPage, removes every
UI element/background via the swf2png renderer, and saves a clean PNG (or GIF) of
the character only. All artifacts are written to the `renders/` directory, which
is recreated on demand and ignored by git.

### Data Scraping
- **scraper.py**: Async CharPage parser (49 FlashVars parameters)
- **wiki_scraper.py**: AQW Wiki data extraction
- **shop_scraper.py**: Shop information lookup
- **ocr_service.py**: OCR for cosmetics item extraction

### Bot Features
- Async HTTP with connection pooling
- Ephemeral responses to prevent spam
- Admin-only verification channels
- Automatic nickname management
- Comprehensive error handling

## Quick Start

### 1. Create a virtual environment (recommended)

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Set up Discord Bot

1. Create a bot application on the [Discord Developer Portal](https://discord.com/developers/applications)
2. Enable these bot permissions:
   - **Manage Nicknames** (required for nickname changes)
   - **Manage Channels** (required for creating verification channels)
   - **Send Messages**
   - **Use Slash Commands**
3. Copy your bot token

### 4. Configure environment variables

Create a `.env` file:

```bash
cp .env.example .env
```

Edit `.env` and add your token:

```bash
DISCORD_TOKEN="your_bot_token_here"
# Optional: for faster testing, register commands to a single guild
# GUILD_ID=123456789012345678
```

### 5. Run the bot

```bash
python bot.py
```

Or use the process manager helper:

```bash
chmod +x start_all.sh
./start_all.sh
```

`start_all.sh` stops any lingering processes, launches the scraper, bot, and
swf2png AIR app (if installed). You can override paths without editing the file:

```bash
SWF2PNG_DIR="$HOME/dev/swf2png" LOG_DIR="$HOME/verificationbot/logs" ./start_all.sh
```

## Usage

### Verifying a Character

1. User runs `/verify`
2. Clicks "Start Verification" button
3. Enters their IGN and Guild in the modal
4. Bot compares against CharPage data
5. If successful, admin channel is created
6. Admin (or user) clicks "Finish Verification"
7. User's nickname changes to their IGN
8. Verification channel is deleted

### Deployment Helper (Admin Only)

1. Admin runs `/deployhelper`
2. Empty embed appears with "Help?" button
3. Members can click "Help?" to see deployment options
4. Select an option from the dropdown menu

## Deployment

### Free Hosting Options

**Recommended: [Render.com](https://render.com)**
- Free tier with 750 hours/month
- Easy GitHub integration
- Auto-restarts on crashes
- Sleeps after 15 minutes of inactivity (wakes instantly on command)

**Other Options:**
- **Railway.app**: $5 free credit monthly (~20 days uptime)
- **Fly.io**: Free tier with 3 shared VMs, always-on
- **PythonAnywhere**: Always-on free tier for Python bots

### Deploy to Render

1. Push your code to GitHub
2. Sign up at [render.com](https://render.com)
3. Create new "Web Service"
4. Connect your GitHub repository
5. Configure:
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
6. Add environment variable:
   - **Key**: `DISCORD_TOKEN`
   - **Value**: Your bot token
7. Deploy!

## Project Structure

```
verificationbot/
├── bot.py                   # Main bot with all commands
├── scraper.py              # CharPage data scraper
├── swf2png_client.py       # Native Flash renderer client (REQUIRED)
├── wiki_scraper.py         # Wiki search functionality
├── shop_scraper.py         # Shop information lookup
├── ocr_service.py          # OCR for item extraction
├── get_guild_id.py         # Guild lookup utility
├── requirements.txt        # Python dependencies
├── start_all.sh            # Process supervisor for scraper + bot + renderer
├── .env                    # Environment variables (not committed)
├── .env.example            # Template for .env
├── QUICK_REFERENCE.md      # Triage / ops runbook
├── SOLUTIONS.md            # Character rendering guide
├── renders/                # Runtime render output (auto-created)
└── README.md               # This file
```

## Requirements

- Python 3.9+
- discord.py 2.6.4+
- httpx 0.27.2+ (async HTTP client)
- aiohttp 3.10.11+ (HTTP sessions)
- beautifulsoup4 4.14.2+ (HTML parsing)
- python-dotenv 1.2.1+
- Pillow 11.0.0+ (image processing)
- opencv-python 4.10.0+ (OCR preprocessing)
- numpy 1.26.4+ (image math)
- pytesseract 0.3.13+ (OCR)

### Optional: swf2png Service
For best character rendering quality, set up the swf2png service:
- See [SOLUTIONS.md](SOLUTIONS.md) for detailed instructions
- Requires Adobe AIR Runtime and Adobe Animate/Flash Professional
- Provides native Flash rendering (vs Ruffle emulation)

## Security Notes

- ✅ `.env` file is protected by `.gitignore`
- ✅ Bot token is never committed to the repository
- ✅ Only environment variables are used for sensitive data
- ⚠️ Ensure your bot role is positioned correctly in Discord server for nickname changes
- ⚠️ Keep your bot token secret - regenerate if exposed

## Troubleshooting

### "Application did not respond"
- Bot may not be running or has crashed
- Check logs for errors
- Restart the bot

### Nickname change fails
1. Check bot has "Manage Nicknames" permission
2. Ensure bot's role is **above** the user's highest role in server settings
3. Bot cannot change server owner's nickname

### Commands not showing
- Commands sync automatically on bot startup
- Wait 1-2 minutes for Discord to update
- Try restarting the bot

## Health Checks

- **Syntax validation**: `PYTHONPYCACHEPREFIX=/tmp/pycache python3 -m compileall bot.py scraper.py char_data_scraper.py ...`
  (use `/tmp/pycache` so no cache files are written into the repo).
- **Process status**: Inspect `/tmp/*.pid` files written by `start_all.sh` and `tail -f bot.log` / `scraper.log`.
- **Renderer availability**: `python -c "import asyncio; from swf2png_client import SWF2PNGClient; print(asyncio.run(SWF2PNGClient().is_available()))"`
- **Cleanup**: The `.gitignore` excludes logs, PID files, renders, and HTML/PNG snapshots so the working tree stays clean after tests.

## Future Enhancements

Potential features to add:
- Automatic role assignment on verification
- Persistent storage of verified users
- Verification logs and analytics
- Custom deployment helper content per option
- Re-verification system
- Verification expiry

## License

This project is provided as-is for AdventureQuest Worlds community use.

## Contact

For issues, suggestions, or contributions, please open an issue on GitHub.
