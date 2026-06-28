#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Image Downloader v3.0 - 通用网页图片下载器"""

import sys
print("Image Downloader v3.0 starting...", flush=True)

# 依赖检查（提前发现缺失的包）
MISSING = []
try: import requests
except ImportError: MISSING.append("requests")
try: from bs4 import BeautifulSoup
except ImportError: MISSING.append("beautifulsoup4")
try: from PIL import Image
except ImportError: MISSING.append("Pillow")

if MISSING:
    print(f"\n[ERROR] Missing Python packages: {', '.join(MISSING)}")
    print(f"Run: pip install {' '.join(MISSING)}")
    sys.exit(1)

import os, re, json, time, hashlib, random, argparse
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ──────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────

CONFIG_FILE = Path(__file__).with_name("config.json")
DEFAULT_CONFIG = {
    "download_dir": "./downloads",
    "timeout": 20, "retry": 3, "delay": 0.3, "max_redirects": 5,
    "convert_to_jpg": True, "jpg_quality": 92,
    "min_image_bytes": 512, "max_image_bytes": 50 * 1024 * 1024,
    "deep_scan": False,
}

UA_POOL = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64; rv:126.0) Gecko/20100101 Firefox/126.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36 Edg/126.0.0.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
]

IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp",
            ".tiff", ".tif", ".ico", ".avif", ".heic", ".heif"}
SVG_EXTS = {".svg", ".svgz"}

CT_EXT_MAP = {
    "image/jpeg": ".jpg", "image/png": ".png", "image/gif": ".gif",
    "image/webp": ".webp", "image/bmp": ".bmp", "image/svg+xml": ".svg",
    "image/tiff": ".tiff", "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico", "image/avif": ".avif",
    "image/heic": ".heic", "image/heif": ".heif",
}

def load_config():
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return {**DEFAULT_CONFIG, **json.load(f)}
    return dict(DEFAULT_CONFIG)

def rand_ua(): return random.choice(UA_POOL)

def is_image_url(url):
    return any(unquote(urlparse(url).path).lower().endswith(e) for e in IMG_EXTS)
def is_svg_url(url):
    return any(unquote(urlparse(url).path).lower().endswith(e) for e in SVG_EXTS)

def safe_name(url, ct=None):
    path_raw = unquote(urlparse(url).path)
    stem = Path(path_raw).stem
    ext = ""
    if ct:
        ext = CT_EXT_MAP.get(ct.split(";")[0].strip().lower(), "")
    if not ext:
        ue = Path(path_raw).suffix.lower()
        if ue in IMG_EXTS: ext = ue
    if not ext: ext = ".jpg"
    stem = re.sub(r"^.*!_", "", stem)
    if not stem: stem = hashlib.md5(url.encode()).hexdigest()[:12]
    return f"{stem}{ext}"

def fmt_size(b):
    if b is None or b < 0: return "?"
    if b == 0: return "?"
    if b < 1024: return f"{b} B"
    if b < 1024**2: return f"{b/1024:.1f} KB"
    return f"{b/(1024**2):.2f} MB"

def guess_ct_by_magic(data):
    h = data[:12]
    if h[:3] == b"\xff\xd8\xff": return "image/jpeg"
    if h[:8] == b"\x89PNG\r\n\x1a\n": return "image/png"
    if h[:6] in (b"GIF87a", b"GIF89a"): return "image/gif"
    if h[:2] == b"BM": return "image/bmp"
    if h[:4] == b"RIFF" and len(h) >= 12 and h[8:12] == b"WEBP": return "image/webp"
    if h[:4] in (b"\x00\x00\x01\x00", b"\x00\x00\x02\x00"): return "image/x-icon"
    return None

def is_image_magic(data):
    return guess_ct_by_magic(data) is not None

# ──────────────────────────────────────────────
# HTTP 会话
# ──────────────────────────────────────────────

