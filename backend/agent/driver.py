import os
import time
from pathlib import Path
from selenium import webdriver #type:ignore
from selenium.webdriver.chrome.options import Options #type:ignore
from selenium.webdriver.chrome.service import Service #type:ignore

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
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1920,1080")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    options.add_experimental_option("prefs", {
        "profile.default_content_setting_values.notifications": 2,
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False
    })

    # Correct: chromedriver path
    # Detect environment automatically
    if os.path.exists("/usr/bin/chromedriver"):
        # AWS / Ubuntu
        service = Service("/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)

    elif os.path.exists("/data/data/com.termux/files/usr/bin/chromedriver"):
        # Termux
        service = Service("/data/data/com.termux/files/usr/bin/chromedriver")
        driver = webdriver.Chrome(service=service, options=options)

    else:
        raise RuntimeError("ChromeDriver not found.")
    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT)

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
        except Exception:
            if attempt < retries - 1:
                try:
                    driver.execute_script("window.stop();")
                except:
                    pass
                time.sleep(1)
    return False

def load_cookies_from_file(driver, platform):
    """Dynamically read selenium_cookies.txt and inject cookies into Selenium session"""
    cookie_file = "selenium_cookies.txt"
    if not os.path.exists(cookie_file):
        print(f"[Cookie Injection] No cookies.txt found in root directory.")
        return

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
                if not raw_line or raw_line.startswith("#") and not raw_line.startswith("#HttpOnly_"):
                    continue
                
                is_httponly = False
                if raw_line.startswith("#HttpOnly_"):
                    is_httponly = True
                    raw_line = raw_line[len("#HttpOnly_"):]
                
                # Handle tab or space formatting
                if "\t" in raw_line:
                    parts = raw_line.split("\t")
                else:
                    parts = raw_line.split()
                if len(parts) < 7:
                    continue
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
