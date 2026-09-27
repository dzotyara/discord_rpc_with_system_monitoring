#!/usr/bin/env python3
"""Render the generated cards of the GitHub profile README.

    python3 scripts/build_profile.py              # live data from the GitHub API
    python3 scripts/build_profile.py --offline    # re-render from data/snapshot.json

A live run saves what it fetched to data/snapshot.json. If the API fails, the
cards are rendered from that snapshot instead, so a bad API day never breaks
the profile. Standard library only: the workflow needs nothing but Python.
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
import textwrap
import time
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"

# Botyara's palette, picked from backseat/docs/assets/avatar.png.
BG, PANEL, BORDER = "#0e0b1d", "#161230", "#2c2360"
TEXT, MUTED, TRACK = "#e9e6ff", "#8f89c0", "#241d4d"
TEAL, PURPLE, CORAL, YELLOW = "#3ee6c8", "#8b6cff", "#ff6b6b", "#ffd166"

PIXEL_COLORS = {
    "W": "#f4f4fb",
    "L": "#d4d4e6",
    "G": "#a6a4c7",
    "O": "#68629a",
    "S": "#151427",
    "s": "#262a4a",
    "E": "#42f5e3",
    "e": "#25aaa5",
    "C": "#ff6b6b",
    "c": "#cd4e5c",
    "X": "#ffffff",
    "A": "#ff6b6b",
    "a": "#cd4e5c",
    "H": "#ffffff",
    "D": "#ffffff",
    "R": "#42f5e3",
    "r": "#f4f4fb",
}
# What the static layer shows under the animated pixels ("." = nothing).
UNDER = {"D": "C", "R": "s", "r": "s", "A": ".", "a": ".", "H": "."}

# GitHub's own language colours, so the bar reads like the one on repo pages.
LANG_COLORS = {
    "Python": "#3572A5",
    "HTML": "#e34c26",
    "CSS": "#663399",
    "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6",
    "Go": "#00ADD8",
    "Shell": "#89e051",
    "Dockerfile": "#384d54",
    "Mako": "#7e858d",
    "Jinja": "#a52a22",
}
OTHER_COLOR = "#6e6a9a"

MONO = "'JBMono', 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
SANS = "'gg sans', 'Noto Sans', 'Segoe UI', 'Helvetica Neue', Helvetica, Arial, sans-serif"
EMOJI = "'Apple Color Emoji', 'Segoe UI Emoji', 'Noto Color Emoji', sans-serif"
CALM = "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"

CONTRIBUTIONS = (
    "query($login: String!) { user(login: $login) { contributionsCollection"
    " { contributionCalendar { totalContributions } } } }"
)


# --------------------------------------------------------------------------- data


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def parse_time(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def warn(message: str) -> None:
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") == "true" else "warning: "
    print(prefix + message, file=sys.stderr)


def http_json(url: str, token: str | None = None, payload: dict | None = None):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "profile-cards",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = None
    if payload is not None:
        body = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)


def own_repos(repos: list[dict], login: str) -> list[dict]:
    """Repos that are really mine: no forks, archives, empty repos or the profile repo itself."""
    return [
        repo
        for repo in repos
        if not repo.get("fork")
        and not repo.get("archived")
        and repo.get("size") != 0
        and repo["name"].lower() != login.lower()
    ]


def fetch_github(login: str, token: str | None = None, get=http_json, now: dt.datetime | None = None) -> dict:
    """Everything the cards need, in the same shape as data/snapshot.json."""
    user = get(f"{API}/users/{login}", token)
    repos = [
        {
            "name": repo["name"],
            "fork": repo.get("fork", False),
            "archived": repo.get("archived", False),
            "stars": repo.get("stargazers_count", 0),
            "size": repo.get("size"),
            "pushed_at": repo.get("pushed_at") or repo.get("updated_at"),
            "description": repo.get("description") or "",
        }
        for repo in get(f"{API}/users/{login}/repos?per_page=100&type=owner&sort=pushed", token)
        if not repo.get("private")
    ]
    languages: dict[str, int] = {}
    for repo in own_repos(repos, login):
        for name, size in get(f"{API}/repos/{login}/{repo['name']}/languages", token).items():
            languages[name] = languages.get(name, 0) + size
    contributions = None
    if token:  # GraphQL does not answer anonymous requests
        try:
            answer = get(f"{API}/graphql", token, {"query": CONTRIBUTIONS, "variables": {"login": login}})
            calendar = answer["data"]["user"]["contributionsCollection"]["contributionCalendar"]
            contributions = calendar["totalContributions"]
        except Exception as error:  # a missing number is not worth failing the whole run
            warn(f"contributions unavailable: {error}")
    return {
        "source": "GitHub API",
        "fetched_at": iso(now or utcnow()),
        "user": {
            "login": user["login"],
            "name": user.get("name") or user["login"],
            "created_at": user["created_at"],
            "public_repos": user.get("public_repos", len(repos)),
            "followers": user.get("followers"),
        },
        "repos": repos,
        "languages": languages,
        "contributions_last_year": contributions,
    }


def cpu_times(proc: Path) -> tuple[int, int]:
    fields = [int(value) for value in (proc / "stat").read_text().splitlines()[0].split()[1:]]
    return fields[3] + (fields[4] if len(fields) > 4 else 0), sum(fields)


def short_cpu(model: str) -> str:
    model = re.sub(r"\((R|TM)\)|\bCPU\b|\bProcessor\b|@.*$|\b\d+-Core\b", "", model, flags=re.I)
    return " ".join(model.split())


def system_stats(proc: Path = Path("/proc"), interval: float = 0.5, sleep=time.sleep) -> dict:
    """CPU, RAM and swap of the machine drawing the card: the Discord RPC monitor's metrics."""
    stats = {
        "cpu_model": None,
        "cpu_count": os.cpu_count(),
        "cpu_percent": None,
        "mem_total": None,
        "mem_used": None,
        "swap_total": None,
        "swap_used": None,
    }
    try:
        match = re.search(r"^model name\s*:\s*(.+)$", (proc / "cpuinfo").read_text(), re.M)
        if match:
            stats["cpu_model"] = short_cpu(match.group(1))
        idle_before, total_before = cpu_times(proc)
        sleep(interval)
        idle_after, total_after = cpu_times(proc)
        if total_after > total_before:
            busy = 1 - (idle_after - idle_before) / (total_after - total_before)
            stats["cpu_percent"] = max(0.0, min(100.0, 100 * busy))
        memory = {}
        for line in (proc / "meminfo").read_text().splitlines():
            key, _, rest = line.partition(":")
            memory[key] = int(rest.split()[0]) * 1024
        stats["mem_total"] = memory["MemTotal"]
        stats["mem_used"] = memory["MemTotal"] - memory.get("MemAvailable", memory.get("MemFree", 0))
        stats["swap_total"] = memory.get("SwapTotal", 0)
        stats["swap_used"] = memory.get("SwapTotal", 0) - memory.get("SwapFree", 0)
    except (OSError, ValueError, KeyError, IndexError) as error:
        warn(f"system stats unavailable, the card will say n/a: {error}")
    return stats


