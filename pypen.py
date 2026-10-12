#!/usr/bin/env python3
"""pypen — converte um arquivo .txt em um PDF de UMA página, com cara de escrita à mão.

Cada caractere é desenhado individualmente com leve rotação, "tremor" de linha e
variação sutil de tamanho/tinta, simulando caligrafia. Usa apenas Pillow.

Exemplos:
    python pypen.py texto.txt
    python pypen.py texto.txt -o saida.pdf
    python pypen.py texto.txt --size 40 --seed 7 --ink 1f3a93
    python pypen.py texto.txt --font medieval --paper-color f5f1e8
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# --- constantes -----------------------------------------------------------------

DPI = 150  # resolução do PDF (A4 em 150 DPI -> 1240 x 1754 px)
MIN_FONT_SIZE = 10
LINE_HEIGHT_FACTOR = 1.45

PAPERS: dict[str, tuple[int, int]] = {
    "a4": (round(595.28 / 72 * DPI), round(841.89 / 72 * DPI)),
    "letter": (round(612 / 72 * DPI), round(792 / 72 * DPI)),
}

BUNDLED_FONTS = ("fonts/PatrickHand-Regular.ttf", "fonts/Kalam-Regular.ttf")

# presets nomeados para --font (valores são caminhos relativos à raiz do projeto)
FONT_PRESETS: dict[str, str] = {
    # — caneta, dia a dia —
    "manuscrita": "fonts/PatrickHand-Regular.ttf",   # caneta, dia a dia
    "kalam": "fonts/Kalam-Regular.ttf",              # caneta, traço mais grosso
    # — cursivas —
    "cursiva": "fonts/Caveat-Variable.ttf",          # cursiva casual (Caveat Project)
    "dancing": "fonts/DancingScript-Variable.ttf",   # cursiva fluida (Dancing Script Project)
    "tangerine": "fonts/Tangerine-Regular.ttf",      # cursiva fina (Toshi Omagari)
    "indie": "fonts/IndieFlower-Regular.ttf",        # cursiva despojada (kimberlygeswein)
    "sacramento": "fonts/Sacramento-Regular.ttf",    # cursiva elegante (Astigmatic)
    "allura": "fonts/Allura-Regular.ttf",            # caligráfica (Allura Project)
    "great-vibes": "fonts/GreatVibes-Regular.ttf",   # caligráfica fina (Great Vibes Project)
    # — medievais —
    "medieval": "fonts/MedievalSharp-Regular.ttf",   # "medieval sharp" (wmk69)
    "uncial": "fonts/UncialAntiqua-Regular.ttf",     # uncial, manuscritos 4º-8º s.
    "fraktur": "fonts/UnifrakturMaguntia-Book.ttf",  # blackletter (j. wust / P. Wiegel)
    "fraktur-bold": "fonts/UnifrakturCook-Bold.ttf", # blackletter grossa (j. wust)
    "almendra": "fonts/Almendra-Regular.ttf",        # serifas "antigas" (A. Sanfelippo)
    "im-fell": "fonts/IMFellEnglish-Regular.ttf",    # estilo livro do séc. XVII (I. Marini)
    "gotica": "fonts/GrenzeGotisch-Variable.ttf",    # gótica de display (Omnibus-Type)
}
SYSTEM_FONTS = (
    "/usr/share/fonts/truetype/crosextra/ComicNeue-Regular.ttf",
    "/usr/share/fonts/truetype/comic/ComicShanns-Regular.ttf",
    "/usr/share/fonts/truetype/caveat/Caveat-Regular.ttf",
    "/usr/share/fonts/truetype/kalam/Kalam-Regular.ttf",
    "/usr/share/fonts/truetype/patrickhand/PatrickHand-Regular.ttf",
)


# --- utilidades -----------------------------------------------------------------

def parse_color(value: str, nome: str = "cor", exemplo: str = "2b3a67") -> tuple[int, int, int]:
    s = value.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or any(c not in "0123456789abcdefABCDEF" for c in s):
        sys.exit(f"erro: {nome} inválida {value!r} (ex.: {exemplo})")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def luminance(rgb: tuple[int, int, int]) -> float:
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: tuple[int, int, int], b: tuple[int, int, int]) -> float:
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def resolve_font_path(explicit: str | None) -> Path | None:
    """Retorna o caminho da fonte a usar, ou None para usar a fonte padrão do Pillow.

    `explicit` pode ser um caminho para .ttf/.otf ou o nome de um preset
    (ex.: "medieval", "fraktur" — veja FONT_PRESETS).
    """
    if explicit:
        p = Path(explicit)
        if p.is_file():
            return p
        rel = FONT_PRESETS.get(explicit.lower())
        if rel:
            fp = Path(__file__).resolve().parent / rel
            if fp.is_file():
                return fp
        preset_list = ", ".join(f"{k} ({v.split('/')[-1]})" for k, v in FONT_PRESETS.items())
        sys.exit(f"erro: fonte não encontrada: {explicit!r}\npresets disponíveis: {preset_list}")
    script_dir = Path(__file__).resolve().parent
    for rel in BUNDLED_FONTS:
        p = script_dir / rel
        if p.is_file():
            return p
    for rel in SYSTEM_FONTS:
        if Path(rel).is_file():
            return Path(rel)
    return None


def has_glyph(font: ImageFont.FreeTypeFont, ch: str) -> bool:
    try:
        b = font.getbbox(ch)
    except (AttributeError, OSError):
        return False
    return b is not None and (b[3] - b[1]) > 0


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: float) -> list[str]:
    """Quebra o texto em linhas (greedy, por palavra) que cabem em max_width."""
    lines: list[str] = []
    for raw in text.splitlines():
        if not raw.strip():
            lines.append("")
            continue
        line = ""
        for word in raw.split():
            trial = f"{line} {word}" if line else word
            if not line or font.getlength(trial) <= max_width:
                line = trial
            else:
                lines.append(line)
                line = word
        lines.append(line)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


# --- renderização ----------------------------------------------------------------

def render(
    text: str,
    *,
    font_path: Path | None,
    size: int,
    page: tuple[int, int],
    margin: int,
    ink: tuple[int, int, int],
    background: tuple[int, int, int] = (255, 255, 255),
    seed: int | None,
    jitter: bool = True,
) -> tuple[Image.Image, int, list[str]]:
    """Desenha o texto em uma página RGB. Retorna (imagem, tamanho final, linhas).

    O tamanho da fonte é reduzido automaticamente até o texto caber em 1 página.
    """
    rng = random.Random(seed)
    page_w, page_h = page
    max_width = page_w - 2 * margin
    max_height = page_h - 2 * margin

    # fonte principal + fallback (para glifos ausentes)
    fallback = ImageFont.load_default(size=32)
    if font_path is not None:
        base_font = ImageFont.truetype(str(font_path), size=32)
    else:
        base_font = fallback

    # encontra o tamanho de fonte que cabe em uma página
    font_size = min(size, 96)
    while font_size > MIN_FONT_SIZE:
        font = base_font.font_variant(size=font_size)
        lines = wrap_text(text, font, max_width)
        if len(lines) * int(font_size * LINE_HEIGHT_FACTOR) <= max_height:
            break
        font_size -= 2
    font = base_font.font_variant(size=font_size)
    lines = wrap_text(text, font, max_width)
    overflow = len(lines) * int(font_size * LINE_HEIGHT_FACTOR) > max_height

    # --- desenha a página ---
    img = Image.new("RGB", (page_w, page_h), background)
    draw = ImageDraw.Draw(img)
    ascent, _ = font.getmetrics()
    line_h = int(font_size * LINE_HEIGHT_FACTOR)
    pad = max(6, font_size // 4)
    scaled_cache: dict[int, ImageFont.FreeTypeFont] = {}

    for i, line in enumerate(lines):
        base_yb = margin + i * line_h + ascent
        x = margin + (rng.uniform(-4, 8) if jitter else 0)  # margem levemente irregular

        for ch in line:
            if ch == " ":
                x += font.getlength(" ")
                continue

            # escolhe a fonte (principal ou fallback)
            f = font if has_glyph(font, ch) else (
                fallback if has_glyph(fallback, ch) else None
            )
            if f is None:  # glifo ausente em ambas: avança sem desenhar
                x += font.getlength(ch)
                continue

            # variação de tamanho por caractere
            s = font_size * rng.uniform(0.95, 1.07) if jitter else float(font_size)
            s_q = max(6, int(round(s / 2)) * 2)
            if s_q not in scaled_cache:
                scaled_cache[s_q] = f.font_variant(size=s_q)
            f2 = scaled_cache[s_q]

            b = f2.getbbox(ch) or (0, 0, 1, 1)
            w = max(1, b[2] - b[0])
            h = max(1, b[3] - b[1])
            tile = Image.new("RGBA", (w + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
            ImageDraw.Draw(tile).text(
                (pad - b[0], pad - b[1]), ch, font=f2,
                fill=ink + (rng.randint(225, 255) if jitter else 255,),
            )
            if jitter:
                tile = tile.rotate(rng.uniform(-4, 4), resample=Image.BICUBIC, expand=True)

            dy = rng.uniform(-1.5, 1.5) * (font_size / 30) if jitter else 0.0
            yb = base_yb + dy
            img.paste(tile, (int(x - pad), int(yb - (pad - b[1]))), tile)
            x += f2.getlength(ch)

    return img, font_size, lines


# --- CLI --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pypen",
        description="Transforma um arquivo .txt em um PDF de uma página com aparência de escrita à mão.",
        epilog="exemplos:\n"
               "  python pypen.py texto.txt\n"
               "  python pypen.py texto.txt -o saida.pdf --seed 7\n"
"  python pypen.py texto.txt --size 40 --ink 1f3a93 --paper letter\n"
"  python pypen.py texto.txt --font medieval --paper-color f5f1e8\n"
"  python pypen.py texto.txt --textura --seed 7   # papel + tinta realistas (augraphy)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("input", type=Path, help="arquivo .txt de entrada")
    p.add_argument("-o", "--output", type=Path, default=None,
                   help="arquivo .pdf de saída (padrão: <entrada>.pdf)")
    p.add_argument("--size", type=int, default=34, help="tamanho da fonte, em px @150 DPI (padrão: 34)")
    p.add_argument("--font", type=str, default=None,
                   help="preset de fonte ou caminho .ttf/.otf (padrão: manuscrita). "
                        f"presets: {', '.join(FONT_PRESETS)}")
    p.add_argument("--ink", type=str, default="2b3a67", help="cor da tinta em hex (sem #), ex.: 2b3a67 (padrão: azul-caneta)")
    p.add_argument("--paper-color", type=str, default="ffffff", dest="paper_color",
                   help="cor do papel em hex (sem #), ex.: f5f1e8 para papel envelhecido (padrão: branco)")
    p.add_argument("--seed", type=int, default=None, help="semente aleatória p/ reproduzir o mesmo 'tremor'")
    p.add_argument("--margin", type=int, default=90, help="margem da página, em pixels (padrão: 90)")
    p.add_argument("--paper", choices=sorted(PAPERS), default="a4", help="tamanho do papel (padrão: a4)")
    p.add_argument("--no-jitter", action="store_true", help="desliga o efeito manuscrito (texto reto)")
    p.add_argument("--textura", action="store_true",
                   help="pós-processa o PDF com textura realista de papel/tinta (módulo textura.py; "
                        "requer: pip install -r requirements-textura.txt)")
    p.add_argument("--intensidade", type=float, default=0.6, dest="intensidade",
                   help="força da textura, 0-1 (padrão: 0.6; só tem efeito com --textura)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if not args.input.is_file():
        sys.exit(f"erro: arquivo não encontrado: {args.input}")
    if args.size < MIN_FONT_SIZE:
        sys.exit(f"erro: --size muito pequeno (mínimo {MIN_FONT_SIZE})")
    if args.margin < 0 or 2 * args.margin >= min(PAPERS[args.paper]):
        sys.exit("erro: --margin incompatível com o tamanho do papel")

    text = args.input.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        print(f"aviso: {args.input} está vazio; gerando página em branco.", file=sys.stderr)

    ink = parse_color(args.ink, "cor da tinta")
    paper = parse_color(args.paper_color, "cor do papel", exemplo="f5f1e8")
    if contrast_ratio(ink, paper) < 2.5:
        print("aviso: tinta e papel muito próximas; o texto pode ficar pouco legível.", file=sys.stderr)

    font_path = resolve_font_path(args.font)
    font_label = str(font_path) if font_path else "padrão (DejaVu)"

    img, font_size, lines = render(
        text,
        font_path=font_path,
        size=args.size,
        page=PAPERS[args.paper],
        margin=args.margin,
        ink=ink,
        background=paper,
        seed=args.seed,
        jitter=not args.no_jitter,
    )

    out = args.output or args.input.with_suffix(".pdf")
    img.save(out, format="PDF", resolution=DPI)

    texturizado = False
    if args.textura:
        try:
            import textura  # módulo opcional da mesma pasta (não afeta o núcleo)
            textura.texturizar_pdf(out, out, seed=args.seed, intensidade=args.intensidade)
            texturizado = True
        except SystemExit as e:
            print(f"aviso: {e}", file=sys.stderr)
            print("O PDF acima foi gerado SEM textura.", file=sys.stderr)
            return 1

    print(f"✔ {out} ({out.stat().st_size / 1024:.1f} KiB)")
    print(f"  página: {PAPERS[args.paper][0]}x{PAPERS[args.paper][1]} px @ {DPI} DPI ({args.paper})")
    print(f"  linhas: {len(lines)} | fonte: {font_label} | tamanho final: {font_size}px")
    if texturizado:
        print(f"  textura: aplicada (augraphy) | intensidade: {args.intensidade}")
    if args.seed is not None:
        print(f"  seed: {args.seed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
