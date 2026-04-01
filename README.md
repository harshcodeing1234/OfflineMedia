# OfflineMedia

A Flask-based web application that scrapes short-form videos from Instagram, YouTube, and Facebook, then provides a TikTok-like interface for viewing and interacting with the content.

## Features

### Core Functionality
- **Multi-Platform Scraping**: Automated scraping from Instagram Reels, YouTube Shorts, and Facebook Reels
- **Video Management**: Download, cache, and organize videos with TTL-based expiration
- **Interactive Player**: TikTok-style video player with swipe navigation
- **Social Features**: Like videos, comment, and interact with content
- **User Authentication**: Secure login/registration system with session management

### Technical Features
- Concurrent video downloads with thread pool executor
- Selenium-based web scraping with anti-detection measures
- yt-dlp integration for reliable video downloads
- SQLite database with SQLAlchemy ORM
- Automatic cleanup of expired content
- Cookie-based authentication for Instagram scraping

## Project Structure

```
project/
├── app.py              # Flask application & API routes
├── agent.py            # Selenium scraping agents for each platform
├── scraper.py          # Video download & scraping orchestration
├── models.py           # Database models (User, Scrape, Video, Comment, Like)
├── database.py         # Database initialization & migrations
├── config.py           # Configuration settings
├── utils.py            # Utility functions for error handling
├── migrate_db.py       # Database migration script
├── requirements.txt    # Python dependencies
├── cookies.txt         # Instagram session cookies (auto-generated)
├── cache/              # Downloaded video storage
├── instance/           # SQLite database
└── templates/          # HTML templates
    ├── auth.html       # Login/registration page
    ├── dashboard.html  # Main dashboard
    ├── scrapp.html     # Scraping interface
    ├── play.html       # Video player
    └── polling.html    # Scraping status monitor
```

## Installation

### Prerequisites
- Python 3.8+
- Chrome browser
- ChromeDriver (compatible with your Chrome version)

### Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd project
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure settings in `config.py`:
```python
SERVER_URL = "http://127.0.0.1:5000"
CACHE_FOLDER = "cache"
THREAD_POOL_WORKERS = 10
```

4. Initialize the database:
```bash
python migrate_db.py
```

5. Run the application:
```bash
python app.py
```

The app will be available at `http://localhost:5000`

## Usage

### Web Interface

1. **Register/Login**: Create an account or login at `/auth`
2. **Start Scraping**: Navigate to `/scrapp` to configure and start a scraping session
   - Set duration (minutes to scrape)
   - Set TTL (hours before videos expire)
3. **Monitor Progress**: View scraping status at `/polling`
4. **Watch Videos**: Browse and watch scraped videos at `/play`
5. **Dashboard**: View statistics and manage scrapes at `/dashboard`

### Standalone Scraping

Run the agent directly for command-line scraping:

```bash
python agent.py
```

You'll be prompted for:
- Scraping duration (minutes)
- TTL (hours)

### API Endpoints

#### Authentication
- `POST /api/login` - User login
- `POST /api/register` - User registration
- `GET /logout` - Logout

#### Scraping
- `POST /api/scrape` - Start new scraping session
- `GET /api/scrapes` - List all scrapes
- `GET /api/scraping-status` - Check if scraping is active
- `POST /api/scrape/<id>/stop` - Stop scraping
- `DELETE /api/scrape/<id>/delete` - Delete scrape and videos

#### Videos
- `GET /api/videos` - List all videos
- `GET /cache/<filename>` - Stream video file
- `POST /api/video/<filename>/like` - Like/unlike video
- `POST /api/video/<filename>/comment` - Add comment
- `GET /api/video/<filename>/comments` - Get comments

#### User
- `GET /api/user` - Get current user info
- `POST /api/user/update` - Update user profile
- `GET /api/stats` - Get user statistics

## Database Schema

### User
- id, username, email, name, phone, avatar, password, created_at

### Scrape
- id, user_id, duration, ttl, status, progress, total_videos, downloaded_videos
- created_at, started_at, expires_at, logs

### Video
- id, scrape_id, platform, url, filename, status, likes
- created_at, expires_at

### Comment
- id, video_id, filename, user_id, text, created_at

### Like
- id, video_id, filename, user_id, created_at

## Configuration

### Scraping Settings
- `MAX_VIDEOS_PER_PLATFORM`: Maximum videos to scrape per platform (default: 100)
- `THREAD_POOL_WORKERS`: Concurrent download threads (default: 10)
- `PAGE_LOAD_TIMEOUT`: Selenium page load timeout (default: 45s)

### Download Settings
- `CACHE_FOLDER`: Video storage directory (default: "cache")
- `CLEANUP_INTERVAL_SECONDS`: Expired content cleanup interval (default: 300s)

## How It Works

### Scraping Process
1. User initiates scrape with duration and TTL
2. Agent launches Selenium browsers for each platform sequentially
3. Instagram: Scrolls explore page, collects reel links
4. YouTube: Navigates shorts, captures URLs
5. Facebook: Scrolls watch page, extracts video links
6. Links saved to database with status tracking

### Download Process
1. Videos queued for download via thread pool
2. yt-dlp downloads each video with retry logic
3. Files saved to cache with platform prefix
4. Database updated with filename and status
5. Progress tracked in real-time

### Expiration & Cleanup
1. Background thread runs every 5 minutes
2. Checks for expired videos based on TTL
3. Deletes files from cache
4. Removes database records
5. Cascades to associated comments and likes

## Security Features

- Password hashing with Werkzeug
- Flask-Login session management
- User ownership validation on all operations
- SQL injection protection via SQLAlchemy ORM
- CSRF protection on state-changing operations

## Performance Optimizations

- Connection pooling for database (pool_size: 20)
- Concurrent fragment downloads in yt-dlp
- Thread pool for parallel video downloads
- Lazy loading of relationships
- Indexed database queries on filename

## Troubleshooting

### Instagram Login Required
If Instagram scraping fails, run `agent.py` standalone first to login manually. Cookies will be saved for future use.

### ChromeDriver Issues
Ensure ChromeDriver version matches your Chrome browser version. Download from: https://chromedriver.chromium.org/

### Download Failures
- Check internet connection
- Verify yt-dlp is up to date: `pip install -U yt-dlp`
- Some videos may be geo-restricted or require authentication

### Database Errors
Run migrations to ensure schema is up to date:
```bash
python migrate_db.py
```

## Dependencies

- **Flask**: Web framework
- **Flask-Login**: User session management
- **Flask-SQLAlchemy**: Database ORM
- **Selenium**: Web scraping automation
- **yt-dlp**: Video downloading
- **Werkzeug**: Security utilities
- **Requests**: HTTP client

## License

This project is for educational purposes only. Respect platform terms of service and copyright laws when scraping content.

## Notes

- Videos are temporary and expire based on configured TTL
- Scraping requires active browser sessions (except YouTube/Facebook which run headless)
- Instagram requires login cookies for reliable scraping
- Download speed depends on network and platform rate limits
