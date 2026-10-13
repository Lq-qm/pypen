#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
textura.py — texturização realista dos PDFs gerados pelo pypen (módulo opcional).

Usa a biblioteca **augraphy** para dar a um PDF que *já foi criado* a cara de
página manuscrita de verdade — e com **opções de personalização**:

  * tipo de textura do papel  (--textura)
  * tom do papel             (--tom: neutro, creme, sepia, azulado)
  * força global             (--intensidade)
  * e cada efeito individual (--manchas, --bleed, --grao, --bordas, --luz)

Como o augraphy 8.x trabalha com camadas separadas (papel e tinta), este módulo:

1. extrai a página (imagem RGB) do PDF;
2. separa a "camada de tinta" (pixels escuros) da página original;
3. gera um papel texturizado sobre um canvas branco (PaperFactory do augraphy);
4. recompor a tinta com a cor original sobre o papel;
5. aplica os efeitos de tinta e envelhecimento (InkBleed, Stains, ...).

O núcleo do pypen (CLI e GUI) NÃO depende deste módulo. Para usá-lo, instale:

    pip install -r requirements.txt        # já inclui o augraphy

Uso no terminal:

    python textura.py saida.pdf                     # -> saida_texturizado.pdf
    python textura.py saida.pdf -o velha.pdf --seed 7
    python textura.py saida.pdf --intensidade 0.9 --textura fine_stains
    python textura.py saida.pdf --tom sepia --bordas 0.8 --luz 0.5 --manchas 0

Uso em Python:

    from textura import texturizar_pdf
    texturizar_pdf("saida.pdf", "saida_texturada.pdf", seed=7,
                   intensidade=0.6, tom="creme", bordas=0.5)
