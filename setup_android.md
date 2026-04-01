# Android Setup Guide (Termux + Termux:X11)

Complete setup guide for running the video scraping platform on Android using Termux.

---

## Prerequisites

1. **Install from F-Droid** (NOT Google Play):
   - [Termux](https://f-droid.org/en/packages/com.termux/)
   - [Termux:X11](https://github.com/termux/termux-x11/releases) - Download latest APK

2. **Device Requirements**:
   - Android 7.0+
   - 4GB+ RAM recommended
   - 2GB+ free storage

---

## Step 1: Initial Termux Setup

```bash
# Update packages
pkg update && pkg upgrade -y

# Install essential packages
pkg install -y python git wget curl

# Install storage access
termux-setup-storage
# (Grant storage permission when prompted)
```

---

## Step 2: Install Chromium & ChromeDriver

```bash
# Install Chromium browser
pkg install -y chromium

# Install ChromeDriver (matching version)
pkg install -y chromedriver

# Verify installation
which chromium-browser
which chromedriver
```

**Expected paths**:
- Browser: `/data/data/com.termux/files/usr/bin/chromium-browser`
- Driver: `/data/data/com.termux/files/usr/bin/chromedriver`

---

## Step 3: Setup Termux:X11 (For Instagram Login)

Instagram scraping requires visible browser for login.

### Install X11 Dependencies

```bash
# Install X11 server components
pkg install -y x11-repo
pkg install -y termux-x11-nightly

# Install window manager (optional but recommended)
pkg install -y openbox
```

### Start X11 Server

**Terminal 1** (Start X11):
```bash
termux-x11 :0 &
```

**Terminal 2** (Set display):
```bash
export DISPLAY=:0
```

### Open Termux:X11 App
- Launch the **Termux:X11** app from your Android launcher
- Keep it running in background

---

## Step 4: Install Python Dependencies

```bash
# Navigate to project directory
cd ~/storage/shared/Amity/project
# OR clone from git:
# git clone <your-repo-url>
# cd project

# Install Python packages
pip install -r requirements.txt
```

**requirements.txt** should contain:
```
flask
flask-login
flask-sqlalchemy
requests
selenium
yt-dlp
werkzeug
```

---

## Step 5: Project Configuration

### Verify Config

Check `config.py`:
```python
SERVER_URL = "http://127.0.0.1:5000"
SERVER_PORT = 5000
MAX_VIDEOS_PER_PLATFORM = 100
CACHE_FOLDER = "cache"
THREAD_POOL_WORKERS = 10
CLEANUP_INTERVAL_SECONDS = 300
```

### Create Required Directories

```bash
mkdir -p cache instance templates
```

---

## Step 6: First-Time Instagram Login

Instagram requires authenticated session for scraping.

### Run Agent Standalone (One-Time Setup)

```bash
# Make sure X11 is running and DISPLAY is set
export DISPLAY=:0

# Run agent for Instagram login
python agent.py
```

**When prompted**:
1. Enter scraping time: `1` (1 minute for test)
2. Enter TTL: `24` (24 hours)

**Browser will open**:
- Instagram login page will appear in Termux:X11 app
- **Manually login** to your Instagram account
- Wait for "Cookies saved" message
- Browser will continue scraping automatically

**Result**: `cookies.txt` file created for future runs

---

## Step 7: Run the Application

### Start Flask Server

```bash
python app.py
```

**Output**:
```
* Running on http://0.0.0.0:5000
```

### Access Web Interface

**Option 1 - On Device**:
- Open browser: `http://localhost:5000`

**Option 2 - From PC (Same Network)**:
```bash
# Find your Android IP
ifconfig wlan0
# Access from PC: http://192.168.x.x:5000
```

---

## Step 8: Usage

### Web Interface

1. **Register/Login**: Create account at `/auth`
2. **Start Scraping**: Go to `/scrapp`
   - Set duration (minutes)
   - Set TTL (hours)
   - Select platforms
   - Click "Start Scraping"
3. **Watch Videos**: Go to `/play`
4. **View Stats**: Dashboard at `/dashboard`

### Standalone Scraping (CLI)

```bash
# For subsequent runs (no X11 needed after first login)
python agent.py
```

---

## Troubleshooting

### Chrome Won't Start

```bash
# Check paths
ls -la /data/data/com.termux/files/usr/bin/chromium-browser
ls -la /data/data/com.termux/files/usr/bin/chromedriver

# Reinstall if missing
pkg reinstall chromium chromedriver
```

### X11 Display Error

```bash
# Restart X11 server
pkill -f termux-x11
termux-x11 :0 &

# Set display in current terminal
export DISPLAY=:0

# Test with simple app
pkg install -y xterm
xterm &  # Should open window in Termux:X11 app
```

### Instagram Login Fails

```bash
# Delete old cookies
rm cookies.txt

# Run agent again with X11
export DISPLAY=:0
python agent.py
# Login manually when browser opens
```

### Out of Memory

```bash
# Reduce workers in config.py
THREAD_POOL_WORKERS = 5
MAX_VIDEOS_PER_PLATFORM = 50
```

### Permission Denied

```bash
# Fix permissions
chmod +x agent.py app.py
chmod -R 755 cache/
```

---

## Running in Background

### Using tmux

```bash
# Install tmux
pkg install -y tmux

# Start session
tmux new -s scraper

# Run app
python app.py

# Detach: Ctrl+B then D
# Reattach: tmux attach -t scraper
```

### Using nohup

```bash
nohup python app.py > app.log 2>&1 &

# Check logs
tail -f app.log

# Stop
pkill -f app.py
```

---

## Performance Tips

1. **Reduce concurrent downloads**:
   ```python
   # config.py
   THREAD_POOL_WORKERS = 5
   ```

2. **Limit video count**:
   ```python
   MAX_VIDEOS_PER_PLATFORM = 30
   ```

3. **Clear cache regularly**:
   ```bash
   rm -rf cache/*.mp4
   ```

4. **Close unused apps** to free RAM

5. **Use headless mode** (after Instagram login):
   - Agent automatically uses headless for YouTube/Facebook
   - Only Instagram needs visible browser for first login

---

## File Structure

```
project/
├── app.py              # Flask server
├── agent.py            # Selenium scraper
├── scraper.py          # Download manager
├── models.py           # Database models
├── database.py         # DB initialization
├── config.py           # Configuration
├── utils.py            # Utilities
├── requirements.txt    # Dependencies
├── cookies.txt         # Instagram session (auto-generated)
├── cache/              # Downloaded videos
├── instance/           # SQLite database
│   └── app.db
└── templates/          # HTML templates
    ├── auth.html
    ├── dashboard.html
    ├── scrapp.html
    ├── play.html
    └── polling.html
```

---

## Security Notes

1. **Change secret key** in production:
   ```bash
   export SECRET_KEY="your-random-secret-key"
   ```

2. **Don't expose to internet** without authentication

3. **Cookies.txt contains sensitive data** - keep private

4. **Use strong passwords** for user accounts

---

## Uninstall

```bash
# Stop running processes
pkill -f app.py
pkill -f agent.py

# Remove project
cd ~
rm -rf project/

# Remove packages (optional)
pkg uninstall chromium chromedriver python
```

---

## Support

- Check logs: `tail -f app.log`
- Database issues: Delete `instance/app.db` and restart
- Browser issues: Clear `~/.config/chromium/` and re-login
- Cookies expired: Delete `cookies.txt` and run agent again

---

**Ready to scrape!** 🚀
