"""Scraper module - handles all scraping logic"""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from yt_dlp import YoutubeDL #type:ignore
import os
import time


def safe_commit(db):
    for _ in range(5):
        try: 
            db.session.commit()  
            return True
        except Exception:
            db.session.rollback()
            time.sleep(0.5)
    print("DB commit failed")
    return False

def log_to_scrape(scrape, message, db):
    """Add log message to scrape"""
    timestamp = datetime.utcnow().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {message}\n"
    try:
        scrape.logs = (scrape.logs or '') + log_line
        safe_commit(db)
    except:
        db.session.rollback()
    print(message)

def run_scraper_session(scrape_id, duration, ttl, platforms, db, Video, Scrape, executor, download_video_func, CACHE_FOLDER):
    """Run scraper in background with proper error handling"""
    try:
        from agent import scrape_instagram, scrape_youtube, scrape_facebook
        
        scrape = Scrape.query.get(scrape_id)
        if not scrape:
            print(f"Scrape {scrape_id} not found")
            return
        
        scrape.status = 'scraping'
        scrape.started_at = datetime.utcnow()
        scrape.expires_at = datetime.utcnow() + timedelta(hours=ttl)
        safe_commit(db)
        log_to_scrape(scrape, f"Scrape {scrape_id} started with platforms: {platforms}", db)
        
        # Parse platforms
        platform_map = {
            'instagram': scrape_instagram,
            'youtube': scrape_youtube,
            'facebook': scrape_facebook
        }
        
        selected_platforms = []
        if platforms == 'all':
            selected_platforms = ['instagram', 'youtube', 'facebook']
        else:
            # Parse "instagram & youtube" format
            selected_platforms = [p.strip() for p in platforms.split('&')]
        
        # SEQUENTIAL EXECUTION - divide time equally
        time_per_platform = duration / len(selected_platforms)
        results = {}
        
        for platform in selected_platforms:
            if platform not in platform_map:
                continue
                
            # Check if stopped
            scrape = Scrape.query.get(scrape_id)
            if scrape.status == 'stopped':
                log_to_scrape(scrape, f"Scrape {scrape_id} stopped by user", db)
                return
            
            try:
                log_to_scrape(scrape, f"Starting {platform.title()} scraping ({time_per_platform:.1f} min)...", db)
                results[platform] = platform_map[platform](time_per_platform)
                log_to_scrape(scrape, f"{platform.title()}: {len(results[platform])} total", db)
            except Exception as e:
                log_to_scrape(scrape, f"{platform.title()} failed: {e}", db)
                results[platform] = []
        
        # Check if stopped
        scrape = Scrape.query.get(scrape_id)
        if scrape.status == 'stopped':
            log_to_scrape(scrape, f"Scrape {scrape_id} stopped by user", db)
            return
        
        # Save videos to database
        total = sum(len(links) for links in results.values())
        scrape.total_videos = total
        scrape.status = 'downloading'
        safe_commit(db)
        
        log_to_scrape(scrape, f"Total videos scraped: {total}", db)
        log_to_scrape(scrape, f"Starting downloads...", db)
        for platform, links in results.items():
            print(f"{platform.title()}: {len(links)}")
        
        # Save each video to database and trigger download
        for platform, links in results.items():
            for link in links:
                scrape = Scrape.query.get(scrape_id)
                if scrape.status == 'stopped':
                    print(f"Scrape {scrape_id} stopped during video save")
                    return
                
                try:
                    video = Video(
                        scrape_id=scrape_id,
                        platform=platform,
                        url=link,
                        status='downloading',
                        expires_at=datetime.utcnow() + timedelta(hours=ttl)
                    )
                    db.session.add(video)
                    safe_commit(db)
                    
                    # Download in background
                    executor.submit(download_video_func, video.id, link, scrape_id)
                except Exception as e:
                    log_to_scrape(scrape, f"Failed to save video {link}: {e}", db)
                    continue
        
        log_to_scrape(scrape, f"All downloads queued. Waiting for completion...", db)
    
    except Exception as e:
        print(f"Scraper failed with error: {e}")
        scrape = Scrape.query.get(scrape_id)
        if scrape:
            scrape.status = 'failed'
            safe_commit(db)
            log_to_scrape(scrape, f"Scraper failed: {e}", db)


