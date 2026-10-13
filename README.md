# pypen ✒️

Transforma um arquivo `.txt` em um **PDF de uma página**, com aparência de **escrita à mão**.

Cada caractere é desenhado individualmente com leve rotação, "tremor" de linha e
variação sutil de tamanho e pressão da tinta — simulando caligrafia. A única
dependência é o [Pillow](https://pillow.readthedocs.io/).

Veem embutidas **16 fontes open-source** (todas com licença [OFL 1.1](fonts/licenses/)):
caneta do dia a dia, **letras cursivas** (da casual à caligráfica) e estilos
**medievais** — uncials, blackletter (fraktur) e serifas antigas de livro.
Veja a [tabela de fontes](#fontes).

## Instalação

```bash
pip install -r requirements.txt          # CLI
pip install -r requirements-gui.txt      # interface gráfica (opcional)
```

## Interface gráfica

Com todos os controles (fonte, cores do papel e da tinta, tamanho, margem, seed) e
**pré-visualização ao vivo** — o resultado aparece na própria página enquanto você
ajusta. Há **duas caixas, uma abaixo da outra**: o PDF **liso** (atualiza ao vivo)
e, logo abaixo, a versão **texturizada** (botão “👀 Atualizar pré-visualização
texturizada”, requer augraphy).
No final, um botão baixa o PDF de uma página:

```bash
.venv/bin/python app.py        # ou: python app.py
# abra http://127.0.0.1:7860
```

## Textura realista (opcional)

O módulo **`textura.py`** é um pós-processador independente: pega o PDF que *já foi
criado* e, usando a biblioteca [augraphy](https://pypi.org/project/augraphy/), dá a ele
cara de página manuscrita de verdade — textura de papel, bleed de tinta (a caneta
“esmaga” o papel), manchas de idade e grão fino.

O núcleo do pypen **não depende** do augraphy: ele só entra em ação quando você pede.

```bash
.venv/bin/pip install -r requirements-textura.txt     # uma vez

# opção 1: tudo num comando (após gerar, texturiza o próprio PDF)
.venv/bin/python pypen.py texto.txt -o saida.pdf --textura --seed 7

# opção 2: texto → PDF → textura, em etapas
.venv/bin/python pypen.py texto.txt -o saida.pdf
.venv/bin/python textura.py saida.pdf --seed 7 --intensidade 0.8

# opção 3: na interface gráfica — pré-visualize na caixa “Texturizado” e baixe
#           pelo botão “Baixar PDF texturizado”
```

`textura.py` também é uma API Python:

```python
from textura import texturizar_pdf
texturizar_pdf("saida.pdf", "saida_texturada.pdf", seed=7, intensidade=0.6)
```

| opção | descrição |
|---|---|
| `--intensidade` | força global do envelhecimento, 0–1 (padrão 0.6) |
| `--textura` | tipo de textura do papel: `normal`, `rough_stains`, `fine_stains`, `light_stains`, `curvy_edge` ou `random` (sorteado com a seed) |
| `--tom` | cor do papel: `neutro` (padrão), `creme`, `sepia`, `azulado` |
| `--manchas` | manchas de idade — 0 desliga, 1 padrão, até 1.5 reforça |
| `--bleed` | bleed de tinta (tinta esmagada no papel) — 0 desliga, 1 padrão |
| `--grao` | grão fino do papel — 0 desliga, 1 padrão |
| `--bordas` | escurecimento das bordas (vignette), 0–1 (padrão 0.5) |
| `--luz` | gradiente de luz (papel sob lâmpada), 0–1 (padrão 0.3) |
| `--seed` | mesma seed → mesmo resultado (reprodutível) |

Cada efeito tem força **individual** — desligue o que não quiser:

```bash
# papel creme, sem manchas de idade, bordas bem marcadas
python textura.py saida.pdf --tom creme --manchas 0 --bordas 0.9

# tinta bem nítida (sem bleed), sem grão, com luz de escritório
python textura.py saida.pdf --bleed 0 --grao 0 --luz 0.5
```

> No `pypen.py` (um comando só) os atalhos são `--textura`, `--intensidade`,
> `--tipo-textura` e `--tom-papel`; para afinar cada efeito, rode o passo 2
> com `textura.py`.

## Uso

```bash
python pypen.py texto.txt                        # gera texto.pdf
python pypen.py texto.txt -o saida.pdf           # saída personalizada
python pypen.py texto.txt --size 40 --seed 7     # reproduz o mesmo "tremor"
python pypen.py texto.txt --ink 1f3a93 --paper letter
python pypen.py texto.txt --paper-color f5f1e8      # papel envelhecido
python pypen.py texto.txt --font medieval           # estilo medieval (MedievalSharp)
python pypen.py texto.txt --font fraktur --paper-color f0ead8  # blackletter, papel velho

python app.py                          # interface gráfica com pré-visualização ao vivo
```

Se o texto não couber na página, o tamanho da fonte é **reduzido automaticamente**
para caber em uma única página (até o mínimo de 10 px; além disso, o excedente é cortado).

## Opções

| opção          | padrão            | descrição                                              |
| -------------- | ----------------- | ------------------------------------------------------ |
| `input`        | —                 | arquivo `.txt` de entrada (UTF-8)                      |
| `-o/--output`  | `<entrada>.pdf`   | arquivo `.pdf` de saída                                |
| `--size`       | `34`              | tamanho da fonte em px @150 DPI                        |
| `--font`       | `manuscrita`      | preset de fonte ou caminho `.ttf`/`.otf` (ver [fontes](#fontes)) |
| `--ink`        | `2b3a67`          | cor da tinta em hex (sem `#`)                          |
| `--paper-color`| `ffffff`          | cor do papel em hex (sem `#`), ex.: `f5f1e8` = envelhecido |
| `--seed`       | aleatória         | semente p/ reproduzir exatamente a mesma página        |
| `--margin`     | `90`              | margem da página, em pixels                            |
| `--paper`      | `a4`              | `a4` ou `letter`                                       |
| `--no-jitter`  | —                 | desliga o efeito manuscrito (texto reto, para testes)  |

## Como funciona

1. O texto é quebrado em linhas que cabem na largura útil da página.
2. Cada caractere vira uma "fotografia" em `RGBA`, girada entre −4° e +4°,
   com jitter vertical e variação de 5–7% no tamanho.
3. As peças são coladas sobre a página (A4/letter em 150 DPI) e salvas como
   PDF de uma página via `Image.save(..., format="PDF")`.

Glifos ausentes na fonte principal caem automaticamente na fonte padrão do
Pillow (DejaVu). Para CJK/árabe etc., passe `--font` com uma fonte adequada.

## Fontes

Todos os presets abaixo já vêm embutidos em `fonts/` e têm cobertura completa
para o português (acentos `ã ç é õ` etc.). Licença [OFL 1.1](fonts/licenses/).

| preset         | fonte               | estilo                                     | autor(a)                    |
| -------------- | ------------------- | ------------------------------------------ | --------------------------- |
| `manuscrita`   | Patrick Hand        | caneta, dia a dia (padrão)                 | Patrick Wagesreiter         |
| `kalam`        | Kalam               | caneta, traço mais grosso                  | Indian Type Foundry         |
| `cursiva`      | Caveat              | cursiva casual, conectada                  | Caveat Project              |
| `dancing`      | Dancing Script      | cursiva fluida, semi-formal                | Dancing Script Project      |
| `tangerine`    | Tangerine           | cursiva fina                               | Toshi Omagari               |
| `indie`        | Indie Flower        | cursiva despojada                          | kimberlygeswein             |
| `sacramento`   | Sacramento          | cursiva elegante                           | Astigmatic (B. Bonislawsky) |
| `allura`       | Allura              | caligráfica, traço firme                   | Allura Project              |
| `great-vibes`  | Great Vibes         | caligráfica fina, formal                   | Great Vibes Project         |
| `medieval`     | MedievalSharp       | "medieval", arestas suaves                 | wmk69                       |
| `uncial`       | Uncial Antiqua      | uncial, manuscritos dos séculos 4–8        | Brian J. Bonislawsky        |
| `fraktur`      | UnifrakturMaguntia  | blackletter (texto gótico antigo)          | j. wust / Peter Wiegel      |
| `fraktur-bold` | UnifrakturCook      | blackletter grossa                         | j. wust / Peter Wiegel      |
| `almendra`     | Almendra            | serifa "antiga", humanista                 | Ana Sanfelippo              |
| `im-fell`      | IM FELL English     | estilo livro impresso do séc. XVII         | Igino Marini                |
| `gotica`       | Grenze Gotisch      | gótica de display, pesada                  | Omnibus-Type                |

Também é possível apontar para qualquer `.ttf`/`.otf` próprio:

```bash
python pypen.py texto.txt --font /caminho/para/Caveat.ttf
```

> Dica: para um visual de "pergaminho", combine `--font uncial` ou `fraktur`
> com `--paper-color f0ead8` e `--ink 3b2f1e`.