def human_uptime(start: dt.datetime, now: dt.datetime) -> str:
    """Calendar distance like '6 years, 1 month, 28 days'."""
    years, months, days = now.year - start.year, now.month - start.month, now.day - start.day
    if days < 0:
        months -= 1
        days += (now.replace(day=1) - dt.timedelta(days=1)).day
    if months < 0:
        years -= 1
        months += 12
    parts = [(years, "year"), (months, "month"), (days, "day")]
    return ", ".join(f"{n} {unit}{'' if n == 1 else 's'}" for n, unit in parts if n) or "0 days"


def top_languages(sizes: dict[str, int], limit: int = 3) -> list[tuple[str, float, str]]:
    """[(name, percent, colour)] for the biggest languages, the rest folded into 'Other'."""
    total = sum(sizes.values())
    if not total:
        return []
    ranked = sorted(sizes.items(), key=lambda item: item[1], reverse=True)
    top = [(name, 100 * size / total, LANG_COLORS.get(name, OTHER_COLOR)) for name, size in ranked[:limit]]
    rest = sum(size for _, size in ranked[limit:])
    if rest:
        top.append(("Other", 100 * rest / total, OTHER_COLOR))
    return top


def pct(value: float) -> str:
    return "<1%" if 0 < value < 1 else f"{value:.0f}%"


def pushed_when(pushed: dt.datetime, now: dt.datetime) -> str:
    days = (now.date() - pushed.date()).days
    if days <= 0:
        return "today"
    if days == 1:
        return "yesterday"
    if days < 7:
        return f"{days} days ago"
    return f"{pushed:%b} {pushed.day}" + ("" if pushed.year == now.year else f", {pushed.year}")


def gigabytes(size: int) -> str:
    return f"{size / 1024**3:.1f}"