def download_video_task(video_id, url, scrape_id, app, db, Video, Scrape, CACHE_FOLDER):
    """Download video with TTL enforcement"""
    with app.app_context():
        video = Video.query.get(video_id)
        scrape = Scrape.query.get(scrape_id)
        
        if not video or not scrape or scrape.status == 'stopped':
            return
        
        # Check TTL before downloading
        if scrape.started_at:
            expires_at = scrape.started_at + timedelta(hours=scrape.ttl)
            if datetime.utcnow() >= expires_at:
                video.status = 'expired'
                safe_commit(db)
                return
            
        filename = f"{video.platform}_{video_id}.mp4"
        path = os.path.join(CACHE_FOLDER, filename)
        
        # Check if already exists
        if os.path.exists(path):
            video.filename = filename
            video.status = 'ready'
            scrape.downloaded_videos += 1
            if scrape.total_videos > 0:
                scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
            safe_commit(db)
            log_to_scrape(scrape, f"✓ Already exists: {filename}", db)
            check_and_complete_scrape(scrape_id, db, Scrape)
            return
        
        try:
            log_to_scrape(scrape, f"⬇ Downloading: {video.platform} video {video_id}...", db)
            
            ydl_opts = {
                'outtmpl': path,
                'quiet': True,
                'no_warnings': True,
                'ignoreerrors': True,
                'skip_unavailable_fragments': True,
                'concurrent_fragment_downloads': 3,
                'http_chunk_size': 10485760,
                'retries': 5,
                'fragment_retries': 5,
                'socket_timeout': 30,
                'extractor_retries': 3,
                'file_access_retries': 3,
            }
            
            # Add cookies only if file exists (for Instagram)
            if os.path.exists('cookies.txt'):
                ydl_opts['cookiefile'] = 'cookies.txt'
            
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    info = ydl.extract_info(url, download=True)
                    if not info:
                        raise Exception("No video info extracted")
                except Exception as e:
                    print(f"Download failed for {url}: {e}")
                    video.status = 'failed'
                    safe_commit(db)
                    log_to_scrape(scrape, f"✗ Failed: {filename} - {str(e)[:50]}", db)
                    check_and_complete_scrape(scrape_id, db, Scrape)
                    return
            
            # Check for actual downloaded file (yt-dlp may change extension)
            actual_files = [f for f in os.listdir(CACHE_FOLDER) if f.startswith(f"{video.platform}_{video_id}")]
            if actual_files:
                video.filename = actual_files[0]
                video.status = 'ready'
                scrape.downloaded_videos += 1
                if scrape.total_videos > 0:
                    scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                print(f"✓ Downloaded: {video.filename}")
                log_to_scrape(scrape, f"✓ Downloaded: {video.filename} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
            else:
                video.status = 'failed'
                print(f"✗ Failed: {url}")
                log_to_scrape(scrape, f"✗ Failed: {filename}", db)
            
            safe_commit(db)
            
            # Check if all downloads complete
            check_and_complete_scrape(scrape_id, db, Scrape)
            
            # Add small delay between downloads
            import random
            time.sleep(random.uniform(0.5, 1))
            
            # Clean up .txt files
            for f in os.listdir(CACHE_FOLDER):
                if f.endswith('.txt'):
                    try:
                        os.remove(os.path.join(CACHE_FOLDER, f))
                    except:
                        pass
                        
        except Exception as e:
            video.status = 'failed'
            safe_commit(db)
            log_to_scrape(scrape, f"✗ Error: {filename} - {str(e)[:50]}", db)
            check_and_complete_scrape(scrape_id, db, Scrape)


def check_and_complete_scrape(scrape_id, db, Scrape):
    """Check if all videos are processed and mark scrape as completed"""
    from models import Video
    scrape = Scrape.query.get(scrape_id)
    if not scrape or scrape.status == 'stopped':
        return
    
    # Count videos that are still downloading
    downloading = Video.query.filter_by(scrape_id=scrape_id, status='downloading').count()
    
    if downloading == 0:
        scrape.status = 'completed'
        safe_commit(db)
        log_to_scrape(scrape, f"All downloads completed! ({scrape.downloaded_videos}/{scrape.total_videos} successful)", db)


def cleanup_expired_videos(app, db, Video, CACHE_FOLDER):
    """Cleanup expired videos and scrapes periodically"""
    time.sleep(5)  # Wait for app to initialize
    while True:
        try:
            with app.app_context():
                from models import Scrape
                now = datetime.utcnow()
                
                # Delete expired videos
                expired_videos = Video.query.filter(Video.expires_at < now).all()
                for video in expired_videos:
                    if video.filename:
                        filepath = os.path.join(CACHE_FOLDER, video.filename)
                        try:
                            if os.path.exists(filepath):
                                os.remove(filepath)
                                print(f"Deleted expired video: {video.filename}")
                        except Exception as e:
                            print(f"Failed to delete expired video {filepath}: {e}")
                    db.session.delete(video)
                
                # Delete expired scrapes and their videos
                expired_scrapes = Scrape.query.filter(Scrape.expires_at < now).all()
                for scrape in expired_scrapes:
                    for video in scrape.videos:
                        if video.filename:
                            filepath = os.path.join(CACHE_FOLDER, video.filename)
                            try:
                                if os.path.exists(filepath):
                                    os.remove(filepath)
                                    print(f"Deleted video from expired scrape: {video.filename}")
                            except Exception as e:
                                print(f"Failed to delete video {filepath}: {e}")
                    db.session.delete(scrape)
                    print(f"Deleted expired scrape: {scrape.id}")
                
                if expired_videos or expired_scrapes:
                    safe_commit(db)
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(300)

def save_cookies(driver, path="cookies.txt"):
    cookies = driver.get_cookies()

    with open(path, "w", encoding="utf-8") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write("# This file is generated by Selenium\n\n")

        for c in cookies:
            domain = c.get("domain", "")
            flag = "TRUE" if domain.startswith(".") else "FALSE"
            path_c = c.get("path", "/")
            secure = "TRUE" if c.get("secure") else "FALSE"
            expiry = int(c.get("expiry", 0))
            name = c.get("name")
            value = c.get("value")

            f.write(f"{domain}\t{flag}\t{path_c}\t{secure}\t{expiry}\t{name}\t{value}\n")
