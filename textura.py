#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
textura.py — texturização realista dos PDFs gerados pelo pypen (módulo opcional).

Usa a biblioteca **augraphy** para dar a um PDF que *já foi criado* a cara de
página manuscrita de verdade: textura de papel, bleed de tinta, manchas de
idade, variação de brilho e grão fino.

Como o augraphy 8.x trabalha com camadas separadas (papel e tinta), este módulo:

1. extrai a página (imagem RGB) do PDF;
2. separa a "camada de tinta" (pixels escuros) da página original;
3. gera um papel texturizado sobre um canvas branco (PaperFactory do augraphy);
4. recompor a tinta com a cor original sobre o papel;
5. aplica os efeitos de tinta e envelhecimento (InkBleed, Stains, ...).

O núcleo do pypen (CLI e GUI) NÃO depende deste módulo. Para usá-lo, instale:

    pip install -r requirements-textura.txt

Uso no terminal:

    python textura.py saida.pdf                     # -> saida_texturizado.pdf
    python textura.py saida.pdf -o velha.pdf --seed 7
    python textura.py saida.pdf --intensidade 0.9 --textura fine_stains

Uso em Python:

    from textura import texturizar_pdf
    texturizar_pdf("saida.pdf", "saida_texturada.pdf", seed=7, intensidade=0.6)
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

# DPI padrão, idêntico ao do pypen (A4/Letter em px já vêm embutidos no PDF)
DPI = 150


def _exigir_augraphy() -> None:
    if augraphy is None:
        raise SystemExit(
            "augraphy não está instalado neste Python. "
            "Rode:  pip install -r requirements-textura.txt"
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


def texturizar_pdf(
    entrada: str | Path,
    saida: str | Path | None = None,
    *,
    seed: int | None = None,
    intensidade: float = 0.6,
    tipo_textura: str = "random",
    dpi: int = DPI,
) -> Path:
    """Aplica texturização realista a um PDF de 1 página e salva o resultado.

    :param entrada: PDF já criado (gerado pelo pypen).
    :param saida: destino; padrão "<nome do entrada>_texturizado.pdf".
    :param seed: semente para reprodutibilidade (None = aleatório).
    :param intensidade: 0.0–1.0 (padrão 0.6) — força do envelhecimento.
    :param tipo_textura: um de SAFE_TEX_TYPES ou "random" (sorteado com a seed).
    :param dpi: resolução do PDF de saída (padrão 150, igual ao pypen).
    :return: caminho do PDF texturizado criado.
    """
    _exigir_augraphy()
    entrada = Path(entrada)
    if not entrada.exists():
        raise FileNotFoundError(f"PDF não encontrado: {entrada}")

    intensidade = min(1.0, max(0.0, float(intensidade)))
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

    # 2) camada de papel texturizado (canvas branco -> textura)
    _semeiar(seed)
    papel = _camada_papel((larg, alt), tipo, rng)

    # 3) recompor a página original (tinta com cor e anti-alias intactos)
    #    sobre o papel texturizado: tinta sólida opaca, bordas mescladas.
    alfa = np.clip((210.0 - lum) / (210.0 - 80.0), 0.0, 1.0)[..., None]
    pagina2 = (papel.astype(float) * (1.0 - alfa) + orig * alfa).astype("uint8")

    # 4) efeito de tinta: bleed (tinta "esmaga" o papel, como caneta de verdade)
    _semeiar(seed)
    if intensidade > 0:
        pagina2 = _aplicar(
            augraphy.InkBleed(
                intensity_range=(0.2, 0.3 + 0.4 * intensidade),
                severity=(0.2, 0.3 + 0.3 * intensidade),
                p=round(0.9 * intensidade, 4),
            ),
            pagina2,
        )

    # 5) envelhecimento: manchas + brilho irregular + grão fino
    pagina2 = _aplicar(
        augraphy.Stains(
            stains_type="random",
            stains_blend_alpha=round(0.2 + 0.3 * intensidade, 3),
            p=round(0.7 * intensidade, 4),
        ),
        pagina2,
    )
    pagina2 = _aplicar(
        augraphy.BrightnessTexturize(
            texturize_range=(round(1 - 0.04 - 0.05 * intensidade, 3), 0.99),
            p=0.8,
        ),
        pagina2,
    )
    pagina2 = _aplicar(
        augraphy.SubtleNoise(subtle_range=max(2, int(2 + 10 * intensidade)), p=1),
        pagina2,
    )

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
        help="força do efeito de envelhecimento (0 = só textura de papel, 1 = forte)",
    )
    ap.add_argument(
        "--textura", default="random",
        help="tipo de textura: random | " + " | ".join(SAFE_TEX_TYPES),
    )
    args = ap.parse_args(argv)

    try:
        saida = texturizar_pdf(
            args.entrada, args.saida,
            seed=args.seed,
            intensidade=args.intensidade,
            tipo_textura=args.textura,
        )
    except (SystemExit, FileNotFoundError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 1
    print(f"PDF texturizado: {saida}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