class SmartSession:
    def __init__(self, cfg):
        self.cfg = cfg
        self.s = requests.Session()
        self.s.max_redirects = cfg["max_redirects"]
        self._rotate_ua()

    def _rotate_ua(self):
        self.s.headers.update({
            "User-Agent": rand_ua(),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                                })

    def get(self, url, referer=None, stream=False):
        headers = {"Referer": referer} if referer else {}
        for attempt in range(self.cfg["retry"]):
            try:
                resp = self.s.get(url, headers=headers, timeout=self.cfg["timeout"],
                                  stream=stream, allow_redirects=True)
                if resp.status_code == 503 and attempt < self.cfg["retry"] - 1:
                    time.sleep(2 * (attempt + 1)); self._rotate_ua(); continue
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "").lower()
                if ct.startswith("image/"): return resp
                resp.encoding = resp.apparent_encoding or resp.encoding or "utf-8"
                return resp
            except requests.RequestException:
                if attempt < self.cfg["retry"] - 1:
                    time.sleep(1 * (attempt + 1)); self._rotate_ua(); continue
                raise
        return None

    def head_or_get(self, url, referer=None):
        h = {"Referer": referer} if referer else {}
        for attempt in range(self.cfg["retry"]):
            try:
                resp = self.s.head(url, headers=h, timeout=self.cfg["timeout"], allow_redirects=True)
                if resp.status_code == 403:
                    resp = self.s.get(url, headers=h, timeout=self.cfg["timeout"], stream=True, allow_redirects=True)
                    ct = resp.headers.get("Content-Type", ""); cl = resp.headers.get("Content-Length", "0")
                    resp.close()
                elif resp.status_code == 503:
                    if attempt < self.cfg["retry"] - 1:
                        time.sleep(2 * (attempt + 1)); self._rotate_ua(); continue
                    return (-1, "", resp.status_code)
                else:
                    ct = resp.headers.get("Content-Type", ""); cl = resp.headers.get("Content-Length", "0")
                ct_clean = ct.split(";")[0].strip().lower()
                sz = int(cl) if cl.isdigit() else -1
                if sz == 0: sz = -1
                return (sz, ct_clean, resp.status_code)
            except requests.RequestException:
                if attempt < self.cfg["retry"] - 1:
                    time.sleep(0.5 * (attempt + 1)); continue
                return (-1, "", 0)
        return (-1, "", 0)

    def download(self, url, dest, referer=None):
        headers = {
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        }
        if referer: headers["Referer"] = referer
        for attempt in range(self.cfg["retry"]):
            try:
                resp = self.s.get(url, headers=headers, timeout=self.cfg["timeout"],
                                  stream=True, allow_redirects=True)
                if resp.status_code == 200:
                    ct = resp.headers.get("Content-Type", "")
                    if "text/html" in ct:
                        return (False, "server returned HTML (anti-hotlink/paywall)")
                    data = resp.content
                    if len(data) < self.cfg["min_image_bytes"]:
                        return (False, "too small")
                    if len(data) >= 4 and not is_image_magic(data):
                        if not (data.strip().startswith(b"<") and b"svg" in data[:200].lower()):
                            return (False, "not a valid image (magic bytes mismatch)")
                    with open(dest, "wb") as f: f.write(data)
                    return (True, None)
                elif resp.status_code in (404, 403):
                    return (False, f"HTTP {resp.status_code}")
                elif resp.status_code == 503:
                    if attempt < self.cfg["retry"] - 1:
                        time.sleep(2 * (attempt + 1)); self._rotate_ua(); continue
                    return (False, "HTTP 503")
                else:
                    if attempt < self.cfg["retry"] - 1:
                        time.sleep(1 * (attempt + 1)); continue
                    return (False, f"HTTP {resp.status_code}")
            except requests.RequestException as e:
                if attempt < self.cfg["retry"] - 1:
                    time.sleep(0.5 * (attempt + 1)); continue
                return (False, str(e))
        return (False, "unknown")

    def fetch_text(self, url, referer=None):
        try:
            resp = self.get(url, referer=referer)
            if resp is None: return (None, url, "")
            ct = resp.headers.get("Content-Type", "").lower()
            if ct.startswith("image/"):
                return ("IMAGE_DIRECT", url, ct)
            return (resp.text, resp.url, ct)
        except Exception as e:
            print(f"  [!] fetch failed: {e}")
            return (None, url, "")

# ──────────────────────────────────────────────
# 图片发现引擎
# ──────────────────────────────────────────────

class URLCollector:
    def __init__(self, base_url):
        self.base = base_url
        self.urls = {}
    def add(self, src, source="?", layer=0):
        if not src: return
        full = urljoin(self.base, src).split("?")[0].split("#")[0]
        if full.startswith("data:") or full.startswith("javascript:"): return
        p = urlparse(full)
        if p.scheme not in ("http", "https"): return
        if full not in self.urls: self.urls[full] = {"source": source, "layer": layer}
    def add_abs(self, url, source="?", layer=0):
        if not url or url.startswith("data:"): return
        p = urlparse(url)
        if p.scheme not in ("http", "https"): return
        clean = url.split("?")[0].split("#")[0]
        if clean not in self.urls: self.urls[clean] = {"source": source, "layer": layer}
    def items(self):
        return list(self.urls.keys()), self.urls

