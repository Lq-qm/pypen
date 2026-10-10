#!/usr/bin/env python3
"""pypen — interface gráfica (Gradio).

Escreva um texto, escolha fonte, cores e veja o resultado **ao vivo**;
depois baixe o PDF de uma página.

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
FONT_OPTIONS = [
    ("manuscrita — Patrick Hand (caneta)", "manuscrita"),
    ("kalam — caneta, traço grosso", "kalam"),
    ("medieval — MedievalSharp", "medieval"),
    ("uncial — Uncial Antiqua (séculos 4–8)", "uncial"),
    ("fraktur — UnifrakturMaguntia (blackletter)", "fraktur"),
    ("fraktur bold — UnifrakturCook", "fraktur-bold"),
    ("almendra — serifa antiga", "almendra"),
    ("im fell — livro do séc. XVII", "im-fell"),
    ("gótica — Grenze Gotisch", "gotica"),
]

# ordem fixa dos parâmetros (precisa casar com as listas `inputs`)
INPUTS = "texto, fonte, cor_papel, cor_tinta, tamanho, formato, margem, seed, jitter"


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


def baixar_pdf(
    texto: str,
    fonte: str,
    cor_papel: str,
    cor_tinta: str,
    tamanho: float,
    formato: str,
    margem: float,
    seed: int | None,
    jitter: bool,
) -> str:
    """Gera o PDF de uma página e retorna o caminho do arquivo temporário."""
    img = render_page(texto, fonte, cor_papel, cor_tinta, tamanho, formato, margem, seed, jitter)
    fd, caminho = tempfile.mkstemp(suffix=".pdf", prefix="pypen-")
    os.close(fd)
    img.save(caminho, format="PDF", resolution=DPI)
    return caminho


# --- interface --------------------------------------------------------------------

def load_demo() -> gr.Blocks:
    with gr.Blocks(title="pypen — do texto ao PDF manuscrito") as demo:
        gr.Markdown(
            "# ✒️ pypen — texto → PDF com cara de escrita à mão\n\n"
            "Escreva (ou cole) o texto à esquerda e o resultado aparece **ao vivo** ao lado. "
            "Quando estiver satisfeito, baixe o PDF de uma página."
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
                pdf_file = gr.File(label="PDF")
                btn_pdf = gr.Button("⬇️ Baixar PDF de uma página", variant="primary")

            with gr.Column(scale=4):
                preview = gr.Image(
                    value=render_page(EXEMPLO, "manuscrita", "#ffffff", "#2b3a67", 34, "a4", 90, 7, True),
                    type="pil",
                    label="Pré-visualização (ao vivo)",
                    height=640,
                )

        all_inputs = [texto, fonte, cor_papel, cor_tinta, tamanho, formato, margem, seed, jitter]
        for comp in all_inputs:
            comp.change(render_page, inputs=all_inputs, outputs=preview, api_name="/render")
        btn_pdf.click(baixar_pdf, inputs=all_inputs, outputs=pdf_file, api_name="/pdf")

    return demo


demo = load_demo()

if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=7860,
        theme=gr.themes.Soft(),
    )
