# main.py  – validate links, rebuild proxy URLs, rewrite tivimate_playlist.m3u8
import argparse
import base64
import logging
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

PROXY_PREFIX = 'https://josh9456-myproxy.hf.space/watch/'
PREMIUM_RE   = re.compile(r'premium(\d+)/mono\.m3u8')

URL_TEMPLATES = [
    "https://nfsnew.newkso.ru/nfs/premium{num}/mono.m3u8",
    "https://windnew.newkso.ru/wind/premium{num}/mono.m3u8",
    "https://zekonew.newkso.ru/zeko/premium{num}/mono.m3u8",
    "https://dokko1new.newkso.ru/dokko1/premium{num}/mono.m3u8",
    "https://ddy6new.newkso.ru/ddy6/premium{num}/mono.m3u8"
]

INPUT_PLAYLIST  = "tivimate_playlist.m3u8"
VALID_LINKS_OUT = "links.m3u8"


# -----------------------------------------------------------------------------
# 1.  Validate every possible premium URL extracted from tivimate_playlist.m3u8
# -----------------------------------------------------------------------------
def validate_links(src=INPUT_PLAYLIST, out=VALID_LINKS_OUT, workers=10):
    log = logging.getLogger("validate_links")
    log.info("Stage 1 ▸ scanning %s", src)

    decoded_urls = []
    with open(src, encoding="utf-8") as fin:
        for line in fin:
            if line.startswith(PROXY_PREFIX):
                try:
                    b64 = line.split('/watch/')[1].split('.m3u8')[0]
                    decoded = base64.b64decode(b64).decode().strip()
                    decoded_urls.append(decoded)
                    log.debug("decoded ⇒ %s", decoded)
                except Exception as e:
                    log.debug("base64 decode failed: %s", e)

    ids = {m.group(1) for u in decoded_urls if (m := PREMIUM_RE.search(u))}
    if not ids:
        log.error("No premium{num} identifiers found – aborting.")
        raise SystemExit(1)

    log.info("Found %d unique premium IDs: %s", len(ids), sorted(ids))

    candidates = [tpl.format(num=i) for i in ids for tpl in URL_TEMPLATES]
    log.info("Generated %d candidate URLs to test", len(candidates))

    def check(url):
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Origin':   'https://lefttoplay.xyz',
            'Referer':  'https://lefttoplay.xyz/'
        }
        for attempt in range(1, 4):
            try:
                log.debug("HEAD  %s  (try %d)", url, attempt)
                r = requests.head(url, headers=headers, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    return url
                if r.status_code == 429:
                    log.debug("429 – sleeping 5 s before retry")
                    time.sleep(5)
                    continue
                if r.status_code == 404:
                    return None
                # fallback to GET for odd responses
                log.debug("GET   %s  (try %d)", url, attempt)
                r = requests.get(url, headers=headers, timeout=10, stream=True, allow_redirects=True)
                if r.status_code == 200:
                    return url
                if r.status_code == 404:
                    return None
            except requests.RequestException as e:
                log.debug("Request error %s: %s", url, e)
                return None
        return None

    valid = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check, u): u for u in candidates}
        for fut in as_completed(futures):
            res = fut.result()
            if res:
                valid.append(res)
                log.info("✓ %s", res)

    with open(out, "w", encoding="utf-8") as fout:
        fout.write("\n".join(valid))

    log.info("Stage 1 complete – %d valid URLs written to %s", len(valid), out)
    return valid


# -----------------------------------------------------------------------------
# 2.  Build {original stream → new proxy link} mapping from the validated URLs
# -----------------------------------------------------------------------------
def build_proxy_map(valid_links):
    log = logging.getLogger("build_proxy_map")
    proxy_map = {}
    for link in valid_links:
        encoded = base64.b64encode(link.encode()).decode()
        proxy_map[link] = f"{PROXY_PREFIX}{encoded}.m3u8"
        log.debug("%s  →  %s", link, proxy_map[link])
    log.info("Stage 2 complete – proxy map has %d entries", len(proxy_map))
    return proxy_map


# -----------------------------------------------------------------------------
# 3.  Rewrite only stream lines inside tivimate_playlist.m3u8
# -----------------------------------------------------------------------------
def rewrite_streams(src=INPUT_PLAYLIST, proxy_map=None):
    log = logging.getLogger("rewrite_streams")

    lines = open(src, encoding="utf-8").read().splitlines()
    out_lines, replaced = [], 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF") and i + 1 < len(lines):
            out_lines.append(line)             # keep EXTINF
            stream = lines[i + 1].strip()
            decoded = None

            if stream.startswith(PROXY_PREFIX):
                try:
                    b64 = stream.split('/watch/')[1].split('.m3u8')[0]
                    decoded = base64.b64decode(b64).decode().strip()
                except Exception:
                    pass

            if decoded and decoded in proxy_map:
                out_lines.append(proxy_map[decoded])
                log.debug("Replaced %s → %s", stream, proxy_map[decoded])
                replaced += 1
            else:
                out_lines.append(stream)
            i += 2
        else:
            out_lines.append(line)
            i += 1

    with open(src, "w", encoding="utf-8") as fout:
        fout.write("\n".join(out_lines) + "\n")

    log.info("Stage 3 complete – %d stream URLs replaced", replaced)


# -----------------------------------------------------------------------------
# entry-point
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Refresh tivimate_playlist.m3u8 with working proxy links")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="show DEBUG-level detail (per-URL checks, replacements)")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s │ %(name)s │ %(message)s")

    logging.info("▶️  Starting playlist refresh (verbose=%s)", args.verbose)

    valid = validate_links()
    proxy_map = build_proxy_map(valid)
    rewrite_streams(proxy_map=proxy_map)

    logging.info("✅  Done – playlist refreshed")


if __name__ == "__main__":
    main()
