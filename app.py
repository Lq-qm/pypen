#!/usr/bin/env python3
"""pypen — interface gráfica (Gradio).

Escreva um texto, escolha fonte, cores e veja o resultado **ao vivo** —
liso e texturizado — e baixe a imagem da página pela própria caixa de pré-visualização.

Executar:
    .venv/bin/python app.py        # abre em http://127.0.0.1:7860
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import gradio as gr

import pypen
from pypen import DPI, FONT_PRESETS, PAPERS

# --- textos e opções -------------------------------------------------------------

RAIZ = Path(__file__).resolve().parent
EXEMPLO = (RAIZ / "exemplo.txt").read_text(encoding="utf-8")

# (rótulo no dropdown, chave do preset em pypen.FONT_PRESETS)
# ordem: caneta → cursivas → medievais
FONT_OPTIONS = [
    ("manuscrita — Patrick Hand (caneta)", "manuscrita"),
    ("kalam — caneta, traço grosso", "kalam"),
    ("cursiva — Caveat (casual)", "cursiva"),
    ("dancing — Dancing Script (fluida)", "dancing"),
    ("tangerine — Tangerine (fina)", "tangerine"),
    ("indie — Indie Flower (despojada)", "indie"),
    ("sacramento — Sacramento (elegante)", "sacramento"),
    ("allura — caligráfica", "allura"),
    ("great vibes — caligráfica fina", "great-vibes"),
    ("medieval — MedievalSharp", "medieval"),
    ("uncial — Uncial Antiqua (séculos 4–8)", "uncial"),
    ("fraktur — UnifrakturMaguntia (blackletter)", "fraktur"),
    ("fraktur bold — UnifrakturCook", "fraktur-bold"),
    ("almendra — serifa antiga", "almendra"),
    ("im fell — livro do séc. XVII", "im-fell"),
    ("gótica — Grenze Gotisch", "gotica"),
]

def render_page(
    texto: str,
    fonte: str,
    cor_papel: str,
    cor_tinta: str,
    tamanho: float,
    formato: str,
    margem: float,
    seed: int | None,
    jitter: bool,
) -> "pypen.Image.Image":
    """Gera a página como imagem RGB (o que aparece na pré-visualização)."""
    font_path = RAIZ / FONT_PRESETS[fonte]
    img, _, _ = pypen.render(
        texto or "",
        font_path=font_path,
        size=int(tamanho),
        page=PAPERS[formato],
        margin=int(margem),
        ink=pypen.parse_color(cor_tinta or "2b3a67", "cor da tinta"),
        background=pypen.parse_color(cor_papel or "ffffff", "cor do papel", exemplo="f5f1e8"),
        seed=int(seed) if seed not in (None, "") else None,
        jitter=bool(jitter),
    )
    return img


def preview_texturizado(
    texto: str,
    fonte: str,
    cor_papel: str,
    cor_tinta: str,
    tamanho: float,
    formato: str,
    margem: float,
    seed: int | None,
    jitter: bool,
    tipo_textura: str,
    tom_papel: str,
    intensidade: float,
) -> tuple["pypen.Image.Image", str]:
    """Gera a pré-visualização texturizada (imagem + mensagem de status).

    Sem augraphy, devolve a imagem lisa + aviso (não quebra a interface).
    """
    import textura  # módulo local; opcional
    img = render_page(texto, fonte, cor_papel, cor_tinta, tamanho, formato, margem, seed, jitter)
    fd, bruto = tempfile.mkstemp(suffix=".pdf", prefix="pypen-")
    os.close(fd)
    img.save(bruto, format="PDF", resolution=DPI)
    fd2, final = tempfile.mkstemp(suffix=".pdf", prefix="pypen-texturizado-")
    os.close(fd2)
    try:
        textura.texturizar_pdf(
            bruto, final,
            seed=seed,
            intensidade=intensidade,
            tipo_textura=tipo_textura,
            tom=tom_papel,
        )
    except SystemExit as e:
        return img, (
            "<span style='color:#b45309'>⚠️ ", str(e),
            " — exibindo a versão <b>sem</b> textura.</span>"
        )
    tex = textura.extrair_pagina(final)
    return tex, "<span style='color:#15803d'>✔ pré-visualização texturizada atualizada</span>"


# --- interface --------------------------------------------------------------------

def load_demo() -> gr.Blocks:
    with gr.Blocks(title="pypen — do texto ao PDF manuscrito") as demo:
        gr.Markdown(
            "# ✒️ pypen — texto → PDF com cara de escrita à mão\n\n"
            "Escreva (ou cole) o texto à esquerda e o resultado aparece **ao vivo** ao lado.\n"
            "Há duas caixas de pré-visualização: a página **lisa** e a versão **texturizada**\n"
            "(papel e tinta realistas). Quando estiver satisfeito, use o botão de download\n"
            "de cada caixa para salvar a imagem da página."
        )
        with gr.Row(equal_height=False):
            with gr.Column(scale=5):
                texto = gr.Textbox(
                    value=EXEMPLO,
                    label="Texto",
                    lines=12,
                    placeholder="Escreva aqui o texto que vai para o PDF…",
                )
                fonte = gr.Dropdown(
                    choices=FONT_OPTIONS,
                    value="manuscrita",
                    label="Fonte",
                )
                with gr.Row():
                    cor_papel = gr.ColorPicker(value="#ffffff", label="Cor do papel")
                    cor_tinta = gr.ColorPicker(value="#2b3a67", label="Cor da tinta")
                tamanho = gr.Slider(14, 80, value=34, step=1, label="Tamanho da fonte (px)")
                with gr.Row():
                    formato = gr.Radio(["a4", "letter"], value="a4", label="Tamanho do papel")
                    margem = gr.Slider(30, 200, value=90, step=5, label="Margem (px)")
                with gr.Row():
                    seed = gr.Number(
                        value=7,
                        precision=0,
                        label="Seed (deixe vazio para aleatório)",
                        scale=2,
                    )
                    jitter = gr.Checkbox(
                        value=True,
                        label="Efeito manuscrito (tremor e rotação)",
                        scale=1,
                    )
                with gr.Row():
                    tipo_textura = gr.Dropdown(
                        choices=["random", "normal", "rough_stains", "fine_stains",
                                "light_stains", "curvy_edge"],
                        value="random",
                        label="Textura: tipo do papel",
                    )
                    tom_papel = gr.Dropdown(
                        choices=["neutro", "creme", "sepia", "azulado"],
                        value="neutro",
                        label="Textura: tom do papel",
                    )
                intensidade = gr.Slider(
                    0, 1, value=0.6, step=0.05,
                    label="Textura: intensidade (0 = só papel, 1 = envelhecido)",
                )
                btn_preview_tex = gr.Button(
                    "👀 Atualizar pré-visualização texturizada",
                    variant="secondary",
                )

            with gr.Column(scale=4):
                preview = gr.Image(
                    value=render_page(EXEMPLO, "manuscrita", "#ffffff", "#2b3a67", 34, "a4", 90, 7, True),
                    type="pil",
                    label="Liso (ao vivo)",
                    height=560,
                )
                preview_tex = gr.Image(
                    type="pil",
                    label="Texturizado (augraphy)",
                    height=560,
                )
                status_tex = gr.HTML("")

        all_inputs = [texto, fonte, cor_papel, cor_tinta, tamanho, formato, margem, seed, jitter]
        for comp in all_inputs:
            comp.change(render_page, inputs=all_inputs, outputs=preview, api_name="/render")
        inputs_tex = all_inputs + [tipo_textura, tom_papel, intensidade]
        btn_preview_tex.click(
            preview_texturizado,
            inputs=inputs_tex,
            outputs=[preview_tex, status_tex],
            api_name="/preview-texturizado",
        )
        # preenche a pré-visualização texturizada assim que a página abre
        demo.load(
            preview_texturizado,
            inputs=inputs_tex,
            outputs=[preview_tex, status_tex],
        )

    return demo


demo = load_demo()

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=gr.themes.Soft(),
    )
