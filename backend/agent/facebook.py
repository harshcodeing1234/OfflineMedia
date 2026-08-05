import os
import time
import random
from selenium.webdriver.common.by import By #type:ignore
from selenium.webdriver.support.ui import WebDriverWait #type:ignore
from selenium.webdriver.support import expected_conditions as EC #type:ignore
from backend.agent.driver import create_driver, load_cookies_from_file

def scrape_facebook(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape Facebook reels from watch page"""
    driver = None
    all_links = set()

    try:
        driver = create_driver("facebook")
        load_cookies_from_file(driver, "facebook")

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
