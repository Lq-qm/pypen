# pypen ✒️

Transforma um arquivo `.txt` em um **PDF de uma página**, com aparência de **escrita à mão**.

Cada caractere é desenhado individualmente com leve rotação, "tremor" de linha e
variação sutil de tamanho e pressão da tinta — simulando caligrafia. A única
dependência é o [Pillow](https://pillow.readthedocs.io/). As fontes embutidas
(**Patrick Hand** e **Kalam**) têm licença [OFL 1.1](fonts/OFL.txt).

## Instalação

```bash
pip install -r requirements.txt
```

## Uso

```bash
python pypen.py texto.txt                        # gera texto.pdf
python pypen.py texto.txt -o saida.pdf           # saída personalizada
python pypen.py texto.txt --size 40 --seed 7     # reproduz o mesmo "tremor"
python pypen.py texto.txt --ink "#1f3a93" --paper letter
python pypen.py texto.txt --paper-color "#f5f1e8"   # papel envelhecido
```

Se o texto não couber na página, o tamanho da fonte é **reduzido automaticamente**
para caber em uma única página (até o mínimo de 10 px; além disso, o excedente é cortado).

## Opções

| opção          | padrão            | descrição                                              |
| -------------- | ----------------- | ------------------------------------------------------ |
| `input`        | —                 | arquivo `.txt` de entrada (UTF-8)                      |
| `-o/--output`  | `<entrada>.pdf`   | arquivo `.pdf` de saída                                |
| `--size`       | `34`              | tamanho da fonte em px @150 DPI                        |
| `--font`       | embutida          | caminho para outra fonte `.ttf`/`.otf` (ex.: Caveat)   |
| `--ink`        | `#2b3a67`         | cor da tinta em hex                                    |
| `--paper-color`| `#ffffff`         | cor do papel em hex (ex.: `#f5f1e8` = envelhecido)     |
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
