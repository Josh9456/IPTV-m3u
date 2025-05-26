# main.py (final with base64 proxy decoding for validation)
import os
import re
import sys
import time
import base64
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

# Files in Git:
# - tivimate_playlist.m3u8 (input, overwritten)
# - links.m3u8 (validated URLs)
# - channels.m3u8 (proxy mappings)

CHANNELS_URL = 'https://josh9456-myproxy.hf.space/playlist/channels'
PREMIUM = re.compile(r'premium(\d+)/mono\.m3u8')
PROXY_PREFIX = 'https://josh9456-myproxy.hf.space/watch/'

# 1. Fetch channels.m3u8
def fetch_channels(dest='channels.m3u8'):
    print(f"⬇️ Fetching channels from {CHANNELS_URL}")
    try:
        resp = requests.get(CHANNELS_URL, timeout=10)
        if resp.status_code == 200:
            with open(dest, 'wb') as f:
                f.write(resp.content)
            print(f"✅ {dest} updated")
        else:
            print(f"❌ Failed fetch (HTTP {resp.status_code})")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Fetch error: {e}")
        sys.exit(1)

# 2. Validate premium URLs (with proxy base64 decode)
def validate_links(src='tivimate_playlist.m3u8', out='links.m3u8'):
    if not os.path.exists(src):
        print(f"❌ {src} missing.")
        sys.exit(1)

    decoded_urls = set()

    with open(src, 'r') as f:
        for line in f:
            line = line.strip()
            if line.startswith(PROXY_PREFIX):
                try:
                    b64 = line[len(PROXY_PREFIX):].split('.m3u8')[0]
                    decoded = base64.b64decode(b64).decode().strip()
                    decoded_urls.add(decoded)
                except Exception as e:
                    print(f"⚠️ Could not decode base64 in line: {line} — {e}")
            elif PREMIUM.search(line):
                decoded_urls.add(line)

    ids = set()
    for url in decoded_urls:
        match = PREMIUM.search(url)
        if match:
            ids.add(match.group(1))

    if not ids:
        print("⚠️ No premium IDs found after decoding.")
        sys.exit(1)

    print(f"✅ Extracted Premium IDs: {ids}")

    templates = [
        'https://nfsnew.newkso.ru/nfs/premium{}/mono.m3u8',
        'https://windnew.newkso.ru/wind/premium{}/mono.m3u8',
        'https://zekonew.newkso.ru/zeko/premium{}/mono.m3u8',
        'https://dokko1new.newkso.ru/dokko1/premium{}/mono.m3u8',
        'https://ddy6new.newkso.ru/ddy6/premium{}/mono.m3u8'
    ]

    candidates = [t.format(i) for i in ids for t in templates]
    valid = []
    print(f"🔎 Checking {len(candidates)} URLs")

    def check(u):
        headers = {'User-Agent': 'Mozilla/5.0'}
        for i in range(1, 6):
            print(f"🌍 {u} (try {i})")
            try:
                r = requests.head(u, headers=headers, allow_redirects=True, timeout=10)
                if r.status_code == 200:
                    return u
                if r.status_code == 429:
                    time.sleep(5)
                    continue
                if r.status_code == 404:
                    return None
                r = requests.get(u, headers=headers, timeout=10)
                if r.status_code == 200:
                    return u
            except:
                return None
        return None

    with ThreadPoolExecutor(max_workers=10) as ex:
        for res in ex.map(check, candidates):
            if res:
                valid.append(res)

    with open(out, 'w') as f:
        f.write("\n".join(valid))
    print(f"🎉 {len(valid)} valid written to {out}")

# 3. Build proxy mapping from channels file
def build_proxy_map(channels='channels.m3u8'):
    if not os.path.exists(channels):
        print(f"❌ {channels} missing.")
        sys.exit(1)
    proxy_map = {}  # original URL -> (EXTINF line, proxy URL line)
    lines = open(channels).read().splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF') and i+1 < len(lines):
            ext = line
            url = lines[i+1]
            if '/watch/' in url:
                b64 = url.split('/watch/')[1].split('.m3u8')[0]
                try:
                    orig = base64.b64decode(b64).decode().strip()
                    proxy_map[orig] = (ext, url)
                except:
                    continue
    print(f"✅ Proxy map entries: {len(proxy_map)}")
    return proxy_map

# 4. Rewrite playlist in-place with full proxy entries
def assemble(src='tivimate_playlist.m3u8',
             links='links.m3u8',
             channels='channels.m3u8'):
    valid = set(open(links).read().splitlines())
    proxy_map = build_proxy_map(channels)

    out = []
    lines = open(src).read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF') and i+1 < len(lines):
            url_line = lines[i+1]
            original_url = url_line
            if url_line.startswith(PROXY_PREFIX):
                try:
                    b64 = url_line[len(PROXY_PREFIX):].split('.m3u8')[0]
                    original_url = base64.b64decode(b64).decode().strip()
                except:
                    pass
            if original_url in valid and original_url in proxy_map:
                ext, proxy_url = proxy_map[original_url]
                out.append(ext)
                out.append(proxy_url)
                i += 2
                continue
        out.append(line)
        i += 1

    with open(src, 'w') as f:
        f.write("\n".join(out) + "\n")
    print(f"🔄 Overwrote {src} with full proxy entries")

if __name__ == '__main__':
    fetch_channels()
    print('=== Validate Links ===')
    validate_links()
    print('=== Assemble Playlist ===')
    assemble()
    print('=== All Done ===')
