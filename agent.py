import os
import sys
import requests #type:ignore
from config import SERVER_URL
from backend.agent import scrape_instagram, scrape_youtube, scrape_facebook

SERVER = SERVER_URL
USER_ID = "user_1"

# Initialize default variables from prompt parameters or CLI defaults
if __name__ == "__main__":
    RUN_TIME_MIN = int(input("Enter scraping time (minutes): "))
    TTL = int(input("Enter TTL (hours): "))
else:
    RUN_TIME_MIN = 5
    TTL = 24

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
