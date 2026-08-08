"""
YouTube Download Diagnostic Script
Run this on AWS EC2 to check which player_client works:

    python3 test_youtube_download.py

It will test each client and print which one succeeds.
"""
import sys
import os
from yt_dlp import YoutubeDL  # type: ignore

# Test with this Shorts video ID
TEST_URL = "https://www.youtube.com/shorts/r6Ib6w-sdjM"

COOKIES_FILE = os.path.join(os.path.dirname(__file__), "selenium_cookies.txt")

def check_yt_dlp_version():
    import yt_dlp
    print(f"yt-dlp version: {yt_dlp.version.__version__}")
    import shutil
    ffmpeg = shutil.which("ffmpeg")
    print(f"ffmpeg:  {'found at ' + ffmpeg if ffmpeg else 'NOT FOUND (format merging disabled)'}")
    deno = shutil.which("deno") or (os.path.expanduser("~/.deno/bin/deno") if os.path.exists(os.path.expanduser("~/.deno/bin/deno")) else None)
    node = shutil.which("node") or shutil.which("nodejs")
    print(f"deno:    {'found at ' + deno if deno else 'NOT FOUND ← THIS IS THE PROBLEM'}")
    print(f"node:    {'found at ' + node if node else 'NOT FOUND'}")
    if not deno and not node:
        print()
        print("  !! NO JS RUNTIME: YouTube signature solving will fail.")
        print("  !! Fix: curl -fsSL https://deno.land/install.sh | sh && source ~/.bashrc")
    print()

def test_client(client_list, fmt, use_cookies=True):
    opts = {
        'quiet': False,
        'no_warnings': False,
        'skip_download': True,   # Only fetch info, don't download
        'format': fmt,
        'extractor_args': {
            'youtube': {'player_client': client_list}
        },
    }
    if use_cookies and os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0:
        opts['cookiefile'] = COOKIES_FILE

    label = f"client={client_list}, format='{fmt}', cookies={'yes' if use_cookies else 'no'}"
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(TEST_URL, download=False)
            if info:
                fmt_id = info.get('format_id', 'unknown')
                title = info.get('title', 'N/A')
                print(f"  ✓ SUCCESS [{label}]")
                print(f"    title={title!r}, format_id={fmt_id}")
                return True
            else:
                print(f"  ✗ FAILED [{label}]: No info returned")
                return False
    except Exception as e:
        print(f"  ✗ FAILED [{label}]: {str(e)[:120]}")
        return False

if __name__ == "__main__":
    check_yt_dlp_version()
    print(f"Testing URL: {TEST_URL}")
    print(f"Cookies file: {COOKIES_FILE if os.path.exists(COOKIES_FILE) else 'NOT FOUND'}")
    print("=" * 60)

    tests = [
        # (client_list, format_string, use_cookies)
        (['tv_embedded'],              '18',                          False),
        (['tv_embedded'],              '18',                          True),
        (['android'],                  '18',                          False),
        (['android'],                  '18',                          True),
        (['web_embedded'],             '18',                          False),
        (['web_embedded'],             '18',                          True),
        (['android_vr'],               'best',                        False),
        (['mweb'],                     'best',                        False),
        (['tv_embedded', 'android'],   '18/best',                     True),
        (['web'],                      'best',                        True),
    ]

    results = []
    for client_list, fmt, use_cookies in tests:
        success = test_client(client_list, fmt, use_cookies)
        results.append((client_list, fmt, use_cookies, success))

    print()
    print("=" * 60)
    print("SUMMARY:")
    for client_list, fmt, use_cookies, success in results:
        status = "✓ WORKS" if success else "✗ FAILS"
        print(f"  {status}  client={client_list}, format='{fmt}', cookies={'yes' if use_cookies else 'no'}")