"""
from __future__ import annotations

import argparse
import io
import random
import sys
from pathlib import Path

try:
    import numpy as np
    import augraphy
except ImportError:  # augraphy é opcional — sem ele este módulo não funciona
    np = None
    augraphy = None

from PIL import Image

# Tipos de textura gerados pelo PaperFactory que usamos (testados no
# augraphy 8.x em Python 3.11+):
#   - determinísticos com random/np/cv2 semeados;
#   - claros (não escurecem o papel);
#   - sem o bug do random.randint com numpy.float64.
# ("strange" é não-determinístico e escuro; "dot_granular"/"rough_granular"
#  têm o bug — todos evitados.)
SAFE_TEX_TYPES = [
    "normal",
    "rough_stains",
    "fine_stains",
    "light_stains",
    "curvy_edge",
]

# Tons de papel: multiplicadores RGB aplicados sobre a textura gerada
# (neutro = sem tingimento; o resto dá a cor de papel velho de verdade).
TONS = {
    "neutro":  (255, 255, 255),
    "creme":   (255, 248, 232),
    "sepia":   (255, 241, 214),
    "azulado": (240, 246, 255),
}

# DPI padrão, idêntico ao do pypen (A4/Letter em px já vêm embutidos no PDF)
DPI = 150


def _exigir_augraphy() -> None:
    if augraphy is None:
        raise SystemExit(
            "augraphy não está instalado neste Python. "
            "Rode:  pip install -r requirements.txt"
        )


def extrair_pagina(caminho: str | Path) -> Image.Image:
    """Extrai a página (imagem RGB) embutida num PDF de 1 página.

    O pypen salva o PDF como uma única imagem JPEG (DCTDecode); localizamos
    a stream JPEG dentro dos bytes do PDF e a abrimos com o Pillow.
    """
    dados = Path(caminho).read_bytes()
    ini = dados.find(b"\xff\xd8")      # SOI — início do JPEG
    fim = dados.rfind(b"\xff\xd9")     # EOI — fim do JPEG
    if ini < 0 or fim <= ini:
        raise ValueError(
            f"Não encontrei imagem embutida em {caminho!r}. "
            "Este módulo funciona com PDFs gerados pelo pypen "
            "(imagem de página inteira)."
        )
    return Image.open(io.BytesIO(dados[ini : fim + 2])).convert("RGB")


def _semeiar(seed: int | float | None) -> None:
    """Semeia os PRNGs usados pelo augraphy (random, numpy, cv2) + o nosso."""
    import numpy as np
    if seed is None:
        return
    s = int(seed)
    random.seed(s)
    np.random.seed(s % (2**32))
    try:
        import cv2
        cv2.setRNGSeed(s)
    except ImportError:
        pass


def _camada_papel(tamanho: tuple[int, int], tipo_textura: str, rng: random.Random) -> np.ndarray:
    """Gera a camada de papel texturizado (RGB, ~branco) no tamanho da página."""
    larg, alt = tamanho
    branco = np.full((alt, larg, 3), 255, dtype=np.uint8)
    pipeline = augraphy.AugraphyPipeline(
        paper_phase=[
            augraphy.PaperFactory(
                generate_texture=1,
                generate_texture_background_type=tipo_textura,
                generate_texture_edge_type="curvy_edge",
                texture_enable_color=0,  # textura neutra; a cor do papel vem do pypen
                blend_texture=1,
                blend_texture_background_type=rng.choice(SAFE_TEX_TYPES),
                blend_texture_edge_type="curvy_edge",
                p=1,
            ),
        ],
        overlay_type="normal",  # preserva o texto (não "esmaga" nada)
    )
    arr = np.asarray(pipeline(branco))
    arr = np.clip(arr, 0, 255).astype("uint8")
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return arr


def _aplicar(aug: object, img: np.ndarray) -> np.ndarray:
    """Aplica uma augmentation diretamente na imagem (preservando 3 canais)."""
    res = aug(img, force=True)
    arr = np.asarray(getattr(res, "result", res))
    arr = np.clip(arr, 0, 255).astype("uint8")
    if arr.ndim == 2:
        arr = np.stack([arr] * 3, axis=-1)
    return arr


def _escurecer_bordas(img: np.ndarray, forca: float) -> np.ndarray:
    """Escurece as bordas da página (vignette) — papel usado de verdade."""
    forca = min(1.0, max(0.0, float(forca)))
    if forca == 0:
        return img
    alt, larg = img.shape[:2]
    y, x = np.mgrid[0:alt, 0:larg]
    dx = (x - larg / 2) / (larg / 2)
    dy = (y - alt / 2) / (alt / 2)
    d = np.sqrt(dx * dx + dy * dy) / np.sqrt(2)  # 0 no centro, 1 nos cantos
    t = np.clip((d - 0.70) / (1.0 - 0.70), 0.0, 1.0) ** 1.7
    fator = (1.0 - forca * 0.30 * t)[..., None]  # até ~30% mais escuro no canto
    return np.clip(img.astype(float) * fator, 0, 255).astype("uint8")


def _escala(valor: float, teto: float = 1.5) -> float:
    """Multiplicador de efeito: 0 desliga, 1 = padrão, até `teto` reforça."""
    return min(float(teto), max(0.0, float(valor)))


def _escalar(efeito: np.ndarray, base: np.ndarray, forca: float) -> np.ndarray:
    """Amplifica o delta do efeito por `forca` (1.0 = efeito como gerado, 1.5 = reforçado)."""
    if forca == 1.0:
        return efeito
    out = base.astype(float) + (efeito.astype(float) - base.astype(float)) * forca
    return np.clip(out, 0, 255).astype("uint8")


def _sombra_suave() -> "augraphy.ShadowCast":
    """ShadowCast afinado: sombra discreta nas bordas da página (a padrão do
    augraphy é forte demais e não dá para dosar por força — por isso o _escalar)."""
    return augraphy.ShadowCast(
        p=1,
        shadow_opacity_range=(0.12, 0.28),
        shadow_width_range=(0.06, 0.16),
        shadow_height_range=(0.06, 0.16),
        shadow_blur_kernel_range=(61, 121),
        shadow_iterations_range=(1, 1),
    )


def texturizar_pdf(
    entrada: str | Path,
    saida: str | Path | None = None,
    *,
    seed: int | None = None,
    intensidade: float = 0.6,
    tipo_textura: str = "random",
    tom: str = "neutro",
    manchas: float = 1.0,
    bleed: float = 1.0,
    grão: float = 1.0,
    bordas: float = 0.5,
    luz: float = 0.3,
    atravessada: float = 0.0,
    sombra: float = 0.0,
    varredura: float = 0.0,
    dpi: int = DPI,
) -> Path:
    """Aplica texturização realista a um PDF de 1 página e salva o resultado.

    :param entrada: PDF já criado (gerado pelo pypen).
    :param saida: destino; padrão "<nome do entrada>_texturizado.pdf".
    :param seed: semente para reprodutibilidade (None = aleatório).
    :param intensidade: 0.0–1.0 (padrão 0.6) — força global do envelhecimento.
    :param tipo_textura: um de SAFE_TEX_TYPES ou "random" (sorteado com a seed).
    :param tom: cor do papel — neutro | creme | sepia | azulado.
    :param manchas: multiplicador das manchas de idade (0 desliga, 1 = padrão).
    :param bleed: multiplicador do bleed de tinta (0 desliga, 1 = padrão).
    :param grão: multiplicador do grão fino (0 desliga, 1 = padrão).
    :param bordas: escurecimento das bordas, 0–1 (padrão 0.5).
    :param luz: gradiente de luz ("papel sob lâmpada"), 0–1 (padrão 0.3).
    :param atravessada: tinta atravessada (fantasma da tinta pelo verso),
        0–1.5 (padrão 0 = desligado; 1 = padrão, 1.5 reforça).
    :param sombra: sombra suave nas bordas da página, 0–1.5 (padrão 0).
    :param varredura: artefatos de varredura antiga (JPEG), 0–1.5 (padrão 0).
    :param dpi: resolução do PDF de saída (padrão 150, igual ao pypen).
    :return: caminho do PDF texturizado criado.
    """
    _exigir_augraphy()
    entrada = Path(entrada)
    if not entrada.exists():
        raise FileNotFoundError(f"PDF não encontrado: {entrada}")
    if tom not in TONS:
        raise ValueError(f"tom desconhecido: {tom!r} — use um de {list(TONS)}")

    intensidade = min(1.0, max(0.0, float(intensidade)))
    m_f = _escala(manchas)   # multiplicadores de cada efeito
    b_f = _escala(bleed)
    g_f = _escala(grão)
    at_f = _escala(atravessada)  # camada "página usada"
    so_f = _escala(sombra)
    va_f = _escala(varredura)

    rng = random.Random(seed)
    tipo = tipo_textura if tipo_textura != "random" else rng.choice(SAFE_TEX_TYPES)
    if tipo not in SAFE_TEX_TYPES:
        raise ValueError(
            f"tipo de textura desconhecido: {tipo!r} — use um de {SAFE_TEX_TYPES} ou 'random'"
        )

    pagina = extrair_pagina(entrada)
    orig = np.array(pagina)
    alt, larg, _ = orig.shape
    lum = 0.299 * orig[..., 0] + 0.587 * orig[..., 1] + 0.114 * orig[..., 2]

    # 2) camada de papel texturizado (canvas branco -> textura) + tom do papel
    _semeiar(seed)
    papel = _camada_papel((larg, alt), tipo, rng)
    if tom != "neutro":
        fator_tom = np.array(TONS[tom], dtype=float) / 255.0
        papel = np.clip(papel.astype(float) * fator_tom, 0, 255).astype("uint8")

    # 3) recompor a página original (tinta com cor e anti-alias intactos)
    #    sobre o papel texturizado: tinta sólida opaca, bordas mescladas.
    alfa = np.clip((210.0 - lum) / (210.0 - 80.0), 0.0, 1.0)[..., None]
    pagina2 = (papel.astype(float) * (1.0 - alfa) + orig * alfa).astype("uint8")

    # 4) efeito de tinta: bleed (tinta "esmaga" o papel, como caneta de verdade)
    _semeiar(seed)
    if intensidade > 0 and b_f > 0:
        pagina2 = _aplicar(
            augraphy.InkBleed(
                intensity_range=(0.2, 0.3 + 0.4 * intensidade * min(b_f, 1.0)),
                severity=(0.2, 0.3 + 0.3 * intensidade * min(b_f, 1.0)),
                p=round(min(1.0, 0.9 * intensidade * b_f), 4),
            ),
            pagina2,
        )

    # 5) envelhecimento do papel
    _semeiar(seed)
    if m_f > 0:  # manchas de idade
        pagina2 = _aplicar(
            augraphy.Stains(
                stains_type="random",
                stains_blend_alpha=round((0.2 + 0.3 * intensidade) * min(m_f, 1.0), 3),
                p=round(min(1.0, 0.7 * intensidade * m_f), 4),
            ),
            pagina2,
        )
    if intensidade > 0:  # brilho irregular (papel que não reflete igual)
        pagina2 = _aplicar(
            augraphy.BrightnessTexturize(
                texturize_range=(round(1 - 0.04 - 0.05 * intensidade, 3), 0.99),
                p=0.8,
            ),
            pagina2,
        )

    # 5b) página usada: tinta atravessada (fantasma da escrita pelo verso)
    if at_f > 0:
        _semeiar(seed)
        bt = _aplicar(augraphy.BleedThrough(p=1), pagina2)
        pagina2 = _escalar(bt, pagina2, at_f)

    # 6) iluminação: gradiente de luz (efeito forte do augraphy, mesclado)
    if luz > 0:
        _semeiar(seed)
        l_f = min(1.0, max(0.0, float(luz)))
        sombra = _aplicar(augraphy.LightingGradient(p=1), pagina2)
        pagina2 = (pagina2.astype(float) * (1.0 - l_f) + sombra * l_f).astype("uint8")

    # 7) bordas escurecidas (vignette) — determinístico, nosso próprio
    pagina2 = _escurecer_bordas(pagina2, bordas)

    # 7b) página usada: sombra suave nas bordas da página
    if so_f > 0:
        _semeiar(seed)
        sc = _aplicar(_sombra_suave(), pagina2)
        pagina2 = _escalar(sc, pagina2, so_f)

    # 8) grão fino (por cima de tudo)
    if g_f > 0:
        pagina2 = _aplicar(
            augraphy.SubtleNoise(subtle_range=max(2, int((2 + 10 * intensidade) * min(g_f, 1.0))), p=1),
            pagina2,
        )

    # 8b) página usada: artefatos de varredura antiga (por último, como num scan real)
    if va_f > 0:
        _semeiar(seed)
        jp = _aplicar(augraphy.Jpeg(p=1, quality_range=(18, 45)), pagina2)
        pagina2 = _escalar(jp, pagina2, va_f)

    img = Image.fromarray(pagina2, "RGB")
    saida = Path(saida) if saida else entrada.with_name(f"{entrada.stem}_texturizado.pdf")
    img.save(saida, format="PDF", resolution=dpi)
    return saida


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Texturiza um PDF do pypen com augraphy (papel, tinta, manchas).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    ap.add_argument("entrada", help="PDF já criado (1 página, gerado pelo pypen)")
    ap.add_argument(
        "-o", "--saida",
        help="destino (padrão: <entrada>_texturizado.pdf)",
    )
    ap.add_argument(
        "--seed", type=int, default=None, metavar="N",
        help="semente para resultado reproduzível (padrão: aleatório)",
    )
    ap.add_argument(
        "--intensidade", type=float, default=0.6, metavar="0-1",
        help="força global do envelhecimento (0 = só textura de papel, 1 = forte)",
    )
    ap.add_argument(
        "--textura", default="random",
        help="tipo de textura do papel: random | " + " | ".join(SAFE_TEX_TYPES),
    )
    ap.add_argument(
        "--tom", default="neutro", choices=list(TONS),
        help="cor do papel (tinge a textura)",
    )
    ap.add_argument(
        "--manchas", type=float, default=1.0, metavar="0-1.5",
        help="manchas de idade: 0 desliga, 1 = padrão, 1.5 reforça",
    )
    ap.add_argument(
        "--bleed", type=float, default=1.0, metavar="0-1.5",
        help="bleed de tinta (tinta esmagada no papel): 0 desliga, 1 = padrão",
    )
    ap.add_argument(
        "--grao", type=float, default=1.0, metavar="0-1.5",
        help="grão fino do papel: 0 desliga, 1 = padrão",
    )
    ap.add_argument(
        "--bordas", type=float, default=0.5, metavar="0-1",
        help="escurecimento das bordas (vignette): 0 desliga",
    )
    ap.add_argument(
        "--luz", type=float, default=0.3, metavar="0-1",
        help="gradiente de luz (papel sob lâmpada): 0 desliga",
    )
    ap.add_argument(
        "--atravessada", type=float, default=0.0, metavar="0-1.5",
        help="tinta atravessada (fantasma da tinta pelo verso): 0 desliga, 1 = padrão",
    )
    ap.add_argument(
        "--sombra", type=float, default=0.0, metavar="0-1.5",
        help="sombra suave nas bordas da página: 0 desliga, 1 = padrão",
    )
    ap.add_argument(
        "--varredura", type=float, default=0.0, metavar="0-1.5",
        help="artefatos de varredura antiga (scan): 0 desliga, 1 = padrão",
    )
    args = ap.parse_args(argv)

    try:
        saida = texturizar_pdf(
            args.entrada, args.saida,
            seed=args.seed,
            intensidade=args.intensidade,
            tipo_textura=args.textura,
            tom=args.tom,
            manchas=args.manchas,
            bleed=args.bleed,
            grão=args.grao,
            bordas=args.bordas,
            luz=args.luz,
            atravessada=args.atravessada,
            sombra=args.sombra,
            varredura=args.varredura,
        )
    except (SystemExit, FileNotFoundError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    print(f"PDF texturizado: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
