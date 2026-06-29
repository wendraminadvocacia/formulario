# Pasta de documentos do caso

Coloque aqui os documentos do caso concreto que serão analisados pelo
`analisar_temas.py` (petição inicial, laudo médico, negativa administrativa,
relatório da CONITEC, comprovantes de renda, estudos científicos etc.).

**Formatos aceitos:** `.txt`, `.md`, `.pdf`, `.docx`.

> Para ler `.pdf` instale `pypdf`; para `.docx` instale `python-docx`
> (já incluídos em `requirements.txt`). Arquivos de imagem digitalizada (PDF
> escaneado sem texto) não são lidos — converta para texto/OCR antes.

Depois, na raiz do projeto, rode:

```bash
python analisar_temas.py            # analisa esta pasta para os Temas 6 e 1234
python analisar_temas.py --tema 6   # somente o Tema 6
```

Os relatórios de preenchimento dos requisitos são gravados em `analises/`.

Este `README.md` é ignorado pela análise.
