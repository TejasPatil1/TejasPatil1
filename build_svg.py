#!/usr/bin/env python3
"""Build profile.svg from ascii.txt + config.json + stats.json (no dependencies)."""
import json
import sys
from datetime import date
from xml.sax.saxutils import escape,quoteattr

W, H, LINE, PAD = 985, 530, 20, 15


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def uptime(birth_iso, today=None):
    today = today or date.today()
    b = date.fromisoformat(birth_iso)
    y, m, d = today.year - b.year, today.month - b.month, today.day - b.day
    if d < 0:
        m -= 1
        # days in the month preceding `today`
        pm_year, pm = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
        nxt = date(pm_year + (pm == 12), pm % 12 + 1, 1)
        d += (nxt - date(pm_year, pm, 1)).days
    if m < 0:
        y, m = y - 1, m + 12
    s = lambda n, w: f"{n} {w}{'' if n == 1 else 's'}"
    return f"{s(y, 'year')}, {s(m, 'month')}, {s(d, 'day')}"


def span(text, cls=None):
    t = escape(text)
    return f'<tspan class="{cls}">{t}</tspan>' if cls else f"<tspan>{t}</tspan>"


def key_spans(key):
    """'Languages.Real' -> orange 'Languages' + '.' + orange 'Real' (as in the reference)."""
    out = []
    for i, part in enumerate(key.split(".")):
        if i:
            out.append(span("."))
        out.append(span(part, "key"))
    return "".join(out)


def row(key, value, width, plain_value=None, link=None):
    """Render a terminal-style row with optional masked hyperlink."""
    value = str(value)
    used = 2 + len(key) + 1 + len(value)
    dots = max(width - used - 2, 2)

    value_markup = span(value, "value")

    if link:
        value_markup = (
            f'<a href={quoteattr(link)}>'
            f'{value_markup}'
            f'</a>'
        )

    return (
        span(". ", "cc")
        + key_spans(key)
        + span(":")
        + span(" " + "." * dots + " ", "cc")
        + value_markup
    )


def header(title, width):
    return span(title) + span(" " + "-" * (width - len(title) - 1))


def cell(key, value, width, extra=None):
    """A stats cell of fixed char width; optional (label, value) shown in braces."""
    value = f"{value:,}" if isinstance(value, int) else str(value)
    extra_len = 0
    extra_markup = ""
    if extra:
        label, ev = extra
        ev = f"{ev:,}"
        extra_len = len(f" {{{label}: {ev}}}")
        extra_markup = (span(" {") + span(label, "key") + span(": ") + span(ev, "value") + span("}"))
    dots = max(width - len(key) - 1 - 2 - len(value) - extra_len, 2)
    return (key_spans(key) + span(":") + span(" " + "." * dots + " ", "cc") +
            span(value, "value") + extra_markup)


def main():
    cfg, stats = load("config.json"), load("stats.json")
    ascii_lines = open("ascii.txt", encoding="utf-8").read().rstrip("\n").split("\n")
    px, cw = cfg["panel_x"], cfg["panel_chars"]

    # ---- left: ASCII portrait ------------------------------------------------
    art = []
    for i, l in enumerate(ascii_lines):
        y = 30 + i * LINE
        art.append(f'<tspan x="{PAD}" y="{y}">{escape(l)}</tspan>')

    # ---- right: terminal panel ----------------------------------------------
    rows, y = [], 30

    def add(markup):
        nonlocal y
        rows.append(f'<tspan x="{px}" y="{y}">{markup}</tspan>')
        y += LINE

    add(header(cfg["title"], cw))
    for item in cfg["info"]:
        if not item:
            add(span(". ", "cc"))
        elif item[0] == "@uptime":
            add(row("Uptime", uptime(cfg["birthdate"]), cw))
        else:
            add(row(item[0], item[1], cw))

    y += LINE  # blank line
    add(header("- " + cfg["contact_title"], cw))
    for item in cfg["contact"]:
     if isinstance(item, dict):
        add(row(
            item["label"],
            item["display"],
            cw,
            link=item.get("url")
        ))
     else:
        k, v = item
        add(row(k, v, cw))

    y += LINE
    add(header("- " + cfg["stats_title"], cw))
    f = lambda n: f"{n:,}"
    left, right = 32, cw - 2 - 3 - 32  # ". " prefix and " | " separator
    add(span(". ", "cc") + cell("Repos", stats["repos"], left, ("Contributed", stats["contributed"]))
        + span(" | ") + cell("Stars", stats["stars"], right))
    add(span(". ", "cc") + cell("Commits", stats["commits"], left)
        + span(" | ") + cell("Followers", stats["followers"], right))
    loc = (span(". ", "cc") + key_spans("Lines of Code on GitHub") + span(":") + span(" ", "cc") +
           span(f(stats["loc_total"]), "value") + span(" ( ") +
           span(f(stats["loc_add"]), "addColor") + span("++", "addColor") + span(", ") +
           span(f(stats["loc_del"]), "delColor") + span("--", "delColor") + span(" )"))
    add(loc)

    svg = f'''<?xml version='1.0' encoding='UTF-8'?>
<svg xmlns="http://www.w3.org/2000/svg" font-family="ConsolasFallback,Consolas,'DejaVu Sans Mono',monospace" width="{W}px" height="{H}px" viewBox="0 0 {W} {H}" font-size="16px">
<style>
@font-face {{
src: local('Consolas'), local('Consolas Bold');
font-family: 'ConsolasFallback';
font-display: swap;
-webkit-size-adjust: 109%;
size-adjust: 109%;
}}
.key {{fill: #ffa657;}}
.value {{fill: #a5d6ff;}}
.addColor {{fill: #3fb950;}}
.delColor {{fill: #f85149;}}
.cc {{fill: #616e7f;}}
text, tspan {{white-space: pre;}}
</style>
<rect width="{W}px" height="{H}px" fill="#161b22" rx="15"/>
<text x="{PAD}" y="30" fill="#c9d1d9" class="ascii">
{chr(10).join(art)}
</text>
<text x="{px}" y="30" fill="#c9d1d9">
{chr(10).join(rows)}
</text>
</svg>
'''
    out = sys.argv[1] if len(sys.argv) > 1 else "profile.svg"
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(svg)
    print(f"Wrote {out} ({len(svg.encode()) / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
