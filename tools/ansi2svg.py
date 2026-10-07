# -*- coding: utf-8 -*-
"""Turn status-line output (ANSI colours) into an SVG that looks like a Windows Terminal window.
Used to build the README previews:  python examples/mock.py --svg docs/images
"""
import html
import re
import unicodedata

# Windows Terminal default scheme ("Campbell")
PALETTE = {
    '31': '#C50F1F', '32': '#13A10E', '33': '#C19C00', '90': '#767676',
    '95': '#B4009E', '96': '#61D6D6', '97': '#F2F2F2',
}
FG, BG, CHROME = '#CCCCCC', '#0C0C0C', '#1F1F1F'
CELL_W, LINE_H, FONT_PX = 8.4, 22, 14
PAD_X, TOP = 18, 52
SGR = re.compile(r'\x1b\[([0-9;]*)m')
BLOCKS = {'█': 1.0, '░': 0.35}   # bar cell → fill opacity


def cell_width(ch):
    """Emoji and East Asian wide characters take two terminal cells."""
    if ord(ch) >= 0x1F000 or unicodedata.east_asian_width(ch) in ('W', 'F'):
        return 2
    return 1


def parse(line):
    """Yield (text, colour, bold) runs."""
    colour, bold, pos = FG, False, 0
    for m in SGR.finditer(line):
        if m.start() > pos:
            yield line[pos:m.start()], colour, bold
        for code in (m.group(1) or '0').split(';'):
            if code in ('', '0'):
                colour, bold = FG, False
            elif code == '1':
                bold = True
            elif code in PALETTE:
                colour = PALETTE[code]
        pos = m.end()
    if pos < len(line):
        yield line[pos:], colour, bold


def to_svg(lines, title='Claude Code'):
    widths = [sum(cell_width(c) for c in SGR.sub('', l)) for l in lines]
    w = int(PAD_X * 2 + max(widths + [60]) * CELL_W)
    h = TOP + LINE_H * len(lines) + 4
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">',
        f'<rect width="{w}" height="{h}" rx="8" fill="{BG}"/>',
        f'<path d="M0 8a8 8 0 0 1 8-8h{w - 16}a8 8 0 0 1 8 8v26H0z" fill="{CHROME}"/>',
        # tab with the window title, Windows-style caption buttons on the right
        f'<rect x="10" y="6" width="150" height="28" rx="6" fill="{BG}"/>',
        f'<text x="24" y="25" font-family="Segoe UI, sans-serif" font-size="12" fill="{FG}">{html.escape(title)}</text>',
        f'<g stroke="{FG}" stroke-width="1" fill="none">'
        f'<line x1="{w - 118}" y1="17" x2="{w - 108}" y2="17"/>'
        f'<rect x="{w - 72}" y="12" width="10" height="10"/>'
        f'<line x1="{w - 28}" y1="12" x2="{w - 18}" y2="22"/><line x1="{w - 18}" y1="12" x2="{w - 28}" y2="22"/></g>',
        f'<g font-family="Cascadia Mono, Consolas, monospace" font-size="{FONT_PX}" xml:space="preserve">',
    ]
    for i, line in enumerate(lines):
        y = TOP + LINE_H * i + 6
        col = 0
        for text, colour, bold in parse(line):
            # Pin everything to terminal cells. Bar cells are drawn as rectangles (fallback fonts
            # draw █/░ wider than one cell); spaces are skipped and only advance the cursor;
            # other characters get one x per glyph so emoji and wide glyphs cannot shift the rest.
            weight = ' font-weight="bold"' if bold else ''
            chars, xs = [], []

            def flush():
                if chars:
                    out.append(f'<text x="{" ".join(xs)}" y="{y}" fill="{colour}"{weight}>'
                               f'{html.escape("".join(chars))}</text>')
                    chars.clear()
                    xs.clear()

            for ch in text:
                x = PAD_X + col * CELL_W
                if ch in BLOCKS:
                    flush()
                    out.append(f'<rect x="{x + 0.5:.1f}" y="{y - 13}" width="{CELL_W - 1:.1f}" height="16" '
                               f'fill="{colour}" fill-opacity="{BLOCKS[ch]}"/>')
                elif ch == ' ':
                    flush()
                else:
                    chars.append(ch)
                    xs.append(f'{x:.1f}')
                col += cell_width(ch)
            flush()
    out.append('</g></svg>')
    return '\n'.join(out)
