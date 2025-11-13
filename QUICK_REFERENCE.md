# Quick Reference Card

## 🚀 Starting the Bot

```bash
# Activate virtual environment
source venv/bin/activate

# Run the bot (simple)
python bot.py
# OR use the supervisor (stops/starts scraper+bot+renderer)
./start_all.sh
```

## 📁 Core Files (8 files)

| File | Purpose | Status |
|------|---------|--------|
| `bot.py` | Main Discord bot | ✅ Working |
| `swf2png_client.py` | Native Flash renderer | ✅ Working (requires service) |
| `scraper.py` | CharPage scraper | ✅ Working |
| `wiki_scraper.py` | Wiki searches | ✅ Working |
| `shop_scraper.py` | Shop information | ✅ Working |
| `ocr_service.py` | Cosmetics OCR | ✅ Working |
| `get_guild_id.py` | Guild lookup utility | ✅ Working |

## 🎮 Discord Commands

| Command | Description | Who Can Use |
|---------|-------------|-------------|
| `/verify` | Character verification | Everyone |
| `/char <username>` | Character lookup with renders | Everyone |
| `/wiki <item>` | Wiki item search | Everyone |
| `/shop <shop>` | Shop information | Everyone |
| `/deployhelper` | Deployment menu | Admins only |

## 🖼️ Character Rendering

### Primary: swf2png Service
```bash
# Check if service is available
python -c "from swf2png_client import SWF2PNGClient; print('Available' if SWF2PNGClient().is_available() else 'Not running')"
```

**Setup:** See [SOLUTIONS.md](SOLUTIONS.md)
- Requires: Adobe AIR Runtime + swf2png application
- Port: 4567 (localhost)
- Quality: Best (native Flash)

> The Discord bot now reports renderer downtime instead of falling back to an emulated screenshot.

## 🔧 Common Tasks

### Check Bot Status
```bash
ps aux | grep "python.*bot.py" | grep -v grep
```

### Kill Bot
```bash
pkill -f "python.*bot.py"
```

### View Logs
```bash
tail -f bot.log
```

### Test Imports
```bash
python -c "import bot; print('✓ All imports OK')"
```

### Test swf2png Client
```bash
python swf2png_client.py Yenne
```

## 📊 File Statistics

- **Total Python Files:** 8
- **Lines of Code:** ~2,500
- **Commands:** 5
- **Removed Files:** 18 (obsolete renderers)
- **Reduction:** 69% fewer files

## 🐛 Troubleshooting

### Bot Won't Start
```bash
# Check for syntax errors
python -m py_compile bot.py

# Check imports
python -c "import bot"

# Check if another instance is running
ps aux | grep bot.py
```

### Character Rendering Fails
1. Check swf2png status: `SWF2PNGClient().is_available()`
2. Inspect `air_renderer.log` for AIR runtime issues
3. Review Discord embed field "Renderer Status" for the latest error

### Permission Errors
- Bot role must be **above** user roles
- Requires "Manage Nicknames" permission
- Cannot change server owner's nickname

## 📚 Documentation Files

| File | Purpose |
|------|---------|
| `README.md` | Main documentation |
| `SOLUTIONS.md` | Character rendering guide |
| `OPTIMIZATION_SUMMARY.md` | Cleanup details |
| `QUICK_REFERENCE.md` | This file |

## 🔒 Security Checklist

- ✅ `.env` file protected by `.gitignore`
- ✅ Bot token never committed
- ✅ Only environment variables for secrets
- ✅ No hardcoded credentials

## 🌐 Deployment Options

| Platform | Cost | Uptime | Setup |
|----------|------|--------|-------|
| Render.com | Free | 750h/month | Easy |
| Railway.app | $5/month | ~20 days | Easy |
| Fly.io | Free | 3 VMs | Medium |
| VPS | $5+/month | 24/7 | Complex |

## 📦 Dependencies

```txt
discord.py==2.6.4    # Discord API
playwright==1.48.0   # Browser automation
httpx==0.27.2        # Async HTTP
beautifulsoup4==4.14.2  # HTML parsing
pytesseract==0.3.13  # OCR
Pillow==11.0.0       # Image processing
```

## 🎯 Project Goals Achieved

- ✅ Character verification system
- ✅ Dual-view character rendering
- ✅ Intelligent fallback system
- ✅ Wiki integration
- ✅ Shop information
- ✅ Clean, maintainable codebase
- ✅ 69% file reduction
- ✅ Comprehensive documentation

## 💡 Tips

1. **Always use swf2png when available** - Best quality
2. **Monitor logs** - Track which renderer is being used
3. **Keep venv activated** - Avoid missing dependencies
4. **Check bot role position** - Above users for nickname changes
5. **Use `/char` extensively** - Shows both cosmetics and equipped

## 🔄 Update Process

```bash
# Pull latest changes
git pull

# Update dependencies
pip install -r requirements.txt --upgrade

# Restart bot
pkill -f "python.*bot.py"
./run.sh
```

---

**Last Updated:** November 11, 2025
**Version:** Optimized (8 core files)
**Status:** Production Ready ✅
