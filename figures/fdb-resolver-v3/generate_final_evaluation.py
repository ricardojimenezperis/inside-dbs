#!/usr/bin/env python3
"""Generate Resolver v3 final-correctness and evaluation figures."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "content" / "systems" / "fdb-resolver-v3"
REGULAR = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

BG = "#ffffff"
INK = "#17233d"
MUTED = "#5f6b80"
GRID = "#bdc6d5"
LIGHT = "#c3cad5"
BLUE = "#2e60aa"
GREEN = "#2f7d32"
ORANGE = "#ef720d"
BOX = "#f7f8fa"
RED = "#b42318"


def font(size: int, bold: bool = False):
    return ImageFont.truetype(BOLD if bold else REGULAR, size)


def text(draw, xy, value, size, *, fill=INK, bold=False, anchor=None):
    draw.text(xy, value, font=font(size, bold), fill=fill, anchor=anchor)


def dashed(draw, xy, fill=GRID, width=2, dash=8, gap=9):
    x1, y1, x2, y2 = xy
    if y1 == y2:
        x = x1
        while x < x2:
            draw.line((x, y1, min(x + dash, x2), y2), fill=fill, width=width)
            x += dash + gap
    else:
        y = y1
        while y < y2:
            draw.line((x1, y, x2, min(y + dash, y2)), fill=fill, width=width)
            y += dash + gap


def rounded_bar(draw, xy, fill, radius=5):
    draw.rounded_rectangle(xy, radius=radius, fill=fill)


def arrow(draw, start, end, *, fill=INK, width=5):
    draw.line((*start, *end), fill=fill, width=width)
    x, y = end
    if end[0] >= start[0]:
        draw.polygon([(x, y), (x - 18, y - 11), (x - 18, y + 11)], fill=fill)
    else:
        draw.polygon([(x, y), (x + 18, y - 11), (x + 18, y + 11)], fill=fill)


def card(draw, xy, title, body, *, accent=BLUE, body_size=25):
    x1, y1, x2, y2 = xy
    draw.rounded_rectangle(xy, radius=22, fill=BOX, outline=accent, width=4)
    draw.rounded_rectangle((x1, y1, x2, y1 + 78), radius=22, fill=accent)
    draw.rectangle((x1, y1 + 45, x2, y1 + 78), fill=accent)
    text(draw, (x1 + 28, y1 + 21), title, 29, bold=True, fill=BG)
    wrapped(draw, (x1 + 28, y1 + 110), body, body_size, x2 - x1 - 56, fill=INK, line_gap=10)


def wrapped(draw, xy, value, size, width, *, fill=MUTED, bold=False, line_gap=7):
    words = value.split()
    lines = []
    line = ""
    f = font(size, bold)
    for word in words:
        candidate = word if not line else f"{line} {word}"
        if draw.textlength(candidate, font=f) <= width:
            line = candidate
        else:
            lines.append(line)
            line = word
    if line:
        lines.append(line)
    x, y = xy
    for item in lines:
        draw.text((x, y), item, font=f, fill=fill)
        y += size + line_gap
    return y


def evolution():
    image = Image.new("RGB", (2560, 1400), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (80, 55), "The same retained history at progressively lower cost", 44, bold=True)
    text(
        draw,
        (80, 118),
        "Final-session time relative to v1 on the Intel Core Ultra 9 285K, same work and decisions. Lower is better.",
        28,
        fill=MUTED,
    )

    labels = [
        "conflictset points",
        "conflictset ranges",
        "integrated points",
        "integrated ranges",
        "skiplisttest, 16 B",
        "skiplisttest, 32 B",
    ]
    v3_v1 = [0.4977, 1.1996, 0.3786, 0.6019, 0.4216, 0.4274]
    v3_v2 = [0.7198, 1.0918, 0.7372, 0.8849, 0.6892, 0.6754]
    v2_v1 = [a / b for a, b in zip(v3_v1, v3_v2)]

    legend_y = 190
    for x, color, label in [(180, LIGHT, "v1"), (365, BLUE, "v2"), (550, ORANGE, "final v3")]:
        draw.rectangle((x, legend_y, x + 28, legend_y + 28), fill=color)
        text(draw, (x + 42, legend_y - 1), label, 25, fill=MUTED)

    left, right, top, bottom = 150, 2460, 255, 1005
    ymax = 1.30
    for tick in [0.25, 0.50, 0.75, 1.00, 1.25]:
        y = bottom - (tick / ymax) * (bottom - top)
        if tick == 1.0:
            draw.line((left, y, right, y), fill="#7c879b", width=3)
        else:
            dashed(draw, (left, y, right, y))
        text(draw, (left - 20, y), f"{tick:.2f}×", 22, fill=MUTED, anchor="rm")
    text(draw, (right, top - 55), "lower is better", 22, fill=MUTED, anchor="ra")

    group_w = (right - left) / len(labels)
    bar_w = 54
    for i, label in enumerate(labels):
        cx = left + group_w * (i + 0.5)
        values = [1.0, v2_v1[i], v3_v1[i]]
        colors = [LIGHT, BLUE, ORANGE]
        for j, (value, color) in enumerate(zip(values, colors)):
            x1 = cx + (j - 1) * 68 - bar_w / 2
            y1 = bottom - (value / ymax) * (bottom - top)
            rounded_bar(draw, (x1, y1, x1 + bar_w, bottom), color)
            text(draw, (x1 + bar_w / 2, y1 - 10), f"{value:.2f}", 22, bold=j == 2, anchor="ms")
        text(draw, (cx, bottom + 24), label, 22, bold=True, anchor="ma")

    box = (120, 1120, 2440, 1345)
    draw.rounded_rectangle(box, radius=20, fill=BOX, outline=ORANGE, width=3)
    text(draw, (155, 1150), "What the final paired session shows", 28, bold=True)
    wrapped(
        draw,
        (155, 1202),
        "V2 removes repeated read-side traversal work; final v3 removes the second write descent and overlaps write-path memory latency. "
        "The short final session contains all four arms, so every bar is derived from one paired protocol. The long trace is omitted here because the final campaign compares only FDB and v3.",
        24,
        2210,
    )
    image.save(OUT / "fig-v3-evolution.png", optimize=True)


def vs_fdb():
    image = Image.new("RGB", (2560, 1432), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (80, 55), "2.20× the history; final v3 cost varies by workload", 44, bold=True)
    text(
        draw,
        (80, 118),
        "Final v3 time relative to FoundationDB in paired sessions; the vertical line marks equal cost. Lower is better.",
        28,
        fill=MUTED,
    )

    rows = ["conflictset points", "conflictset ranges", "integrated points", "integrated ranges", "skiplisttest", "long trace"]
    intel = [0.8078, 1.1238, 0.9989, 0.9154, (0.7354, 0.9103), 0.7723]
    amd = [1.0515, 1.2867, 1.3237, 0.9899, (0.9531, 1.0099), None]
    panels = [
        ("Intel Core Ultra 9 285K", 180, 1290, intel),
        ("AMD Ryzen 7 7700", 1450, 2470, amd),
    ]
    xmin, xmax = 0.6, 1.4
    chart_top, chart_bottom = 340, 1010
    row_gap = (chart_bottom - chart_top) / len(rows)

    for title, left, right, values in panels:
        label_width = 365 if left < 1000 else 0
        plot_left = left + label_width
        text(draw, ((plot_left + right) / 2, 190), title, 30, bold=True, anchor="ma")
        for tick in [0.6, 0.8, 1.0, 1.2, 1.4]:
            x = plot_left + (tick - xmin) / (xmax - xmin) * (right - plot_left)
            if tick == 1.0:
                draw.line((x, 285, x, chart_bottom + 10), fill=INK, width=3)
                text(draw, (x, 260), "FoundationDB = 1.0", 21, fill=MUTED, anchor="ms")
            else:
                dashed(draw, (x, 285, x, chart_bottom + 10))
            text(draw, (x, chart_bottom + 32), f"{tick:.1f}×", 22, fill=MUTED, anchor="ma")

        for i, (label, value) in enumerate(zip(rows, values)):
            y = chart_top + row_gap * (i + 0.5)
            if left < 1000:
                text(draw, (plot_left - 35, y), label, 24, bold=True, anchor="rm")
            if value is None:
                text(draw, (plot_left + 16, y), "N/A — one functional pair; no ratio inferred", 21, fill=MUTED, anchor="lm")
                continue
            if isinstance(value, tuple):
                lo, hi = value
                x1 = plot_left + (lo - xmin) / (xmax - xmin) * (right - plot_left)
                x2 = plot_left + (hi - xmin) / (xmax - xmin) * (right - plot_left)
                rounded_bar(draw, (x1, y - 23, x2, y + 23), GREEN if hi <= 1 else "#52945a")
                text(draw, (x1 - 14, y), f"{lo:.2f}–{hi:.2f}×", 22, bold=True, anchor="rm")
                continue
            x0 = plot_left + (1.0 - xmin) / (xmax - xmin) * (right - plot_left)
            x1 = plot_left + (value - xmin) / (xmax - xmin) * (right - plot_left)
            color = GREEN if value < 1 else ORANGE
            rounded_bar(draw, (min(x0, x1), y - 23, max(x0, x1), y + 23), color)
            if value < 1:
                text(draw, (x1 - 15, y), f"{value:.2f}×", 22, bold=True, anchor="rm")
            else:
                text(draw, (x1 + 15, y), f"{value:.2f}×", 22, bold=True, anchor="lm")

    box = (120, 1135, 2440, 1375)
    draw.rounded_rectangle(box, radius=20, fill=BOX, outline=ORANGE, width=3)
    text(draw, (155, 1165), "Final sessions, not a universal speedup claim", 28, bold=True)
    wrapped(
        draw,
        (155, 1217),
        "On Intel final v3 is faster in conflictset points, integrated ranges, all seven skiplist layouts and the long trace; integrated points is level and conflictset ranges is slower. "
        "On AMD it is within about ±5% of FDB in skiplisttest and integrated ranges, and slower in conflictset points, conflictset ranges and integrated points. "
        "The AMD long trace reproduces decisions and retention with one pair, so its two observed times are published without inferring a performance ratio.",
        24,
        2210,
    )
    image.save(OUT / "fig-v3-vs-fdb.png", optimize=True)


def generation_spaces():
    image = Image.new("RGB", (2560, 1500), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (80, 55), "One pool, two disjoint generation spaces", 44, bold=True)
    text(
        draw,
        (80, 118),
        "The block address may be reused across roles; the generation value cannot be mistaken for the other role.",
        28,
        fill=MUTED,
    )

    card(
        draw,
        (100, 230, 780, 610),
        "Node block",
        "Leaf and internal nodes receive odd generations: 1, 3, 5, …\n\nA deferred cleanup record stores the node address and its generation.",
        accent=BLUE,
    )
    card(
        draw,
        (940, 230, 1620, 610),
        "Shared free block",
        "Release clears the old header and returns the same physical block to the pool. Its next allocation may have a different role.",
        accent=MUTED,
    )
    card(
        draw,
        (1780, 230, 2460, 610),
        "Key block",
        "Key blocks receive even generations: 2, 4, 6, …\n\nA RangeRef stores the first-block address, offset, lengths and generation.",
        accent=ORANGE,
    )
    arrow(draw, (790, 420), (920, 420), fill=MUTED)
    arrow(draw, (1630, 420), (1760, 420), fill=MUTED)

    text(draw, (1280, 690), "Validation never relies on the address alone", 34, bold=True, anchor="ma")
    card(
        draw,
        (100, 765, 1190, 1170),
        "Logical and key-reference checks",
        "1. Compare the entry commit version with the reclamation cutoff.\n\n2. Compare the RangeRef generation with the last reclaimed key generation before reading key bytes.\n\nA reclaimed key reference is rejected without dereferencing its block.",
        accent=GREEN,
        body_size=24,
    )
    card(
        draw,
        (1370, 765, 2460, 1170),
        "Node and cross-role checks",
        "A deferred node record is accepted only when its saved generation still matches. If that address now holds keys, its even generation cannot equal the saved odd node generation.\n\nThe same separation prevents a key block reused as a node from reviving an old key reference.",
        accent=BLUE,
        body_size=24,
    )

    draw.rounded_rectangle((100, 1260, 2460, 1425), radius=20, fill="#fff7ed", outline=ORANGE, width=3)
    text(draw, (135, 1292), "Final-v3 invariant", 29, bold=True, fill=ORANGE)
    wrapped(
        draw,
        (135, 1340),
        "Node generations are odd and key-block generations are even. Reusing the same physical block across roles therefore cannot produce a false generation match.",
        25,
        2250,
        fill=INK,
    )
    image.save(OUT / "fig-v3-generation.png", optimize=True)


def destination_validation():
    image = Image.new("RGB", (2560, 1680), BG)
    draw = ImageDraw.Draw(image)
    text(draw, (80, 55), "A prepared write destination is a checked hint", 44, bold=True)
    text(
        draw,
        (80, 118),
        "Final v3 saves both leaf identity and leaf state with each rank, then validates them immediately before reuse.",
        28,
        fill=MUTED,
    )

    card(
        draw,
        (110, 220, 2450, 510),
        "Prepared during checkReads",
        "saved leaf address  •  saved leaf generation  •  saved mutation epoch  •  saved rank  •  representative and boundary context",
        accent=BLUE,
        body_size=27,
    )

    text(draw, (1280, 585), "Before addWrites reuses the rank", 34, bold=True, anchor="ma")
    cards = [
        (
            (90, 660, 820, 1190),
            "Generation + epoch match",
            "The address still contains the same leaf generation and its mutation epoch is unchanged.\n\nThe saved rank may be reused, subject to the representative and boundary checks.",
            GREEN,
            "REUSE",
        ),
        (
            (915, 660, 1645, 1190),
            "Same leaf, newer epoch",
            "An earlier accepted write changed this leaf. Its address and generation still match, but the mutation epoch does not.\n\nThe saved rank is stale.",
            ORANGE,
            "SEARCH AGAIN",
        ),
        (
            (1740, 660, 2470, 1190),
            "Generation mismatch",
            "Reclamation released the leaf, or the block was reused. Odd node and even key generations also make cross-role reuse fail safely.\n\nThe saved leaf must not be dereferenced as the old leaf.",
            RED,
            "SEARCH AGAIN",
        ),
    ]
    for xy, title_value, body, accent, result in cards:
        card(draw, xy, title_value, body, accent=accent, body_size=23)
        x1, _, x2, y2 = xy
        draw.rounded_rectangle((x1 + 25, y2 - 82, x2 - 25, y2 - 25), radius=14, fill=accent)
        text(draw, ((x1 + x2) / 2, y2 - 54), result, 25, bold=True, fill=BG, anchor="mm")

    draw.rounded_rectangle((110, 1290, 2450, 1595), radius=22, fill="#eef4ff", outline=BLUE, width=4)
    text(draw, (145, 1325), "Boundary check after validation", 30, bold=True, fill=BLUE)
    wrapped(
        draw,
        (145, 1380),
        "Even when leaf generation and epoch match, a split may have changed the leaf's upper boundary. If the write key now belongs beyond that boundary, the task follows the right neighbour and continues from the correct leaf. Every failure path treats the prepared destination as a hint and searches the current tree state.",
        25,
        2240,
        fill=INK,
        line_gap=11,
    )
    image.save(OUT / "fig-v3-destination-validation.png", optimize=True)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    generation_spaces()
    destination_validation()
    evolution()
    vs_fdb()
