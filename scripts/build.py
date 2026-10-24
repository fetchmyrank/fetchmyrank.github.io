"""Builds one ranking map (PNG + web page) per file in data/*.json into site/."""
import json, math, os, glob, html, collections, time
import requests
from PIL import Image, ImageDraw, ImageFont

Z = 13
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
UA = {"User-Agent": "FetchMyRank-maps/1.0 (fetchmyrank@gmail.com)"}
FONT_DIRS = ["/usr/share/fonts/truetype/dejavu/"]
RED, ORANGE, AMBER, GREEN = (196, 48, 43), (214, 96, 40), (230, 160, 30), (34, 139, 84)
INK, MUTED, BG = (28, 28, 30), (105, 105, 110), (250, 248, 244)


def font(bold, size):
    name = "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"
    for d in FONT_DIRS:
        if os.path.exists(d + name):
            return ImageFont.truetype(d + name, size)
    return ImageFont.load_default()


def to_px(lat, lng):
    n = 2 ** Z * 256
    x = (lng + 180) / 360 * n
    y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n
    return x, y


def tile(x, y):
    os.makedirs(".tiles", exist_ok=True)
    p = f".tiles/{Z}_{x}_{y}.png"
    if not os.path.exists(p):
        r = requests.get(TILE_URL.format(z=Z, x=x, y=y), headers=UA, timeout=30)
        r.raise_for_status()
        open(p, "wb").write(r.content)
        time.sleep(0.2)
    return Image.open(p).convert("RGB")


def rank_num(r):
    return int(r) if str(r).isdigit() else None


def color(r):
    n = rank_num(r)
    if n is None:
        return RED
    return GREEN if n <= 3 else AMBER if n <= 10 else ORANGE