def load_quotes(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    quotes = [line.strip() for line in lines if line.strip() and not line.startswith("#")]
    if not quotes:
        raise ValueError(f"{path}: no quotes")
    return quotes


def pick_quote(quotes: list[str], day: dt.date) -> str:
    """A different line every day, cycling through the whole file."""
    return quotes[day.toordinal() % len(quotes)]


def load_pixels(path: Path) -> list[str]:
    rows = [line for line in path.read_text(encoding="utf-8").splitlines() if line and not line.startswith("#")]
    if not rows or any(len(row) != len(rows[0]) for row in rows):
        raise ValueError(f"{path}: pixel rows must all have the same length")
    unknown = set("".join(rows)) - set(PIXEL_COLORS) - {"."}
    if unknown:
        raise ValueError(f"{path}: unknown pixel codes {''.join(sorted(unknown))}")
    return rows


# --------------------------------------------------------------------------- svg helpers


def esc(value) -> str:
    return html.escape(str(value), quote=True)


def fit(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def font_css(fonts: Path, *weights: int) -> str:
    faces = []
    for weight in weights:
        data = (fonts / f"jbmono-{'Bold' if weight >= 600 else 'Regular'}.woff2").read_bytes()
        encoded = base64.b64encode(data).decode()
        faces.append(
            f"@font-face{{font-family:'JBMono';font-weight:{weight};"
            f"src:url(data:font/woff2;base64,{encoded}) format('woff2')}}"
        )
    return "".join(faces)


def svg_doc(width: int, height: int, title: str, css: str, body: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img"><title>{esc(title)}</title>'
        f"<style><![CDATA[{css}]]></style>{body}</svg>\n"
    )


def discrete(events: list[tuple[float, float]], total: float) -> tuple[str, str]:
    """keyTimes/values for a calcMode=discrete SMIL animation from (seconds, value) events."""
    times: list[float] = []
    values: list[float] = []
    for when, value in events:
        key = round(when / total, 4)
        if times and key <= times[-1]:
            values[-1] = value
            continue
        times.append(key)
        values.append(value)
    return ";".join(f"{t:g}" for t in times), ";".join(f"{v:g}" for v in values)


def segments(parts: list[tuple[str, str]]) -> str:
    return "".join(f'<tspan fill="{color}">{esc(text)}</tspan>' for text, color in parts)


def level_color(fraction: float) -> str:
    return TEAL if fraction < 0.5 else YELLOW if fraction < 0.8 else CORAL


def bar(x: float, y: float, width: float, height: float, fills, delay: float, clip_id: str) -> str:
    """Rounded progress bar; `fills` is a fraction or a list of (fraction, colour) segments."""
    if isinstance(fills, (int, float)):
        fraction = max(0.0, min(1.0, float(fills)))
        fills = [(fraction, level_color(fraction))]
    rects, cursor = [], x
    for fraction, color in fills:
        size = width * fraction
        if size > 0:
            rects.append(f'<rect x="{cursor:.1f}" y="{y}" width="{size:.1f}" height="{height}" fill="{color}"/>')
            cursor += size
    radius = height / 2
    return (
        f'<clipPath id="{clip_id}"><rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}"/></clipPath>'
        f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="{radius}" fill="{TRACK}"/>'
        f'<g clip-path="url(#{clip_id})"><g class="grow" style="animation-delay:{delay:.2f}s">{"".join(rects)}</g></g>'
    )


def pixel_runs(rows: list[str], wanted) -> list[tuple[int, int, int, str]]:
    """Horizontal runs of equal codes: (x, y, length, code)."""
    runs = []
    for y, row in enumerate(rows):
        x = 0
        while x < len(row):
            end = x
            while end < len(row) and row[end] == row[x]:
                end += 1
            if wanted(row[x]):
                runs.append((x, y, end - x, row[x]))
            x = end
    return runs


def clusters(rows: list[str], code: str) -> list[list[tuple[int, int, int, str]]]:
    """Connected groups of one code (each typing dot), left to right, as 1-pixel runs."""
    cells = {(x, y) for y, row in enumerate(rows) for x, c in enumerate(row) if c == code}
    groups = []
    while cells:
        stack, group = [cells.pop()], []
        while stack:
            x, y = stack.pop()
            group.append((x, y))
            for neighbour in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbour in cells:
                    cells.remove(neighbour)
                    stack.append(neighbour)
        groups.append(sorted(group, key=lambda cell: (cell[1], cell[0])))
    groups.sort(key=lambda group: min(x for x, _ in group))
    return [[(x, y, 1, code) for x, y in group] for group in groups]


def render_pixels(rows: list[str], x0: float, y0: float, size: float) -> str:
    """Botyara, with a blinking antenna LED, "typing" dots and a wink."""

    def rects(runs) -> str:
        return "".join(
            f'<rect x="{x0 + x * size:g}" y="{y0 + y * size:g}" width="{n * size:g}" height="{size:g}"/>'
            for x, y, n, _ in runs
        )

    def layer(runs) -> str:
        by_color = defaultdict(list)
        for run in runs:
            by_color[PIXEL_COLORS[run[3]]].append(run)
        return "".join(f'<g fill="{color}">{rects(group)}</g>' for color, group in by_color.items())

    base = ["".join(UNDER.get(code, code) for code in row) for row in rows]
    parts = [layer(pixel_runs(base, lambda code: code != "."))]
    parts.append(f'<g class="led">{layer(pixel_runs(rows, lambda code: code in "AaH"))}</g>')
    for i, dot in enumerate(clusters(rows, "D")):
        parts.append(
            f'<g class="dot" style="animation-delay:{2 + i * 0.2:.1f}s" fill="{PIXEL_COLORS["D"]}">{rects(dot)}</g>'
        )
    eye = pixel_runs(rows, lambda code: code in "Rr")
    if eye:
        parts.append(f'<g class="eye">{layer(eye)}</g>')
        top, bottom = min(y for _, y, _, _ in eye), max(y for _, y, _, _ in eye)
        left, right = min(x for x, _, _, _ in eye), max(x + n for x, _, n, _ in eye)
        shut = [(left, (top + bottom) // 2, right - left, "R")]
        parts.append(f'<g class="shut" fill="{PIXEL_COLORS["R"]}">{rects(shut)}</g>')
    return f'<g class="bot" shape-rendering="crispEdges">{"".join(parts)}</g>'


# --------------------------------------------------------------------------- cards


def render_typing(lines: list[str], fonts: Path, width: int = 660, height: int = 46, size: int = 24) -> str:
    """Lines typed and erased one after another, with no server behind it."""
    if not lines:
        raise ValueError("profile.json: 'typing' needs at least one line")
    char = size * 0.6  # JetBrains Mono advance width
    width = max(width, round(max(len(line) for line in lines) * char) + 32)
    type_step, hold, erase_step, pause = 0.075, 1.8, 0.03, 0.35
    plan, t = [], 0.0
    for line in lines:
        n = len(line)
        typed = t + n * type_step
        plan.append((line, (width - n * char) / 2, t, typed, typed + hold))
        t = typed + hold + n * erase_step + pause
    total = t
    baseline, top = height / 2 + size * 0.35, height / 2 - size * 0.62

    defs, texts = [], []
    cursor_x: list[tuple[float, float]] = []
    cursor_on: list[tuple[float, float]] = []
    for i, (line, left, start, typed, erase) in enumerate(plan):
        n = len(line)
        widths = [(0.0, 0)]
        widths += [(start + k * type_step, round(k * char, 1)) for k in range(1, n + 1)]
        widths += [(erase + k * erase_step, round((n - k) * char, 1)) for k in range(1, n + 1)]
        key_times, values = discrete(widths, total)
        defs.append(
            f'<clipPath id="line{i}"><rect x="{left:.1f}" y="0" width="0" height="{height}">'
            f'<animate attributeName="width" values="{values}" keyTimes="{key_times}" calcMode="discrete" '
            f'dur="{total:.3f}s" repeatCount="indefinite"/></rect></clipPath>'
        )
        texts.append(f'<text x="{left:.1f}" y="{baseline:.1f}" clip-path="url(#line{i})">{esc(line)}</text>')
        cursor_x.append((start, round(left + 1, 1)))
        cursor_x += [(start + k * type_step, round(left + k * char + 1, 1)) for k in range(1, n + 1)]
        cursor_x += [(erase + k * erase_step, round(left + (n - k) * char + 1, 1)) for k in range(1, n + 1)]
        cursor_on.append((start, 1))
        blink, visible = typed, 1
        while blink < erase:
            cursor_on.append((blink, visible))
            blink, visible = blink + 0.45, 1 - visible
        cursor_on.append((erase, 1))

    x_times, x_values = discrete(cursor_x, total)
    on_times, on_values = discrete(cursor_on, total)
    cursor = (
        f'<rect y="{top:.1f}" width="3" height="{size * 1.2:.1f}" rx="1.5" fill="{CORAL}">'
        f'<animate attributeName="x" values="{x_values}" keyTimes="{x_times}" calcMode="discrete" '
        f'dur="{total:.3f}s" repeatCount="indefinite"/>'
        f'<animate attributeName="opacity" values="{on_values}" keyTimes="{on_times}" calcMode="discrete" '
        f'dur="{total:.3f}s" repeatCount="indefinite"/></rect>'
    )
    css = font_css(fonts, 400) + f"text{{font-family:{MONO};font-size:{size}px;fill:{PURPLE}}}"
    return svg_doc(width, height, " · ".join(lines), css, f"<defs>{''.join(defs)}</defs>{''.join(texts)}{cursor}")


def render_wave(size: int = 40) -> str:
    """👋 that actually waves, rotating around the wrist."""
    cx, cy = size * 0.66, size * 0.86
    angles = [0, 16, -8, 16, -4, 12, 0, 0]
    values = ";".join(f"{a} {cx:g} {cy:g}" for a in angles)
    body = (
        f'<text x="{size / 2:g}" y="{size * 0.82:g}" font-size="{size * 0.74:g}" text-anchor="middle" '
        f'font-family="{esc(EMOJI)}">👋<animateTransform attributeName="transform" type="rotate" '
        f'values="{values}" keyTimes="0;.08;.16;.24;.32;.4;.48;1" dur="2.6s" repeatCount="indefinite"/></text>'
    )
    return svg_doc(size, size, "waving hand", "", body)


def render_neofetch(
    cfg: dict, snap: dict, system: dict, pixels: list[str], fonts: Path, now: dt.datetime, live: bool
) -> str:
    """neofetch for a human: live GitHub stats plus the runner's CPU/RAM/swap."""
    user = snap["user"]
    login = user["login"]
    name = cfg.get("name") or user.get("name") or login
    handle = f"{name.lower()}@{login}"
    info = cfg.get("neofetch", {})
    own = own_repos(snap["repos"], login)
    width, font, step = 860, 15, 24
    char = font * 0.6
    label_x, value_x = 296, 400
    text_limit = int((width - 24 - value_x) / char)
    bar_width = 120
    bar_text_limit = int((width - 24 - value_x - bar_width - 12) / char)

    rows: list[dict] = []

    def add(label: str, parts, icon: str | None = None, fills=None) -> None:
        if isinstance(parts, str):
            parts = [(parts, TEXT)]
        rows.append({"label": label, "parts": parts, "icon": icon, "fills": fills})

    add("OS", fit(info.get("os", "Human"), text_limit))
    add("Host", f"github.com/{login}")
    add("Uptime", human_uptime(parse_time(user["created_at"]), now))
    packages = [f"{user['public_repos']} public repos"]
    stars = [repo.get("stars") for repo in own]
    if stars and None not in stars:
        packages.append(f"{sum(stars)} stars")
    if user.get("followers") is not None:
        packages.append(f"{user['followers']} followers")
    add("Packages", fit(" · ".join(packages), text_limit))
    if info.get("shell"):
        add("Shell", fit(info["shell"], text_limit))
    if info.get("stack"):
        add("Stack", fit(info["stack"], text_limit))
    if own:
        latest = max(own, key=lambda repo: repo["pushed_at"] or "")
        when = f" · pushed {pushed_when(parse_time(latest['pushed_at']), now)}" if latest["pushed_at"] else ""
        add("Now", [(fit(latest["name"], text_limit - len(when)), TEAL), (when, MUTED)])
    if snap.get("contributions_last_year") is not None:
        add("Activity", f"{snap['contributions_last_year']} contributions in the last year")
    languages = top_languages(snap.get("languages", {}))
    if languages:
        legend = " · ".join(f"{lang} {pct(share)}" for lang, share, _ in languages if lang != "Other")
        add("Languages", fit(legend, bar_text_limit), fills=[(share / 100, color) for _, share, color in languages])
    if info.get("bots"):
        add("Bots", fit(info["bots"], text_limit))

    cpu = system.get("cpu_percent")
    model = system.get("cpu_model") or "CPU"
    count = f" ×{system['cpu_count']}" if system.get("cpu_count") else ""
    add(
        "CPU",
        fit(f"{cpu:.0f}% · {model}{count}", bar_text_limit) if cpu is not None else "n/a",
        icon="🖥️",
        fills=cpu / 100 if cpu is not None else 0,
    )
    if system.get("mem_total"):
        used, total = system["mem_used"], system["mem_total"]
        add("RAM", f"{gigabytes(used)} / {gigabytes(total)} GB", icon="💾", fills=used / total)
    else:
        add("RAM", "n/a", icon="💾", fills=0)
    if system.get("swap_total"):
        used, total = system["swap_used"], system["swap_total"]
        add("SWAP", f"{gigabytes(used)} / {gigabytes(total)} GB", icon="🗄️", fills=used / total)
    else:
        add("SWAP", "off", icon="🗄️", fills=0)

    header_y, first_y = 102, 150
    logo_bottom = 92 + 6 * len(pixels)
    swatch_y = first_y + len(rows) * step
    height = max(swatch_y + 58, logo_bottom + 108)
    body = [
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="{BG}" stroke="{BORDER}"/>',
        f'<path d="M0.5 36V14.5a14 14 0 0 1 14-14h{width - 29}a14 14 0 0 1 14 14V36z" fill="{PANEL}"/>',
        f'<line x1="0.5" y1="36" x2="{width - 0.5}" y2="36" stroke="{BORDER}"/>',
        f'<circle cx="22" cy="18" r="6" fill="{CORAL}"/><circle cx="42" cy="18" r="6" fill="{YELLOW}"/>'
        f'<circle cx="62" cy="18" r="6" fill="{TEAL}"/>',
        f'<text x="{width / 2}" y="22.5" text-anchor="middle" class="title">{esc(handle)}: ~ — neofetch</text>',
    ]
    prompt = [(handle, TEAL), (":", MUTED), ("~", PURPLE), ("$ ", MUTED)]
    prompt_width = sum(len(text) for text, _ in prompt) * char
    command_x = 24 + prompt_width
    command = "neofetch"
    typing = [(0.0, 0)] + [(k * 0.07, round(k * char, 1)) for k in range(1, len(command) + 1)]
    key_times, values = discrete(typing, 0.7)
    body.append(f'<text x="24" y="68">{segments(prompt)}</text>')
    body.append(
        f'<clipPath id="cmd"><rect x="{command_x:.1f}" y="50" width="0" height="26">'
        f'<animate attributeName="width" values="{values}" keyTimes="{key_times}" calcMode="discrete" '
        f'begin="0.25s" dur="0.7s" fill="freeze"/></rect></clipPath>'
        f'<text x="{command_x:.1f}" y="68" clip-path="url(#cmd)">{command}</text>'
    )
    body.append(render_pixels(pixels, 28, 92, 6))
    body.append(
        f'<g class="in" style="animation-delay:1.2s">'
        f'<text x="148" y="{logo_bottom + 30}" text-anchor="middle" class="caption">Botyara v1.0</text>'
        f'<text x="148" y="{logo_bottom + 50}" text-anchor="middle" class="small">'
        "commenting from the back row</text></g>"
    )
    header = segments([(name.lower(), TEAL), ("@", MUTED), (login, PURPLE)])
    body.append(
        f'<g class="in" style="animation-delay:0.95s">'
        f'<text x="{label_x}" y="{header_y}" class="head">{header}</text>'
        f'<text x="{label_x}" y="{header_y + 22}" fill="{MUTED}">{"─" * len(handle)}</text></g>'
    )
    y = first_y
    for i, row in enumerate(rows):
        delay = 1.05 + i * 0.06
        label_start = label_x
        cells = [f'<g class="in" style="animation-delay:{delay:.2f}s">']
        if row["icon"]:
            cells.append(f'<text x="{label_x}" y="{y}" class="emoji">{row["icon"]}</text>')
            label_start += 24
        cells.append(f'<text x="{label_start}" y="{y}" class="label">{esc(row["label"])}</text>')
        text_x = value_x
        if row["fills"] is not None:
            cells.append(bar(value_x, y - 10, bar_width, 10, row["fills"], delay + 0.15, f"bar{i}"))
            text_x += bar_width + 12
        cells.append(f'<text x="{text_x}" y="{y}">{segments(row["parts"])}</text></g>')
        body.append("".join(cells))
        y += step
    palette = [CORAL, YELLOW, TEAL, PURPLE, "#b9a8ff", "#ff9ecf", "#6cb6ff", TEXT]
    swatches = "".join(
        f'<rect x="{label_x + i * 30}" y="{y - 8}" width="26" height="14" rx="3" fill="{color}"/>'
        for i, color in enumerate(palette)
    )
    body.append(f'<g class="in" style="animation-delay:{1.05 + len(rows) * 0.06:.2f}s">{swatches}</g>')
    where = "GitHub Actions runner" if os.environ.get("GITHUB_ACTIONS") == "true" else "local machine"
    source = "live GitHub stats" if live else f"snapshot of {snap.get('fetched_at', '?')[:10]}"
    body.append(
        f'<g class="in" style="animation-delay:{1.2 + len(rows) * 0.06:.2f}s">'
        f'<text x="24" y="{height - 22}">{segments(prompt)}</text>'
        f'<rect class="cursor" x="{command_x:.1f}" y="{height - 35}" width="{char:.0f}" height="17" fill="{TEAL}"/>'
        f'<text x="{width - 24}" y="{height - 22}" text-anchor="end" class="small">'
        f"{esc(source)} · drawn {now:%Y-%m-%d %H:%M} UTC on a {where}</text></g>"
    )
    css = (
        font_css(fonts, 400, 700)
        + f"text{{font-family:{MONO};font-size:{font}px;fill:{TEXT}}}"
        + f".title{{font-size:12.5px;fill:{MUTED}}}.small{{font-size:11.5px;fill:{MUTED}}}"
        + f".caption{{font-size:13px;font-weight:700;fill:{TEAL}}}.head{{font-weight:700}}"
        + f".label{{font-weight:700;fill:{PURPLE}}}.emoji{{font-family:{EMOJI};font-size:15px}}"
        + ".in{animation:in .45s ease-out both}@keyframes in{from{opacity:0;transform:translateX(-8px)}}"
        + ".grow{transform-box:fill-box;transform-origin:0 50%;animation:grow 1s cubic-bezier(.2,.8,.2,1) both}"
        + "@keyframes grow{from{transform:scaleX(0)}}"
        + ".bot{animation:rise .6s ease-out .8s both}@keyframes rise{from{opacity:0;transform:translateY(6px)}}"
        + ".led{animation:led 2.4s ease-in-out 2s infinite}@keyframes led{50%{opacity:.3}}"
        + ".dot{animation:dot 1.2s ease-in-out infinite}@keyframes dot{0%,100%{opacity:.3}40%{opacity:1}}"
        + ".eye{animation:eye 6s steps(1,end) 3s infinite}@keyframes eye{92%{opacity:0}96%{opacity:1}}"
        + ".shut{opacity:0;animation:shut 6s steps(1,end) 3s infinite}@keyframes shut{92%{opacity:1}96%{opacity:0}}"
        + ".cursor{animation:blink 1.1s steps(1,end) infinite}@keyframes blink{50%{opacity:0}}"
        + CALM
    )
    title = f"neofetch for {login}: {user['public_repos']} public repos"
    return svg_doc(width, height, title, css, "".join(body))


def render_says(quote: str, avatar: bytes, now: dt.datetime, width: int = 860) -> str:
    """Botyara's comment of the day, as a Discord message."""
    lines = textwrap.wrap(quote, 84) or [""]
    top, first, step = 44, 104, 23
    last = first + (len(lines) - 1) * step
    chip_y = last + 14
    height = chip_y + 28 + 18
    image = base64.b64encode(avatar).decode()
    laughs = 3 + int(hashlib.sha256(now.strftime("%Y-%m-%d").encode()).hexdigest(), 16) % 9
    message = "".join(f'<tspan x="84" y="{first + i * step}">{esc(line)}</tspan>' for i, line in enumerate(lines))
    dots = "".join(
        f'<circle cx="{90 + i * 10}" cy="{first - 5}" r="3.2" fill="{MUTED}" class="bounce" '
        f'style="animation-delay:{i * 0.15:.2f}s"/>'
        for i in range(3)
    )
    body = (
        f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="{BG}" stroke="{BORDER}"/>'
        f'<text x="24" y="27" class="channel"><tspan fill="{MUTED}"># </tspan>back-row</text>'
        f'<text x="{width - 24}" y="27" text-anchor="end" class="time">{now:%d.%m.%Y}</text>'
        f'<line x1="0.5" y1="{top}" x2="{width - 0.5}" y2="{top}" stroke="{BORDER}"/>'
        f'<clipPath id="avatar"><circle cx="46" cy="{top + 34}" r="22"/></clipPath>'
        f'<image href="data:image/png;base64,{image}" x="24" y="{top + 12}" width="44" height="44" '
        f'clip-path="url(#avatar)"/>'
        f'<text x="84" y="{top + 30}" class="name">Botyara</text>'
        f'<rect x="156" y="{top + 17}" width="30" height="16" rx="4" fill="#5865f2"/>'
        f'<text x="171" y="{top + 29}" text-anchor="middle" class="tag">BOT</text>'
        f'<text x="196" y="{top + 29.5}" class="time">Today at {now:%H:%M}</text>'
        f'<g class="typing">{dots}<text x="124" y="{first}" class="time">Botyara is typing…</text></g>'
        f'<g class="message"><text class="text">{message}</text>'
        f'<rect x="84" y="{chip_y}" width="58" height="26" rx="8" fill="{PANEL}" stroke="{PURPLE}"/>'
        f'<text x="94" y="{chip_y + 18}" class="chip"><tspan class="emoji">😂</tspan> {laughs}</text></g>'
    )
    css = (
        f"text{{font-family:{SANS};fill:{TEXT}}}"
        f".channel{{font-size:14px;font-weight:700}}.name{{font-size:16px;font-weight:700;fill:{TEAL}}}"
        f".tag{{font-size:10px;font-weight:700;fill:#fff}}.time{{font-size:12.5px;fill:{MUTED}}}"
        f".text{{font-size:15.5px}}.chip{{font-size:13px;font-weight:700;fill:{TEXT}}}"
        f".emoji{{font-family:{EMOJI}}}"
        ".typing{opacity:0;animation:typing 1.9s both}@keyframes typing{0%,88%{opacity:1}100%{opacity:0}}"
        ".bounce{animation:bounce .9s ease-in-out infinite}@keyframes bounce{0%,60%,100%{transform:none}"
        "30%{transform:translateY(-4px)}}"
        ".message{animation:message .45s ease-out 1.8s both}"
        "@keyframes message{from{opacity:0;transform:translateY(4px)}}" + CALM
    )
    return svg_doc(width, height, f"Botyara says: {quote}", css, body)


def render_snake_placeholder(dark: bool) -> str:
    """Stand-in until the first workflow run draws the real contribution snake."""
    cols, rows, cell, gap = 53, 7, 12, 3
    width, height = cols * (cell + gap) + 17, rows * (cell + gap) + 60
    levels = (
        ["#161b22", "#2e2a5c", "#4b3aa8", "#7053e8", "#9d86ff"]
        if dark
        else ["#ebedf0", "#d9d0ff", "#b3a1ff", "#8a6dff", "#5b3fd9"]
    )
    squares = "".join(
        f'<rect x="{10 + x * (cell + gap)}" y="{10 + y * (cell + gap)}" width="{cell}" height="{cell}" rx="2.5" '
        f'fill="{levels[(x * 7 + y * 3 + (x * y) % 5) % 5 if (x + y) % 3 else 0]}"/>'
        for x in range(cols)
        for y in range(rows)
    )
    color = MUTED if dark else "#57606a"
    body = (
        f'{squares}<text x="{width / 2}" y="{height - 16}" text-anchor="middle" '
        f'fill="{color}">the snake hatches after the first workflow run</text>'
    )
    css = f"text{{font-family:{SANS};font-size:13px}}"
    return svg_doc(width, height, "contribution snake placeholder", css, body)


# --------------------------------------------------------------------------- main


def build(
    root: Path,
    offline: bool = False,
    login: str | None = None,
    now: dt.datetime | None = None,
    fetch=fetch_github,
    system=system_stats,
) -> dict:
    """Render every card under `root`. Returns the snapshot that was used."""
    data, fonts, assets = root / "data", root / "fonts", root / "assets"
    out = assets / "generated"
    cfg = json.loads((data / "profile.json").read_text(encoding="utf-8"))
    login = login or cfg["user"]
    now = now or utcnow()
    snapshot_path = data / "snapshot.json"
    snap, live = None, False
    if not offline:
        try:
            snap = fetch(login, os.environ.get("GITHUB_TOKEN"), now=now)
            live = True
        except Exception as error:  # any API trouble: fall back to the last good data
            warn(f"GitHub API failed, rendering from the snapshot instead: {error}")
    if snap is None:
        snap = json.loads(snapshot_path.read_text(encoding="utf-8"))
    else:
        snapshot_path.write_text(json.dumps(snap, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    out.mkdir(parents=True, exist_ok=True)
    cards = {
        assets / "typing.svg": render_typing(cfg["typing"], fonts),
        assets / "wave.svg": render_wave(),
        out / "neofetch.svg": render_neofetch(cfg, snap, system(), load_pixels(data / "botyara.txt"), fonts, now, live),
        out / "botyara-says.svg": render_says(
            pick_quote(load_quotes(data / "quotes.txt"), now.date()),
            (assets / "botyara-avatar.png").read_bytes(),
            now,
        ),
    }
    for theme in ("light", "dark"):
        snake = out / f"snake-{theme}.svg"
        if not snake.exists():
            cards[snake] = render_snake_placeholder(theme == "dark")
    for path, content in cards.items():
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(root)} ({len(content.encode()) / 1024:.1f} KiB)")
    return snap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Render the generated profile cards.")
    parser.add_argument("--offline", action="store_true", help="render from data/snapshot.json, no API calls")
    parser.add_argument("--user", help="GitHub login (default: data/profile.json)")
    args = parser.parse_args(argv)
    build(ROOT, offline=args.offline, login=args.user)
    return 0


if __name__ == "__main__":
    sys.exit(main())
