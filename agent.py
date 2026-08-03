import time
import requests #type:ignore
import sys
import random 
import tempfile
from pathlib import Path
from selenium import webdriver #type:ignore
from selenium.webdriver.common.by import By #type:ignore
from selenium.webdriver.common.keys import Keys #type:ignore
from selenium.webdriver.chrome.options import Options #type:ignore
from selenium.webdriver.chrome.service import Service #type:ignore
from selenium.webdriver.support.ui import WebDriverWait #type:ignore
from selenium.webdriver.support import expected_conditions as EC #type:ignore
from selenium.common.exceptions import TimeoutException #type:ignore
from scraper import save_cookies
import os
from config import SERVER_URL

SERVER = SERVER_URL
USER_ID = "user_1"

if __name__ == "__main__":
    RUN_TIME_MIN = int(input("Enter scraping time (minutes): "))
    TTL = int(input("Enter TTL (hours): "))
else:
    RUN_TIME_MIN = 5
    TTL = 24

MAX_RETRIES = 3
PAGE_LOAD_TIMEOUT = 45

def create_driver(profile_name):
    """Create Chrome driver (Termux + PC compatible)"""

    options = Options()

    # Chrome browser path
    chrome_path = "/data/data/com.termux/files/usr/bin/chromium-browser"
    if os.path.exists(chrome_path):
        options.binary_location = chrome_path

    # Profile
    profile_dir = Path.home() / "selenium-profiles" / profile_name
    profile_dir.mkdir(parents=True, exist_ok=True)
    options.add_argument(f"--user-data-dir={profile_dir}") 

    # Stability options
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-notifications")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    # Termux ke liye headless MUST 
    # if profile_name != "instagram":
    #     options.add_argument("--headless=new")
    # options.add_argument("--disable-software-rasterizer")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })

    # Correct: chromedriver path
    chromedriver_path = "/data/data/com.termux/files/usr/bin/chromedriver"

    if os.path.exists(chromedriver_path):
        service = Service(chromedriver_path)
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)

    driver.set_page_load_timeout(45)

    # Anti-detection (safe)
    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": """
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            """
        })
    except:
        pass

    return driver

def safe_load_page(driver, url, retries=MAX_RETRIES):
    """Load page with retry logic"""
    for attempt in range(retries):
        try:
            driver.get(url)
            time.sleep(2)
            return True
        except TimeoutException:
            if attempt < retries - 1:
                try:
                    driver.execute_script("window.stop();")
                except:
                    pass
                time.sleep(1)
        except Exception:
            if attempt < retries - 1:
                time.sleep(1)
    return False


def load_cookies_from_file(driver, platform):
    """Dynamically read selenium_cookies.txt and inject cookies into Selenium session for the active domain"""
    cookie_file = "selenium_cookies.txt"  # separate file — yt-dlp never touches this
    if not os.path.exists(cookie_file):
        print(f"[Cookie Injection] No cookies.txt found in root directory.")
        return

    # FIX #5: Use the correct domain URL for each platform (was always youtube for non-instagram)
    if platform == "instagram":
        domain_url = "https://www.instagram.com"
    elif platform == "facebook":
        domain_url = "https://www.facebook.com"
    else:
        domain_url = "https://www.youtube.com"

    try:
        driver.get(domain_url)
        time.sleep(3)
        
        cookies_added = 0
        with open(cookie_file, "r", encoding="utf-8") as f:
            for line in f:
                raw_line = line.strip()
                if not raw_line:
                    continue
                
                is_httponly = False
                if raw_line.startswith("#HttpOnly_"):
                    is_httponly = True
                    raw_line = raw_line[len("#HttpOnly_"):]
                elif raw_line.startswith("#"):
                    continue
                
                # Handle both tab-separated (Cookie-Editor) and space-separated (yt-dlp) formats
                if "\t" in raw_line:
                    parts = raw_line.split("\t")
                else:
                    parts = raw_line.split()
                if len(parts) < 7:
                    continue
                # yt-dlp space-split may over-split value if it contains spaces — rejoin from index 6
                if len(parts) > 7:
                    parts = parts[:6] + [" ".join(parts[6:])]
                
                cookie_domain = parts[0]
                if platform in cookie_domain:
                    domain_val = cookie_domain
                    cookie = {
                        'name': parts[5],
                        'value': parts[6],
                        'domain': domain_val,
                        'path': parts[2],
                        'secure': parts[3] == 'TRUE',
                        'httpOnly': is_httponly
                    }
                    
                    try:
                        expiry = int(parts[4])
                        if expiry > 0:
                            cookie['expiry'] = expiry
                    except:
                        pass
                    
                    try:
                        driver.add_cookie(cookie)
                        cookies_added += 1
                    except Exception:
                        if domain_val.startswith('.'):
                            try:
                                cookie['domain'] = domain_val[1:]
                                driver.add_cookie(cookie)
                                cookies_added += 1
                            except:
                                pass
        
        if cookies_added > 0:
            print(f"[Cookie Injection] Successfully injected {cookies_added} cookies for {platform}.")
            driver.refresh()
            time.sleep(3)
    except Exception as e:
        print(f"[Cookie Injection] Error injecting cookies: {e}")


def scrape_instagram(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape Instagram from explore page or hashtags with rate limiting"""    
    driver = None
    all_links = set()
    
    # FIX #1: Normalize hashtags first, then open the try block at function level
    # (was accidentally indented inside elif, so driver was never created)
    if hashtags is None:
        hashtags = []
    elif isinstance(hashtags, str):
        hashtags = [hashtags] if hashtags else []

    hashtags = [h for h in hashtags if h]  # moved to correct indentation level

    try:  # try block now correctly at function body level
        driver = create_driver("instagram")
        load_cookies_from_file(driver, "instagram")
        
        if hashtags:
            # Divide quantity equally among hashtags
            per_hashtag = quantity // len(hashtags)
            time_per_hashtag = duration_min / len(hashtags)
            
            for hashtag in hashtags:
                if stop_flag and os.path.exists(stop_flag):
                    print("Instagram scraping stopped by user")
                    break
                    
                if len(all_links) >= quantity:
                    break
                    
                url = f"https://www.instagram.com/explore/tags/{hashtag}/"
                if not safe_load_page(driver, url):
                    continue
                
                time.sleep(5)
                cookies = driver.get_cookies()
                if any(c['name'] == 'sessionid' for c in cookies):
                    save_cookies(driver, path="selenium_cookies.txt")
                
                start_time = time.time()
                hashtag_links = set()
                
                while time.time() - start_time < time_per_hashtag * 60 and len(hashtag_links) < per_hashtag:
                    if stop_flag and os.path.exists(stop_flag):
                        print("Instagram scraping stopped by user")
                        break
                        
                    try:
                        elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/reel/') or contains(@href, '/p/')]")
                        
                        for elem in elements:
                            try:
                                href = elem.get_attribute("href")
                                if href and "instagram.com" in href:
                                    hashtag_links.add(href)
                                    if len(hashtag_links) >= per_hashtag:
                                        break
                            except:
                                pass
                        
                        print(f"IG #{hashtag}: {len(hashtag_links)}/{per_hashtag}")
                        
                        if len(hashtag_links) >= per_hashtag:
                            break
                        
                        driver.execute_script("window.scrollBy(0, 1500);")
                        time.sleep(random.uniform(1, 1.5))
                        
                    except Exception as e:
                        print(f"Error: {e}")
                        time.sleep(2)
                
                all_links.update(hashtag_links)
                print(f"IG #{hashtag}: {len(hashtag_links)} collected\n")
        else:
            # Original explore scraping
            url = "https://www.instagram.com/explore/"
            if not safe_load_page(driver, url):
                return []
            
            time.sleep(5)
            cookies = driver.get_cookies()
            if any(c['name'] == 'sessionid' for c in cookies):
                save_cookies(driver, path="selenium_cookies.txt")
            
            start_time = time.time()
            
            while time.time() - start_time < duration_min * 60 and len(all_links) < quantity:
                if stop_flag and os.path.exists(stop_flag):
                    print("Instagram scraping stopped by user")
                    break
                    
                try:
                    elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/reel/') or contains(@href, '/p/')]")
                    
                    for elem in elements:
                        try:
                            href = elem.get_attribute("href")
                            if href and "instagram.com" in href:
                                all_links.add(href)
                        except:
                            pass
                    
                    print(f"IG: {len(all_links)}/{quantity}")
                    
                    if len(all_links) >= quantity:
                        break
                    
                    driver.execute_script("window.scrollBy(0, 1500);")
                    time.sleep(random.uniform(1, 1.5))
                    
                except Exception as e:
                    print(f"Error: {e}")
                    time.sleep(2)
        
        print(f"Instagram: {len(all_links)} reels total\n")
        
    except Exception as e:
        print(f"Instagram failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return list(all_links)


def scrape_youtube(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape YouTube shorts via navigation or hashtag search"""
    
    driver = None
    all_links = set()
    
    # FIX #2: Normalize hashtags first, then open the try block at function level
    # (driver = create_driver(...) was accidentally indented under hashtag filter line)
    if hashtags is None:
        hashtags = []
    elif isinstance(hashtags, str):
        hashtags = [hashtags] if hashtags else []

    hashtags = [h for h in hashtags if h]

    try:  # try block now correctly at function body level
        # Clear cached YouTube profile so cookies.txt account is used, not old saved session
        import shutil
        yt_profile = Path.home() / "selenium-profiles" / "youtube"
        if yt_profile.exists():
            shutil.rmtree(yt_profile)
        yt_profile.mkdir(parents=True, exist_ok=True)

        driver = create_driver("youtube")
        load_cookies_from_file(driver, "youtube")
        
        if hashtags:
            # Divide quantity equally among hashtags
            per_hashtag = quantity // len(hashtags)
            time_per_hashtag = duration_min / len(hashtags)
            
            for hashtag in hashtags:
                if stop_flag and os.path.exists(stop_flag):
                    print("YouTube scraping stopped by user")
                    break
                    
                if len(all_links) >= quantity:
                    break
                
                url = f"https://www.youtube.com/results?search_query=%23{hashtag}+shorts&sp=EgIYAQ%253D%253D"
                if not safe_load_page(driver, url):
                    continue
                
                time.sleep(2)
                start_time = time.time()
                hashtag_links = set()
                
                while time.time() - start_time < time_per_hashtag * 60 and len(hashtag_links) < per_hashtag:
                    if stop_flag and os.path.exists(stop_flag):
                        print("YouTube scraping stopped by user")
                        break
                        
                    try:
                        elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/shorts/')]")
                        for elem in elements:
                            try:
                                href = elem.get_attribute("href")
                                if href and "/shorts/" in href:
                                    hashtag_links.add(href.split('?')[0])
                                    if len(hashtag_links) >= per_hashtag:
                                        break
                            except:
                                pass
                        
                        print(f"YT #{hashtag}: {len(hashtag_links)}/{per_hashtag}")
                        
                        if len(hashtag_links) >= per_hashtag:
                            break
                        
                        driver.execute_script("window.scrollBy(0, 1000);")
                        time.sleep(0.5)
                        
                    except Exception as e:
                        print(f"Error: {e}")
                        time.sleep(1)
                
                all_links.update(hashtag_links)
                print(f"YT #{hashtag}: {len(hashtag_links)} collected\n")
        else:
            # Original shorts feed navigation
            url = "https://www.youtube.com/shorts"
            if not safe_load_page(driver, url):
                return []
            
            time.sleep(2)
            start_time = time.time()
            
            while time.time() - start_time < duration_min * 60 and len(all_links) < quantity:
                if stop_flag and os.path.exists(stop_flag):
                    print("YouTube scraping stopped by user")
                    break
                    
                try:
                    current_url = driver.current_url
                    
                    if "/shorts/" in current_url:
                        all_links.add(current_url)
                    
                    print(f"YT: {len(all_links)}/{quantity}")
                    
                    if len(all_links) >= quantity:
                        break
                    
                    try:
                        driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
                    except:
                        driver.execute_script("window.scrollBy(0, 1000);")
                    
                    time.sleep(0.4)
                    
                except Exception as e:
                    print(f"Error: {e}")
                    time.sleep(1)
        
        print(f"YouTube: {len(all_links)} shorts total\n")
        
    except Exception as e:
        print(f"YouTube failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return list(all_links)


def scrape_facebook(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape Facebook reels from watch page"""
    
    driver = None
    all_links = set()

    # FIX #3 & #4: Move try block to function level so driver is created unconditionally.
    # Also move refresh_watch() definition AFTER driver is assigned, and pass driver
    # as a parameter so it is always in scope (was an UnboundLocalError closure bug).
    try:
        driver = create_driver("facebook")
        load_cookies_from_file(driver, "facebook")

        # FIX #4: refresh_watch now receives driver as argument — no closure scope issue
        def refresh_watch(driver):
            driver.get("https://www.facebook.com/watch")
            try:
                WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
            except:
                pass
            time.sleep(2)
            for _ in range(3):
                driver.execute_script("window.scrollBy(0, 1500);")
                time.sleep(0.2)

        refresh_watch(driver)
        
        start_time = time.time()
        
        while time.time() - start_time < duration_min * 60 and len(all_links) < quantity:
            if stop_flag and os.path.exists(stop_flag):
                print("Facebook scraping stopped by user")
                break
                
            try:
                elements = [e for e in driver.find_elements(By.TAG_NAME, "a") if e.get_attribute("href")]
            except:
                elements = []
            
            for e in elements:
                try:
                    href = e.get_attribute("href")
                    if href and "facebook.com" in href:
                        if "/reel/" in href:
                            reel_id = href.split("/reel/")[1].split("/")[0].split("?")[0]
                            href = f"https://www.facebook.com/reel/{reel_id}"
                        elif "/watch/?v=" in href:
                            video_id = href.split("v=")[1].split("&")[0]
                            href = f"https://www.facebook.com/watch/?v={video_id}"
                        elif "/videos/" in href:
                            href = href.split("?")[0]
                        else:
                            continue
                        
                        all_links.add(href)
                        if len(all_links) >= quantity:
                            break
                except:
                    pass
            
            print(f"FB: {len(all_links)}/{quantity}")
            
            if len(all_links) >= quantity:
                break
            
            for _ in range(2):
                driver.execute_script(f"window.scrollBy(0, {random.randint(1500, 2500)});")
                time.sleep(random.uniform(0.5, 1))
        
        print(f"Facebook: {len(all_links)} videos\n")
        
    except Exception as e:
        print(f"Facebook failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return list(all_links)


def send_to_server(platform, links):
    """Send scraped links to server"""
    payload = {
        "user": USER_ID,
        "category": platform,
        "links": links,
        "ttl": TTL,
        "status": "completed"
    }
    
    try:
        response = requests.post(f"{SERVER}/upload", json=payload, timeout=30)
        print(f"{platform}: {len(links)} videos sent (status {response.status_code})")
    except Exception as e:
        print(f"{platform} upload error: {e}")


if __name__ == "__main__":
    print(f"\n{'='*50}\nSCRAPING SESSION\n{'='*50}")
    print(f"Duration: {RUN_TIME_MIN} min | TTL: {TTL}h\n")
    
    # Ask for quantity
    quantity = int(input("Quantity per platform (default 100): ") or 100)
    
    # Ask for hashtags
    use_hashtags = input("Use hashtags? (y/n): ").lower() == 'y'
    hashtags = {}
    if use_hashtags:
        for platform in ['instagram', 'youtube']:
            tags = input(f"{platform.title()} hashtags (comma-separated, leave empty to skip): ").strip()
            if tags:
                hashtags[platform] = [t.strip().replace('#', '') for t in tags.split(',') if t.strip()]
    
    time_per_platform = RUN_TIME_MIN / 3
    results = {}
    
    # Sequential execution
    for platform, scraper in [("instagram", scrape_instagram), ("youtube", scrape_youtube), ("facebook", scrape_facebook)]:
        try:
            platform_hashtags = hashtags.get(platform, [])
            results[platform] = scraper(time_per_platform, platform_hashtags, quantity)
        except Exception as e:
            print(f"✗ {platform} failed: {e}")
            results[platform] = []
    
    # Send to server
    print(f"\n{'='*50}\nUPLOADING TO SERVER\n{'='*50}")
    for platform, links in results.items():
        send_to_server(platform, links)
    
    # Summary
    total = sum(len(v) for v in results.values())
    print(f"\n{'='*50}\nCOMPLETED\n{'='*50}")
    print(f"Instagram: {len(results['instagram'])}")
    print(f"YouTube: {len(results['youtube'])}")
    print(f"Facebook: {len(results['facebook'])}")
    print(f"Total: {total} videos\n")