def build(d, out):
    pts = [p for p in d["points"] if p.get("rank") != "N"]
    xy = [to_px(p["lat"], p["lng"]) for p in d["points"]]
    pad = 55
    minx, maxx = min(x for x, _ in xy) - pad, max(x for x, _ in xy) + pad
    miny, maxy = min(y for _, y in xy) - pad, max(y for _, y in xy) + pad
    tx0, tx1, ty0, ty1 = int(minx // 256), int(maxx // 256), int(miny // 256), int(maxy // 256)
    big = Image.new("RGB", ((tx1 - tx0 + 1) * 256, (ty1 - ty0 + 1) * 256))
    for tx in range(tx0, tx1 + 1):
        for ty in range(ty0, ty1 + 1):
            big.paste(tile(tx, ty), ((tx - tx0) * 256, (ty - ty0) * 256))
    ox, oy = tx0 * 256, ty0 * 256
    crop = big.crop((int(minx - ox), int(miny - oy), int(maxx - ox), int(maxy - oy)))
    S = 1.55
    crop = crop.resize((int(crop.width * S), int(crop.height * S)), Image.LANCZOS)
    crop = Image.blend(crop, Image.new("RGB", crop.size, (255, 255, 255)), 0.35)
    header, panel, footer = 200, 340, 70
    img = Image.new("RGB", (crop.width + panel, header + crop.height + footer), BG)
    img.paste(crop, (0, header))
    dr = ImageDraw.Draw(img)
    dr.text((36, 30), d["business"], font=font(True, 40), fill=INK)
    dr.text((36, 90), f"Google Maps search: “{d['keyword']}” · {len(pts)} spots across ~{d['span']}",
            font=font(False, 21), fill=MUTED)
    top3 = sum(1 for p in pts if rank_num(p["rank"]) and rank_num(p["rank"]) <= 3)
    miss = sum(1 for p in pts if not rank_num(p["rank"]))
    x = 36
    for big_t, small in [(f"{top3}/{len(pts)}", "spots where you're top 3"),
                         (f"{miss}/{len(pts)}", "spots where you're not in the top 20")]:
        dr.text((x, 128), big_t, font=font(True, 38), fill=RED)
        w = dr.textlength(big_t, font=font(True, 38))
        dr.text((x + w + 10, 144), small, font=font(False, 19), fill=MUTED)
        x += w + 10 + dr.textlength(small, font=font(False, 19)) + 40
    for p, (px, py) in zip(d["points"], xy):
        if p.get("rank") == "N":
            continue
        cx, cy = (px - minx) * S, (py - miny) * S + header
        R = 22
        dr.ellipse((cx - R + 3, cy - R + 4, cx + R + 3, cy + R + 4), fill=(150, 150, 150))
        dr.ellipse((cx - R, cy - R, cx + R, cy + R), fill=color(p["rank"]), outline="white", width=4)
        lab = str(p["rank"]) if rank_num(p["rank"]) else "–"
        f = font(True, 20 if len(lab) < 3 else 16)
        dr.text((cx - dr.textlength(lab, font=f) / 2, cy - 12), lab, font=f, fill="white")
    bx, by = to_px(d["lat"], d["lng"])
    cx, cy = (bx - minx) * S, (by - miny) * S + header
    dr.polygon([(cx, cy + 46), (cx - 12, cy + 26), (cx + 12, cy + 26)], fill=INK)
    dr.rounded_rectangle((cx - 60, cy + 46, cx + 60, cy + 74), 8, fill=INK)
    t = "Your listing"
    dr.text((cx - dr.textlength(t, font=font(True, 15)) / 2, cy + 51), t, font=font(True, 15), fill="white")
    px0, y = crop.width + 28, header + 10
    dr.text((px0, y), "Who shows up #1", font=font(True, 24), fill=INK); y += 38
    dr.text((px0, y), "instead of you", font=font(False, 19), fill=MUTED); y += 42
    me = d["business"].lower()
    c = collections.Counter(p["top"][0] for p in pts if p.get("top") and p["top"][0].lower() != me)
    for name, k in c.most_common(6):
        nm = name if len(name) <= 26 else name[:25] + "…"
        dr.text((px0, y), nm, font=font(True, 17), fill=INK)
        dr.rounded_rectangle((px0, y + 28, px0 + max(8, int(260 * k / len(pts))), y + 40), 5, fill=RED)
        dr.text((px0 + int(260 * k / len(pts)) + 10, y + 22), str(k), font=font(True, 17), fill=INK)
        y += 64
    y += 14
    dr.text((px0, y), "Legend", font=font(True, 19), fill=INK); y += 32
    for cc, txt in [(GREEN, "Top 3 (gets the calls)"), (AMBER, "4–10"), (ORANGE, "11–20"), (RED, "–  Not in top 20")]:
        dr.ellipse((px0, y, px0 + 22, y + 22), fill=cc)
        dr.text((px0 + 34, y), txt, font=font(False, 17), fill=INK); y += 32
    H = img.height
    dr.text((36, H - 48), f"Checked {d['date']} · Google Maps results at each spot · Map data © OpenStreetMap contributors",
            font=font(False, 15), fill=MUTED)
    t = "FetchMyRank"
    dr.text((img.width - 36 - dr.textlength(t, font=font(True, 19)), H - 50), t, font=font(True, 19), fill=INK)
    os.makedirs(out, exist_ok=True)
    img.save(f"{out}/map.png", optimize=True)
    rows = "".join(
        f"<tr><td>{p['r']+1}-{p['c']+1}</td><td>{html.escape(str(p['rank']) if rank_num(p['rank']) else 'not in top 20')}</td>"
        f"<td>{html.escape(', '.join(p.get('top', [])[:3]))}</td></tr>" for p in pts)
    page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex">
<title>{html.escape(d['business'])} | Google Maps ranking map</title>
<style>body{{font-family:system-ui,sans-serif;max-width:980px;margin:0 auto;padding:16px;color:#1c1c1e;background:#faf8f4}}
img{{width:100%;height:auto;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:14px}}
td,th{{border-bottom:1px solid #ddd;padding:6px;text-align:left}}a{{color:#2b45b8}}</style></head><body>
<h1>{html.escape(d['business'])}</h1>
<p>Google Maps search: “{html.escape(d['keyword'])}”, checked {html.escape(d['date'])}. Top 3 in {top3} of {len(pts)} spots.</p>
<img src="map.png" alt="Ranking map for {html.escape(d['business'])}">
<h2>Who shows up at each spot</h2>
<table><tr><th>Spot (row-col)</th><th>Your rank</th><th>Top results there</th></tr>{rows}</table>
<p><a href="https://fetchmyrank.tinypages.co/groomers">FetchMyRank</a> · Map data © OpenStreetMap contributors</p>
</body></html>"""
    open(f"{out}/index.html", "w").write(page)


def main():
    os.makedirs("site", exist_ok=True)
    open("site/index.html", "w").write('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=https://fetchmyrank.tinypages.co/groomers">')
    open("site/robots.txt", "w").write("User-agent: *\nDisallow: /\n")
    for f in sorted(glob.glob("data/*.json")):
        d = json.load(open(f))
        build(d, f"site/{d['slug']}")
        print("built", d["slug"])


if __name__ == "__main__":
    main()