class ImageDiscoverer:
    def __init__(self, session, cfg):
        self.session = session
        self.cfg = cfg
        self.collector = None

    def discover(self, html, base_url, deep=False):
        self.collector = URLCollector(base_url)
        self._scan_dom(html, base_url, 0)
        self._scan_raw_text(html, base_url, 1)
        self._scan_ssr_data(html, base_url, 2)
        if deep:
            self._scan_iframes(html, base_url, 3)
            self._scan_external_css(html, base_url, 4)
        return self.collector.items()

    def _scan_dom(self, html, base_url, layer):
        soup = BeautifulSoup(html, "html.parser"); c = self.collector
        for tag in soup.find_all("img"):
            if tag.get("src"): c.add(tag["src"], "img", layer)
            for attr in ("data-src", "data-lazy-src", "data-original",
                         "data-url", "data-lazyload", "data-srcset"):
                v = tag.get(attr)
                if v:
                    for part in re.split(r"[\s,]+", v):
                        part = re.sub(r"\s+\d+[wx]$", "", part.strip())
                        if part and not part.startswith("data:"):
                            c.add(part, f"img[{attr}]", layer)
        for tag in soup.find_all(["img", "source"]):
            ss = tag.get("srcset", "")
            if ss:
                for part in re.split(r"[\s]*,[\s]*", ss):
                    uc = re.split(r"\s+", part.strip())[0]
                    if uc and not uc.startswith("data:"): c.add(uc, "srcset", layer)
        for tag in soup.find_all("source"):
            src = tag.get("src") or tag.get("srcset")
            if src:
                for part in re.split(r"[\s,]+", src):
                    part = re.sub(r"\s+\d+[wx]$", "", part.strip())
                    if part: c.add(part, "picture", layer)
        for a in soup.find_all("a", href=True):
            lp = urlparse(a["href"]).path.lower()
            if any(lp.endswith(e) for e in IMG_EXTS): c.add(a["href"], "a[href]", layer)
        for tag in soup.find_all(style=True):
            for m in re.finditer(r"url\([\"']?([^)\"']+)[\"']?\)", tag["style"]):
                c.add(m.group(1), "inline-css", layer)
        for meta in soup.find_all("meta"):
            prop = (meta.get("property") or meta.get("name") or "").lower()
            if prop in ("og:image", "twitter:image", "og:image:url"):
                v = meta.get("content")
                if v: c.add(v, f"meta[{prop}]", layer)
        for link in soup.find_all("link", href=True):
            rel = link.get("rel") or []
            if isinstance(rel, str): rel = [rel]
            rl = [r.lower() for r in rel]
            if "icon" in rl or "apple-touch-icon" in rl:
                c.add(link["href"], "link-icon", layer)
        for s in soup.find_all("script", type="application/ld+json"):
            try: self._walk_json(json.loads(s.string or ""), base_url, layer)
            except (json.JSONDecodeError, TypeError): pass

    def _walk_json(self, data, base_url, layer, depth=0):
        if depth > 5: return
        if isinstance(data, dict):
            for k in ("image", "thumbnailUrl", "thumbnail", "url", "contentUrl",
                      "img", "pic", "src", "logo", "icon"):
                if k in data:
                    v = data[k]
                    if isinstance(v, str): self.collector.add(v, f"jsonld[{k}]", layer)
                    elif isinstance(v, dict) and "url" in v: self.collector.add(v["url"], f"jsonld[{k}]", layer)
                    elif isinstance(v, list):
                        for item in v:
                            if isinstance(item, str): self.collector.add(item, f"jsonld[{k}]", layer)
                            elif isinstance(item, dict):
                                for fk in ("url", "src", "image"):
                                    if fk in item: self.collector.add(item[fk], f"jsonld[{k}]", layer)
            for val in data.values():
                if isinstance(val, (dict, list)): self._walk_json(val, base_url, layer, depth + 1)
        elif isinstance(data, list):
            for item in data: self._walk_json(item, base_url, layer, depth + 1)

    def _scan_raw_text(self, html, base_url, layer):
        c = self.collector
        for m in re.finditer(r"""["'\(]\s*(https?://[^"'\s\)]{4,}\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^"'\s\)]*)?)""", html, re.I):
            c.add_abs(m.group(1), "raw-abs", layer)
        for m in re.finditer(r"""["'\(]\s*(/(?:[^"'\s\)]*/)*[^"'\s\)]{1,200}\.(?:jpg|jpeg|png|gif|webp|bmp|svg)(?:\?[^"'\s\)]*)?)""", html, re.I):
            c.add(m.group(1), "raw-rel", layer)
        for m in re.finditer(r"""["']\s*((?:https?:)?//[^"']{4,200}?\.(?:jpg|jpeg|png|gif|webp|bmp)(?:\?[^"']*)?)""", html, re.I):
            c.add_abs(m.group(1), "raw-cdn", layer)
        for m in re.finditer(r"""["'](?:image|img|url|src|pic|cover|thumb)["']\s*:\s*["']([^"']{4,300}\.(?:jpg|jpeg|png|gif|webp|bmp|svg)[^"']{0,50})""", html, re.I):
            u = m.group(1).strip()
            if u.startswith("//"): u = "https:" + u
            elif u.startswith("/"): u = urljoin(base_url, u)
            c.add_abs(u, "json-field", layer)

    def _scan_ssr_data(self, html, base_url, layer):
        c = self.collector
        for m in re.finditer(r'<script[^>]*id\s*=\s*["\']__NEXT_DATA__[^>]*>(.*?)</script>', html, re.S):
            try: self._walk_json(json.loads(m.group(1).strip()), base_url, layer)
            except: pass
        for m in re.finditer(r'window\.__NUXT__\s*=\s*({.*?});', html, re.S):
            try: self._walk_json(json.loads(m.group(1).strip()), base_url, layer)
            except: pass
        for m in re.finditer(r'window\.__(?:INITIAL_)?STATE__\s*=\s*({.*?});', html, re.S):
            try: self._walk_json(json.loads(m.group(1).strip()), base_url, layer)
            except: pass
        for m in re.finditer(r'<script[^>]*type\s*=\s*["\']application/json["\'][^>]*>(.*?)</script>', html, re.S):
            raw = m.group(1).strip()[:500000]
            try: self._walk_json(json.loads(raw), base_url, layer)
            except: pass

    def _scan_iframes(self, html, base_url, layer):
        soup = BeautifulSoup(html, "html.parser")
        iframes = soup.find_all("iframe", src=True)
        if not iframes: return
        print(f"  [L{layer}] Scanning {len(iframes)} iframe(s)...")
        for tag in iframes[:5]:
            src = tag["src"]; iframe_url = urljoin(base_url, src)
            try:
                text, _, _ = self.session.fetch_text(iframe_url, referer=base_url)
                if text and isinstance(text, str) and len(text) > 100:
                    self._scan_dom(text, iframe_url, layer=layer)
                    self._scan_raw_text(text, iframe_url, layer=layer)
            except: pass

    def _scan_external_css(self, html, base_url, layer):
        soup = BeautifulSoup(html, "html.parser")
        css_urls = [urljoin(base_url, l["href"]) for l in soup.find_all("link", rel="stylesheet", href=True)]
        if not css_urls: return
        print(f"  [L{layer}] Scanning {len(css_urls)} CSS file(s)...")
        for css_url in css_urls[:5]:
            try:
                resp = self.session.get(css_url, referer=base_url)
                if resp and hasattr(resp, 'text'):
                    for m in re.finditer(r"url\([\"']?([^)\"']+)[\"']?\)", resp.text):
                        self.collector.add(m.group(1), "ext-css", layer)
            except: pass

