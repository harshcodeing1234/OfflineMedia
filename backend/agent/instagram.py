import os
import time
import random
from selenium.webdriver.common.by import By #type:ignore
from backend.agent.driver import create_driver, load_cookies_from_file, safe_load_page

def scrape_instagram(duration_min, hashtags=None, quantity=100, stop_flag=None):
    """Scrape Instagram from explore page or hashtags with rate limiting"""    
    driver = None
    all_links = set()
    
    if hashtags is None:
        hashtags = []
    elif isinstance(hashtags, str):
        hashtags = [hashtags] if hashtags else []

    hashtags = [h for h in hashtags if h]

    try:
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
                # Cookies are read-only and managed by the user manually
                
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
            # Cookies are read-only and managed by the user manually
            
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
