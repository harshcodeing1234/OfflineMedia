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
from pathlib import Path
import tempfile
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

MAX_VIDEOS_PER_PLATFORM = 100
MAX_RETRIES = 3
PAGE_LOAD_TIMEOUT = 45

def create_driver(profile_name):
    """Create Chrome driver (Termux + PC compatible)"""


    options = Options()

    # Correct: Chrome browser path (NOT chromedriver)
    chrome_path = "/data/data/com.termux/files/usr/bin/chromium-browser"
    if os.path.exists(chrome_path):
        options.binary_location = chrome_path

    # Profile (safe)
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
    if profile_name != "instagram":
        options.add_argument("--headless=new")
    options.add_argument("--disable-software-rasterizer")

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


def scrape_instagram(duration_min):
    """Scrape Instagram from explore page with rate limiting"""    
    driver = None
    all_links = set()
    
    try:
        driver = create_driver("instagram")
        
        if not safe_load_page(driver, "https://www.instagram.com/explore/"):
            return []
        
        if __name__ == "__main__":
            # wait until login really complete
            WebDriverWait(driver, 60).until(
                EC.presence_of_element_located((By.XPATH, "//a[contains(@href,'/reel/')]"))
            )

            # check login cookie
            cookies = driver.get_cookies()
            if not any(c['name'] == 'sessionid' for c in cookies):
                print("Login not detected properly")
            else:
                print("Login detected - saving cookies...")
                save_cookies(driver)
                print("✓ Cookies saved to cookies.txt")
        else:
            # When running from web app, wait for login session to load
            time.sleep(5)
            # Save cookies for yt-dlp if not already saved
            cookies = driver.get_cookies()
            if any(c['name'] == 'sessionid' for c in cookies):
                save_cookies(driver)
                print("✓ Instagram session active, cookies saved")
        
        start_time = time.time()
        last_total = 0
        no_growth = 0
        scroll_count = 0
        
        while time.time() - start_time < duration_min * 60:
            try:
                elements = driver.find_elements(By.XPATH, "//a[contains(@href, '/reel/') or contains(@href, '/p/')]")
                
                for elem in elements:
                    try:
                        href = elem.get_attribute("href")
                        if href and "instagram.com" in href:
                            all_links.add(href)
                    except:
                        pass
                
                print(f"IG: {len(all_links)} total")
                
                if len(all_links) >= MAX_VIDEOS_PER_PLATFORM:
                    break
                
                if len(all_links) == last_total:
                    no_growth += 1
                    if no_growth >= 3:
                        for _ in range(5):
                            driver.execute_script("window.scrollBy(0, 2000);")
                            time.sleep(random.uniform(0.5, 1))
                        no_growth = 0
                else:
                    no_growth = 0
                
                last_total = len(all_links)
                
                # Rate limiting: balanced scrolling
                scroll_count += 1
                driver.execute_script("window.scrollBy(0, 1500);")
                
                # Add random delays every few scrolls
                if scroll_count % 5 == 0:
                    time.sleep(random.uniform(1.5, 2.5))
                else:
                    time.sleep(random.uniform(1, 1.5))
                
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(2)
        
        print(f"Instagram: {len(all_links)} reels\n")
        
    except Exception as e:
        print(f"Instagram failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return list(all_links)


def scrape_youtube(duration_min):
    """Scrape YouTube shorts via navigation"""
    
    driver = None
    all_links = set()
    
    try:
        driver = create_driver("youtube")
        
        if not safe_load_page(driver, "https://www.youtube.com/shorts"):
            return []
        
        time.sleep(2)
        start_time = time.time()
        last_total = 0
        no_growth = 0
        
        while time.time() - start_time < duration_min * 60:
            try:
                current_url = driver.current_url
                
                if "/shorts/" in current_url:
                    all_links.add(current_url)
                    print(f"YT: {len(all_links)} total")
                
                if len(all_links) >= MAX_VIDEOS_PER_PLATFORM:
                    break
                
                if len(all_links) == last_total:
                    no_growth += 1
                    if no_growth >= 8:
                        safe_load_page(driver, "https://www.youtube.com/shorts")
                        no_growth = 0
                else:
                    no_growth = 0
                
                last_total = len(all_links)
                
                try:
                    driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ARROW_DOWN)
                except:
                    driver.execute_script("window.scrollBy(0, 1000);")
                
                time.sleep(0.4)
                
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(1)
        
        print(f"YouTube: {len(all_links)} shorts\n")
        
    except Exception as e:
        print(f"YouTube failed: {e}")
    finally:
        if driver:
            try:
                driver.quit()
            except:
                pass
    
    return list(all_links)


def scrape_facebook(duration_min):
    """Scrape Facebook reels from watch page"""
    
    driver = None
    all_links = set()
    
    def refresh_watch():
        driver.get("https://www.facebook.com/watch")
        try:
            WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.TAG_NAME, "a")))
        except:
            pass
        time.sleep(2)
        for _ in range(3):
            driver.execute_script("window.scrollBy(0, 1500);")
            time.sleep(0.2)
    
    try:
        driver = create_driver("facebook")
        refresh_watch()
        
        start_time = time.time()
        last_total = 0
        no_growth = 0
        
        while time.time() - start_time < duration_min * 60:
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
                except:
                    pass
            
            print(f"FB: {len(all_links)} total")
            
            if len(all_links) >= MAX_VIDEOS_PER_PLATFORM:
                break
            
            if len(all_links) == last_total:
                no_growth += 1
                if no_growth >= 3:
                    refresh_watch()
                    no_growth = 0
                    continue
            else:
                no_growth = 0
            
            last_total = len(all_links)
            
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
    print(f"Duration: {RUN_TIME_MIN} min | TTL: {TTL}h | Max: {MAX_VIDEOS_PER_PLATFORM}/platform\n")
    
    time_per_platform = RUN_TIME_MIN / 3
    results = {}
    
    # Sequential execution
    for platform, scraper in [("instagram", scrape_instagram), ("youtube", scrape_youtube), ("facebook", scrape_facebook)]:
        try:
            results[platform] = scraper(time_per_platform)
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
