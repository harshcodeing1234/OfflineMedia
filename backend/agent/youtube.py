import os
import time
import shutil
from pathlib import Path
from selenium.webdriver.common.by import By #type:ignore
from selenium.webdriver.common.keys import Keys #type:ignore
from backend.agent.driver import create_driver, load_cookies_from_file, safe_load_page

def scrape_youtube(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape YouTube shorts via navigation or hashtag search"""
    driver = None
    all_links = set()
    
    if hashtags is None:
        hashtags = []
    elif isinstance(hashtags, str):
        hashtags = [hashtags] if hashtags else []

    hashtags = [h for h in hashtags if h]

    try:
        # Clear cached YouTube profile so cookies.txt account is used
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