# ──────────────────────────────────────────────
# 格式转换
# ──────────────────────────────────────────────

def convert_to_jpg(src_path, quality=92):
    if src_path.suffix.lower() in (".jpg", ".jpeg"): return src_path
    if src_path.suffix.lower() in (".svg", ".svgz"): return src_path
    try:
        img = Image.open(src_path)
        if img.mode in ("RGBA", "LA", "P", "PA"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P": img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"): bg.paste(img, mask=img.split()[-1])
            else: bg.paste(img)
            img = bg
        elif img.mode not in ("RGB", "L"): img = img.convert("RGB")
        jpg_path = src_path.with_suffix(".jpg")
        img.save(jpg_path, "JPEG", quality=quality, optimize=True)
        if src_path != jpg_path and src_path.exists(): src_path.unlink()
        return jpg_path
    except: return src_path

# ──────────────────────────────────────────────
# 主程序
# ──────────────────────────────────────────────

class ImageDownloader:
    def __init__(self, args=None):
        self.cfg = load_config()
        self.args = args or {}
        if self.args.get("no_convert"): self.cfg["convert_to_jpg"] = False
        self.deep = self.args.get("deep", self.cfg.get("deep_scan", False))
        self.session = SmartSession(self.cfg)
        self.finder = ImageDiscoverer(self.session, self.cfg)

    def _download_one(self, url, name=None, referer=None):
        dl = Path(self.cfg["download_dir"]); dl.mkdir(parents=True, exist_ok=True)
        if not name: name = safe_name(url)
        dest = dl / name
        ok, err = self.session.download(url, dest, referer=referer)
        if not ok: return (False, err, None)
        final = convert_to_jpg(dest, self.cfg["jpg_quality"]) if self.cfg["convert_to_jpg"] else dest
        return (True, None, final)

    def run(self, url, raw_select=None):
        if not url.startswith("http"): url = "https://" + url
        print(f"\n{'='*60}")
        print(f"  Image Downloader v3.0")
        print(f"  URL: {url}")
        if self.deep: print(f"  Mode: DEEP (all layers)")
        print(f"{'='*60}")

        text, final_url, ct = self.session.fetch_text(url)
        if text is None: return
        if text == "IMAGE_DIRECT":
            print(f"[+] Direct image ({ct})")
            ok, err, final = self._download_one(final_url, safe_name(final_url, ct))
            print(f"  {'OK -> '+str(final.absolute())+' ('+fmt_size(final.stat().st_size)+')' if ok else 'FAIL: '+err}")
            return

        base_url = final_url
        print(f"[OK] Page: {len(text)} chars")
        urls, meta = self.finder.discover(text, base_url, deep=self.deep)

        layer_counts = {}
        for u, info in meta.items(): layer_counts[info["layer"]] = layer_counts.get(info["layer"], 0) + 1
        summary = " + ".join(f"L{n}:{c}" for n, c in sorted(layer_counts.items()))
        print(f"[+] Found {len(urls)} candidates ({summary})")

        if not urls:
            print("[!] No images found.")
            if not self.deep: print("[TIP] Try --deep for iframe + CSS scanning.")
            return

        print(f"\n[*] Probing {len(urls)} URLs...")
        results = []
        for i, u in enumerate(urls, 1):
            print(f"\r  {i}/{len(urls)}", end="", flush=True)
            sz, ct, st = self.session.head_or_get(u, referer=base_url)
            info = meta.get(u, {})
            results.append({
                "url": u, "size": sz, "content_type": ct, "status": st,
                "source": info.get("source", "?"), "layer": info.get("layer", 0),
                "rejected": ct.startswith("text/html") if ct else False,
                "is_svg": is_svg_url(u) or ct == "image/svg+xml",
            })
            time.sleep(self.cfg["delay"])
        print()

        display = self._build_display(results)
        if not display:
            print("[!] No downloadable images after filtering.")
            return

        if raw_select is not None:
            self._auto_download(display, raw_select, base_url)
        else:
            self._interactive_loop(display, base_url)

    def _build_display(self, results):
        print(f"\n{'='*85}")
        print(f"{'#':>4}  {'Size':>10}  {'Sts':>4}  {'Source':<18}  Filename")
        print(f"{'='*85}")
        dl = []; idx = 1
        for r in results:
            if r["status"] == 404 and r["size"] <= 0: continue
            if r["rejected"]: continue
            ct = r.get("content_type", "")
            if ct and "image" not in ct and "svg" not in ct and r["size"] <= 0: continue
            name = safe_name(r["url"], ct)
            sz = fmt_size(r["size"])
            st = "OK" if r["status"] == 200 else str(r["status"]) if r["status"] > 0 else "??"
            src = r["source"][:18]
            tag = " [SVG]" if r.get("is_svg") else ""
            print(f"{idx:>4}  {sz:>10}  {st:>4}  {src:<18}  {name}{tag}")
            dl.append({**r, "name": name, "index": idx})
            idx += 1
        if not dl: print("  (nothing downloadable)")
        else:
            svg_count = sum(1 for d in dl if d.get("is_svg"))
            if svg_count: print(f"  NOTE: {svg_count} SVG file(s) - won't convert to JPG")
        print(f"{'='*85}")
        return dl

    def _parse_selection(self, raw, display):
        sel = set()
        for part in [p.strip() for p in raw.split(",")]:
            if not part: continue
            m = re.match(r"^([><]=?)\s*(\d+\.?\d*)\s*(B|KB|MB|GB)$", part, re.I)
            if m:
                op, val, unit = m.group(1), float(m.group(2)), m.group(3).upper()
                mul = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}
                th = int(val * mul[unit])
                for d in display:
                    if d["size"] < 0: continue
                    if (op == ">" and d["size"] > th) or (op == ">=" and d["size"] >= th) or \
                       (op == "<" and d["size"] < th) or (op == "<=" and d["size"] <= th):
                        sel.add(d["index"])
                continue
            m = re.match(r"^(\d+)\s*-\s*(\d+)$", part)
            if m:
                for i in range(int(m.group(1)), int(m.group(2)) + 1): sel.add(i)
                continue
            if part.isdigit(): sel.add(int(part))
        return sel

    def _download_many(self, display, selected, referer):
        if not selected: return
        ids = sorted(selected)
        dl = Path(self.cfg["download_dir"]); dl.mkdir(parents=True, exist_ok=True)
        ok_cnt = fail_cnt = 0
        print(f"\n>>> Downloading {len(ids)} to {dl.absolute()}\n")
        for i in ids:
            d = next((x for x in display if x["index"] == i), None)
            if not d: continue
            name = d.get("name", safe_name(d["url"]))
            print(f"  [{i}/{len(display)}] {name}", end="", flush=True)
            ok, err, final = self._download_one(d["url"], name, referer=referer)
            if not ok: print(f" FAIL: {err}"); fail_cnt += 1
            else:
                sz = fmt_size(final.stat().st_size) if final else "?"
                print(f" OK ({sz})"); ok_cnt += 1
            time.sleep(self.cfg["delay"])
        print(f"\n[DONE] {ok_cnt} OK / {fail_cnt} FAIL / {len(ids)} total")

    def _auto_download(self, display, raw_select, referer):
        sel = set(d["index"] for d in display) if raw_select == "all" else self._parse_selection(raw_select, display)
        if not sel: print(f"[!] No match: {raw_select}"); return
        chosen = [d for d in display if d["index"] in sel]
        print(f"\nAuto-selected {len(chosen)}:")
        for d in sorted(chosen, key=lambda x: x["index"]):
            print(f"  [{d['index']}] {d['name']} ({fmt_size(d['size'])})")
        self._download_many(display, sel, referer)

    def _interactive_loop(self, display, referer):
        while True:
            print("\n[?] number | 1,3,7 | 2-6 | >100KB | <1MB | >=500KB | all | q")
            raw = input("\n> ").strip().lower()
            if raw in ("q", "quit", "exit"): print("Bye!"); break
            sel = set(d["index"] for d in display) if raw == "all" else self._parse_selection(raw, display)
            if not sel: print("[!] Invalid, try again"); continue
            chosen = [d for d in display if d["index"] in sel]
            print(f"\nSelected {len(chosen)}:")
            for d in sorted(chosen, key=lambda x: x["index"]):
                extra = " [SVG]" if d.get("is_svg") else ""
                print(f"  [{d['index']}] {d['name']} ({fmt_size(d['size'])}){extra}")
            if input("\nDownload? (y/n): ").strip().lower() in ("y", "yes"):
                self._download_many(display, sel, referer)
            if input("\nContinue? (y/n): ").strip().lower() not in ("y", "yes"):
                print("Bye!"); break


def parse_args():
    p = argparse.ArgumentParser(description="Universal Image Downloader")
    p.add_argument("url", nargs="?", help="Webpage URL or direct image URL")
    p.add_argument("--select", "-s", help="Auto-select: '1-5,>100KB' or 'all'")
    p.add_argument("--no-convert", action="store_true", help="Keep original format")
    p.add_argument("--delay", type=float, help="Delay between requests (seconds)")
    p.add_argument("--deep", action="store_true", help="Enable ALL discovery layers")
    return p.parse_args()


def main():
    args = parse_args()
    opts = {"no_convert": args.no_convert, "deep": args.deep}
    dl = ImageDownloader(opts)
    if args.delay is not None: dl.cfg["delay"] = args.delay

    if not args.url:
        try:
            print("\n[Image Downloader v3.0]")
            print("Usage: python image_downloader.py <url> [--deep] [--select '1-5']")
            args.url = input("\nURL: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[!] No URL provided. Run: python image_downloader.py <url>")
            return
        if not args.url:
            print("[!] URL required"); return

    dl.run(args.url, args.select)


if __name__ == "__main__":
    main()
