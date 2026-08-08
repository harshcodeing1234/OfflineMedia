"""Scraper module - handles all scraping logic"""
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor
from yt_dlp import YoutubeDL #type:ignore
import os
import time
import threading

cookie_lock = threading.Lock()


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

def run_scraper_session(scrape_id, duration, ttl, platforms, hashtags, quantity, db, Video, Scrape, executor, download_video_func, CACHE_FOLDER):
    """Run scraper in background with proper error handling"""
    try:
        from backend.agent import scrape_instagram, scrape_youtube, scrape_facebook
        from backend.models import WatchHistory
        
        scrape = Scrape.query.get(scrape_id)
        if not scrape:
            print(f"Scrape {scrape_id} not found")
            return
        
        # Clean up any leftover stop flag from previous scrapes
        stop_flag = f"stop_{scrape_id}.flag"
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
            print(f"Cleaned up leftover stop flag: {stop_flag}")

        scrape.status = 'scraping'
        scrape.started_at = datetime.utcnow()
        scrape.expires_at = datetime.utcnow() + timedelta(hours=ttl)
        safe_commit(db)
        log_to_scrape(scrape, f"Scrape {scrape_id} started with platforms: {platforms}", db)
        
        # Get existing video URLs to avoid duplicates
        existing_urls = set(v.url for v in Video.query.all())
        log_to_scrape(scrape, f"Found {len(existing_urls)} existing videos in database", db)
        
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
        
        # Create stop flag file path
        stop_flag = f"stop_{scrape_id}.flag"
        
        for platform in selected_platforms:
            if platform not in platform_map:
                continue
                
            # Check if stopped
            scrape = Scrape.query.get(scrape_id)
            if scrape.status == 'stopped':
                log_to_scrape(scrape, f"Scrape {scrape_id} stopped by user", db)
                # Create stop flag file
                open(stop_flag, 'w').close()
                return
            
            try:
                platform_hashtags = hashtags.get(platform, [])
                if isinstance(platform_hashtags, str):
                    platform_hashtags = [platform_hashtags]
                
                if platform_hashtags:
                    log_to_scrape(scrape, f"Starting {platform.title()} scraping with hashtags: {', '.join(['#' + h for h in platform_hashtags])} ({time_per_platform:.1f} min)...", db)
                else:
                    log_to_scrape(scrape, f"Starting {platform.title()} scraping ({time_per_platform:.1f} min)...", db)
                
                all_links = platform_map[platform](time_per_platform, platform_hashtags, quantity, stop_flag)
                
                # Filter out duplicates
                new_links = [link for link in all_links if link not in existing_urls]
                skipped = len(all_links) - len(new_links)
                
                results[platform] = new_links
                
                # Check if stopped during scraping
                if os.path.exists(stop_flag):
                    log_to_scrape(scrape, f"Scrape {scrape_id} stopped during {platform} scraping", db)
                    os.remove(stop_flag)
                    return
                
                log_to_scrape(scrape, f"{platform.title()}: {len(new_links)} new videos ({skipped} duplicates skipped)", db)
            except Exception as e:
                log_to_scrape(scrape, f"{platform.title()} failed: {e}", db)
                results[platform] = []
        
        # Clean up stop flag if exists
        if os.path.exists(stop_flag):
            os.remove(stop_flag)
        
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
        try:
            video = Video.query.get(video_id)
            scrape = Scrape.query.get(scrape_id)
            
            if not video or not scrape or scrape.status == 'stopped':
                return
            
            platform = video.platform
            
            # Check TTL before downloading
            if scrape.started_at:
                expires_at = scrape.started_at + timedelta(hours=scrape.ttl)
                if datetime.utcnow() >= expires_at:
                    video.status = 'expired'
                    safe_commit(db)
                    return
                
            filename = f"{platform}_{video_id}.mp4"
            path = os.path.join(CACHE_FOLDER, filename)
            
            # Check if already exists
            if os.path.exists(path):
                video.filename = filename
                video.status = 'ready'
                scrape.downloaded_videos += 1
                if scrape.total_videos > 0:
                    scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                safe_commit(db)
                log_to_scrape(scrape, f"✓ Already exists: {filename} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
                check_and_complete_scrape(scrape_id, db, Scrape)
                return
            
            # Check again before starting download
            if scrape.status == 'stopped':
                video.status = 'stopped'
                safe_commit(db)
                return
            
            log_to_scrape(scrape, f"⬇ Downloading: {platform} video {video_id}...", db)
            
            # Commit and release the connection before starting the long download
            db.session.commit()
            db.session.remove()
            
            # Perform the long network download without holding a DB connection
            download_success = False
            download_error = None

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
                'js_runtimes': {'node': {}, 'deno': {}, 'quickjs': {}},
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            }
            import shutil
            import tempfile
            
            temp_cookies_path = None
            project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            # YouTube downloads on EC2 require active logged-in session cookies (selenium_cookies.txt)
            # to bypass anti-bot blocks. Other platforms remain on cookies.txt.
            cookies_file = 'selenium_cookies.txt' if platform == 'youtube' else 'cookies.txt'
            cookies_path = os.path.join(project_root, cookies_file)
            
            # Use cookie_lock to safely copy or initialize the cookies file
            with cookie_lock:
                try:
                    with tempfile.NamedTemporaryFile(suffix="_cookies.txt", delete=False) as tmp_file:
                        temp_cookies_path = tmp_file.name
                    
                    if platform == 'youtube':
                        # YouTube requires both the SOCS consent cookie (from cookies.txt) and
                        # active session cookies (from selenium_cookies.txt) to bypass GDPR and bot blocks on EC2.
                        # We merge both, writing selenium_cookies.txt last so it takes precedence.
                        with open(temp_cookies_path, 'w', encoding='utf-8') as outfile:
                            outfile.write("# Netscape HTTP Cookie File\n# Generated by scraper\n\n")
                            
                            legacy_path = os.path.join(project_root, 'cookies.txt')
                            if os.path.exists(legacy_path):
                                with open(legacy_path, 'r', encoding='utf-8') as f:
                                    outfile.write(f.read())
                                    outfile.write("\n")
                                    
                            selenium_path = os.path.join(project_root, 'selenium_cookies.txt')
                            if os.path.exists(selenium_path):
                                with open(selenium_path, 'r', encoding='utf-8') as f:
                                    outfile.write(f.read())
                                    outfile.write("\n")
                    else:
                        if os.path.exists(cookies_path):
                            shutil.copyfile(cookies_path, temp_cookies_path)
                        else:
                            # Auto-create cookies.txt with a valid Netscape header if it doesn't exist
                            with open(temp_cookies_path, 'w', encoding='utf-8') as f:
                                f.write("# Netscape HTTP Cookie File\n# This file is generated by yt-dlp.  Do not edit.\n\n")
                    
                    ydl_opts['cookiefile'] = temp_cookies_path
                except Exception as ce:
                    print(f"[Scraper] Failed to setup temp cookies: {ce}. Falling back to original.")
                    ydl_opts['cookiefile'] = cookies_path
            
            try:
                with YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    if info:
                        download_success = True
                    else:
                        download_error = "No video info extracted"
            except Exception as e:
                download_error = str(e)
            finally:
                if temp_cookies_path and os.path.exists(temp_cookies_path):
                    # If download succeeded, write the updated cookies back to main file under lock.
                    # Never write back or modify selenium_cookies.txt via yt-dlp.
                    if download_success and cookies_file != 'selenium_cookies.txt':
                        with cookie_lock:
                            try:
                                if os.path.getsize(temp_cookies_path) > 0:
                                    shutil.copyfile(temp_cookies_path, cookies_path)
                                    try:
                                        os.chmod(cookies_path, 0o666)
                                    except:
                                        pass
                            except Exception as ce:
                                print(f"[Scraper] Failed to writeback cookies: {ce}")
                    try:
                        os.remove(temp_cookies_path)
                    except:
                        pass
            
            # Re-fetch objects and update DB status
            video = Video.query.get(video_id)
            scrape = Scrape.query.get(scrape_id)
            
            if not video or not scrape:
                return
                
            if scrape.status == 'stopped':
                video.status = 'stopped'
                safe_commit(db)
                return
                
            if not download_success:
                print(f"Download failed for {url}: {download_error}")
                video.status = 'failed'
                scrape.downloaded_videos += 1
                if scrape.total_videos > 0:
                    scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                safe_commit(db)
                log_to_scrape(scrape, f"✗ Failed: {filename} - {download_error[:50]} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
                check_and_complete_scrape(scrape_id, db, Scrape)
                return
            
            # Check for actual downloaded file
            actual_files = [f for f in os.listdir(CACHE_FOLDER) if f.startswith(f"{video.platform}_{video_id}")]
            if actual_files:
                downloaded_filename = actual_files[0]
                
                # Check watch history
                from backend.models import WatchHistory
                existing_history = WatchHistory.query.filter_by(
                    user_id=scrape.user_id,
                    filename=downloaded_filename
                ).first()
                
                if existing_history:
                    try:
                        os.remove(os.path.join(CACHE_FOLDER, downloaded_filename))
                        log_to_scrape(scrape, f"⊘ Skipped (already watched): {downloaded_filename}", db)
                    except:
                        pass
                    video.status = 'skipped'
                    db.session.delete(video)
                    scrape.downloaded_videos += 1
                    if scrape.total_videos > 0:
                        scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                else:
                    video.filename = downloaded_filename
                    video.status = 'completed'
                    scrape.downloaded_videos += 1
                    if scrape.total_videos > 0:
                        scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                    print(f"✓ Downloaded: {video.filename}")
                    log_to_scrape(scrape, f"✓ Downloaded: {video.filename} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
            else:
                video.status = 'failed'
                scrape.downloaded_videos += 1
                if scrape.total_videos > 0:
                    scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                print(f"✗ Failed: {url}")
                log_to_scrape(scrape, f"✗ Failed: {filename} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
            
            safe_commit(db)
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
            try:
                # Re-fetch objects if session was removed
                video = Video.query.get(video_id)
                scrape = Scrape.query.get(scrape_id)
                if video and scrape:
                    video.status = 'failed'
                    scrape.downloaded_videos += 1
                    if scrape.total_videos > 0:
                        scrape.progress = int((scrape.downloaded_videos / scrape.total_videos) * 100)
                    safe_commit(db)
                    log_to_scrape(scrape, f"✗ Error: {filename} - {str(e)[:50]} ({scrape.downloaded_videos}/{scrape.total_videos})", db)
                    check_and_complete_scrape(scrape_id, db, Scrape)
            except:
                pass
        finally:
            db.session.remove()


def check_and_complete_scrape(scrape_id, db, Scrape):
    """Check if all videos are processed and mark scrape as completed"""
    from backend.models import Video
    scrape = Scrape.query.get(scrape_id)
    if not scrape or scrape.status == 'stopped':
        return
    
    # Count videos that are still downloading
    downloading = Video.query.filter_by(scrape_id=scrape_id, status='downloading').count()
    
    if downloading == 0:
        # Count different statuses (exclude stopped videos)
        completed = Video.query.filter_by(scrape_id=scrape_id, status='completed').count()
        failed = Video.query.filter_by(scrape_id=scrape_id, status='failed').count()
        already = Video.query.filter_by(scrape_id=scrape_id, status='already_downloaded').count()
        skipped = Video.query.filter_by(scrape_id=scrape_id, status='skipped').count()
        stopped = Video.query.filter_by(scrape_id=scrape_id, status='stopped').count()
        
        scrape.status = 'completed'
        safe_commit(db)
        
        # Clear cache so new downloads are visible
        try:
            from backend.cache_store import cache
            cache.clear()
        except Exception as ce:
            print(f"Failed to clear cache on scrape completion: {ce}")
            
        msg = f"All downloads completed! ({completed}/{scrape.total_videos} successful, {failed} failed, {already} already downloaded"
        if skipped > 0:
            msg += f", {skipped} already watched"
        if stopped > 0:
            msg += f", {stopped} stopped"
        msg += ")"
        log_to_scrape(scrape, msg, db)


def cleanup_expired_videos(app, db, Video, CACHE_FOLDER):
    """Cleanup expired videos and scrapes periodically"""
    time.sleep(5)  # Wait for app to initialize
    while True:
        try:
            with app.app_context():
                try:
                    from backend.models import Scrape, SavedVideo
                    now = datetime.utcnow()
                    
                    # Get all saved filenames to protect them
                    saved_filenames = {s.filename for s in SavedVideo.query.all()}
                    
                    # Delete expired videos (but not saved ones)
                    expired_videos = Video.query.filter(Video.expires_at < now).all()
                    for video in expired_videos:
                        if video.filename and video.filename not in saved_filenames:
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
                            if video.filename and video.filename not in saved_filenames:
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
                        try:
                            from backend.cache_store import cache
                            cache.clear()
                        except Exception as ce:
                            print(f"Failed to clear cache on cleanup: {ce}")
                finally:
                    db.session.remove()
        except Exception as e:
            print(f"Cleanup error: {e}")
        time.sleep(300)

def save_cookies(driver, path="selenium_cookies.txt"):
    """Merge new cookies from Selenium with existing cookies in selenium_cookies.txt to avoid overwriting other domains"""
    try:
        new_cookies = driver.get_cookies()
        if not new_cookies:
            return

        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if path == "selenium_cookies.txt":
            path = os.path.join(project_root, "selenium_cookies.txt")

        current_url = driver.current_url.lower()
        current_platform = ""
        if "instagram.com" in current_url:
            current_platform = "instagram"
        elif "youtube.com" in current_url:
            current_platform = "youtube"
        elif "facebook.com" in current_url:
            current_platform = "facebook"

        existing_lines = []
        if os.path.exists(path) and os.path.getsize(path) > 0:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if line.startswith("#") and not stripped.startswith("#HttpOnly_"):
                        existing_lines.append(line)
                        continue
                    if not stripped:
                        existing_lines.append(line)
                        continue

                    # Parse domain from active line
                    raw_line = stripped
                    if raw_line.startswith("#HttpOnly_"):
                        raw_line = raw_line[len("#HttpOnly_"):]
                    
                    parts = raw_line.split("\t")
                    if len(parts) >= 1:
                        domain_val = parts[0]
                        if current_platform and current_platform in domain_val:
                            # Filter out old cookies for current platform to overwrite them with fresh ones
                            continue
                        existing_lines.append(line)

        # Write merged cookies back to file
        with open(path, "w", encoding="utf-8") as f:
            for line in existing_lines:
                f.write(line)

            if current_platform:
                f.write(f"\n# ── UPDATED {current_platform.upper()} COOKIES VIA SELENIUM ──\n")

            for c in new_cookies:
                domain = c.get("domain", "")
                flag = "TRUE" if domain.startswith(".") else "FALSE"
                path_c = c.get("path", "/")
                secure = "TRUE" if c.get("secure") else "FALSE"
                expiry = int(c.get("expiry", 0))
                name = c.get("name")
                value = c.get("value")
                prefix = "#HttpOnly_" if c.get("httpOnly") else ""

                f.write(f"{prefix}{domain}\t{flag}\t{path_c}\t{secure}\t{expiry}\t{name}\t{value}\n")

        # Ensure correct permissions
        try:
            os.chmod(path, 0o666)
        except:
            pass

        print(f"[Cookie Sync] Successfully merged and saved fresh {current_platform} cookies to {path}.")
    except Exception as e:
        print(f"[Cookie Sync] Error merging cookies: {e}")