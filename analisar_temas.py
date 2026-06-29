#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analisador dos Temas 6 e 1234 do STF (ações de fornecimento de medicamentos).

O que faz, em ordem:
  1. Carrega a base estruturada das teses (temas_stf/temas.yaml), onde cada
     requisito/critério ("item") tem termos e padrões de detecção.
  2. Lê os documentos de um caso concreto a partir de uma pasta
     (padrão: documentos/). Aceita .txt, .md, .pdf e .docx.
  3. Para cada item da tese, procura no texto dos documentos evidências de que
     aquele requisito está demonstrado e classifica o status:
        ✅ atendido        — evidência forte
        ⚠️ indício         — alguma evidência, conferir
        ❌ não localizado  — nenhuma evidência encontrada
        📋 manual          — item que depende de conferência humana
  4. Para o Tema 1234, tenta calcular a competência (custo anual x 210 salários
     mínimos) quando encontra valores monetários nos documentos.
  5. Gera um relatório de PREENCHIMENTO dos requisitos em analises/ (um .md por
     tema), com os trechos encontrados e a orientação de prova de cada item.

Uso:
  python analisar_temas.py                       # analisa documentos/ p/ os 2 temas
  python analisar_temas.py --docs ./caso_joao    # outra pasta de documentos
  python analisar_temas.py --tema 6              # só o Tema 6
  python analisar_temas.py --tema 1234           # só o Tema 1234
  python analisar_temas.py --custo-anual 250000  # informa o custo anual (R$) p/ competência

IMPORTANTE: esta ferramenta faz uma TRIAGEM assistida por palavras-chave. Não
substitui a análise jurídica nem a leitura integral das teses e dos documentos.
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
from datetime import datetime, timezone, timedelta
from pathlib import Path

import yaml

# --------------------------------------------------------------------------- #
# Caminhos e constantes
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parent
BASE_TEMAS = RAIZ / "temas_stf" / "temas.yaml"
DIR_DOCS = RAIZ / "documentos"
DIR_ANALISES = RAIZ / "analises"

FUSO_BR = timezone(timedelta(hours=-3))

EXTS_TEXTO = {".txt", ".md", ".markdown", ".csv"}
EXT_PDF = ".pdf"
EXT_DOCX = ".docx"

# Limiar (nº de termos distintos encontrados) para considerar "atendido".
LIMIAR_ATENDIDO = 2


# --------------------------------------------------------------------------- #
# Utilidades de texto
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    agora = datetime.now(FUSO_BR).strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


def normalizar(texto: str) -> str:
    """Tira acentos e deixa minúsculo, para a busca ignorar acentuação."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def trecho_contexto(texto: str, pos: int, raio: int = 90) -> str:
    """Devolve um pequeno trecho ao redor de uma posição, para evidência."""
    ini = max(0, pos - raio)
    fim = min(len(texto), pos + raio)
    bruto = texto[ini:fim].replace("\n", " ")
    bruto = re.sub(r"\s+", " ", bruto).strip()
    prefixo = "…" if ini > 0 else ""
    sufixo = "…" if fim < len(texto) else ""
    return f"{prefixo}{bruto}{sufixo}"


# --------------------------------------------------------------------------- #
# Leitura de documentos
# --------------------------------------------------------------------------- #

def ler_pdf(caminho: Path) -> str:
    """Lê texto de um PDF. Usa pypdf se disponível; senão avisa e retorna ''."""
    try:
        from pypdf import PdfReader
    except Exception:
        try:
            from PyPDF2 import PdfReader  # alternativa
        except Exception:
            log(f"  ⚠️  {caminho.name}: instale 'pypdf' para ler PDFs "
                f"(pip install pypdf). Pulando.")
            return ""
    try:
        leitor = PdfReader(str(caminho))
        partes = [(p.extract_text() or "") for p in leitor.pages]
        return "\n".join(partes)
    except Exception as e:
        log(f"  ⚠️  {caminho.name}: falha ao ler PDF ({e}).")
        return ""


def ler_docx(caminho: Path) -> str:
    """Lê texto de um .docx. Usa python-docx se disponível."""
    try:
        import docx  # python-docx
    except Exception:
        log(f"  ⚠️  {caminho.name}: instale 'python-docx' para ler .docx "
            f"(pip install python-docx). Pulando.")
        return ""
    try:
        documento = docx.Document(str(caminho))
        return "\n".join(p.text for p in documento.paragraphs)
    except Exception as e:
        log(f"  ⚠️  {caminho.name}: falha ao ler .docx ({e}).")
        return ""


def carregar_documentos(pasta: Path) -> list[dict]:
    """Lê todos os documentos suportados da pasta. Devolve [{nome, texto}]."""
    if not pasta.exists():
        log(f"Pasta de documentos não encontrada: {pasta}")
        return []

    docs: list[dict] = []
    for caminho in sorted(pasta.rglob("*")):
        if not caminho.is_file():
            continue
        if caminho.name.upper() == "README.MD":
            continue
        ext = caminho.suffix.lower()
        texto = ""
        if ext in EXTS_TEXTO:
            texto = caminho.read_text(encoding="utf-8", errors="ignore")
        elif ext == EXT_PDF:
            texto = ler_pdf(caminho)
        elif ext == EXT_DOCX:
            texto = ler_docx(caminho)
        else:
            continue
        if texto.strip():
            docs.append({"nome": caminho.name, "texto": texto})
            log(f"  • lido: {caminho.name} ({len(texto)} caracteres)")
        else:
            log(f"  • vazio/ilegível: {caminho.name}")
    return docs


# --------------------------------------------------------------------------- #
# Análise de um item (requisito) contra o texto dos documentos
# --------------------------------------------------------------------------- #

def analisar_item(item: dict, texto_norm: str, texto_bruto: str) -> dict:
    """
    Procura, no texto dos documentos, evidências do requisito 'item'.
    Devolve dict com status, termos encontrados e trechos de evidência.
    """
    det = item.get("deteccao", {}) or {}
    termos = det.get("termos", []) or []
    padroes = det.get("padroes", []) or []

    encontrados: list[str] = []
    evidencias: list[str] = []

    for termo in termos:
        chave = normalizar(termo)
        if not chave:
            continue
        pos = texto_norm.find(chave)
        if pos != -1:
            encontrados.append(termo)
            evidencias.append(trecho_contexto(texto_bruto, pos))

    for padrao in padroes:
        try:
            m = re.search(padrao, texto_norm, flags=re.IGNORECASE)
        except re.error:
            continue
        if m:
            encontrados.append(f"/{padrao}/")
            evidencias.append(trecho_contexto(texto_bruto, m.start()))

    # Classificação do status.
    n = len(set(encontrados))
    if item.get("tipo") == "procedimento" and n == 0:
        status = "manual"
    elif n >= LIMIAR_ATENDIDO:
        status = "atendido"
    elif n == 1:
        status = "indicio"
    else:
        status = "nao_localizado"

    return {
        "id": item["id"],
        "status": status,
        "encontrados": sorted(set(encontrados)),
        "evidencias": evidencias[:3],   # no máximo 3 trechos por item
    }


# --------------------------------------------------------------------------- #
# Cálculo de competência (Tema 1234)
# --------------------------------------------------------------------------- #

RX_VALOR = re.compile(
    r"r\$\s*([\d\.]{1,12},\d{2})", flags=re.IGNORECASE
)


def extrair_valores_reais(texto_bruto: str) -> list[float]:
    """Extrai valores monetários no formato R$ 1.234,56 e devolve floats."""
    valores: list[float] = []
    for m in RX_VALOR.finditer(texto_bruto):
        bruto = m.group(1).replace(".", "").replace(",", ".")
        try:
            valores.append(float(bruto))
        except ValueError:
            continue
    return valores


def avaliar_competencia(custo_anual: float, parametros: dict) -> dict:
    """Compara o custo anual com o limiar de 210 salários mínimos."""
    sm = float(parametros.get("salario_minimo", 0) or 0)
    fator = float(parametros.get("fator_competencia_federal", 210) or 210)
    limiar = sm * fator
    federal = custo_anual >= limiar if limiar else None
    return {
        "custo_anual": custo_anual,
        "salario_minimo": sm,
        "fator": fator,
        "limiar": limiar,
        "competencia": (
            "Justiça Federal (União no polo passivo)"
            if federal else "Justiça Estadual"
        ) if limiar else "indefinida (configure o salário mínimo)",
        "federal": federal,
    }


# --------------------------------------------------------------------------- #
# Relatório de preenchimento
# --------------------------------------------------------------------------- #

ICONE = {
    "atendido": "✅",
    "indicio": "⚠️",
    "nao_localizado": "❌",
    "manual": "📋",
}
ROTULO = {
    "atendido": "Atendido",
    "indicio": "Indício (conferir)",
    "nao_localizado": "Não localizado",
    "manual": "Conferência manual",
}


def montar_relatorio(tema: dict, resultados: list[dict], docs: list[dict],
                     competencia: dict | None) -> str:
    L: list[str] = []
    num = tema["numero"]
    L.append(f"# Preenchimento dos requisitos — Tema {num} do STF")
    L.append("")
    L.append(f"**{tema['titulo'].strip()}**")
    L.append("")
    L.append(f"- Leading case: {tema.get('leading_case', '—')}")
    L.append(f"- Situação: {tema.get('situacao', '—')}")
    L.append(f"- Fonte oficial: {tema.get('fonte_oficial', '—')}")
    gerado = datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")
    L.append(f"- Gerado em: {gerado} (horário de Brasília)")
    L.append("")

    if docs:
        L.append(f"**Documentos analisados ({len(docs)}):** "
                 + ", ".join(d["nome"] for d in docs))
    else:
        L.append("> ⚠️ Nenhum documento foi analisado — coloque arquivos em "
                 "`documentos/` (.txt, .md, .pdf, .docx).")
    L.append("")

    # Placar.
    contagem: dict[str, int] = {}
    for r in resultados:
        contagem[r["status"]] = contagem.get(r["status"], 0) + 1
    placar = " · ".join(
        f"{ICONE[s]} {ROTULO[s]}: {contagem.get(s, 0)}"
        for s in ("atendido", "indicio", "nao_localizado", "manual")
    )
    L.append(f"**Placar:** {placar}")
    L.append("")

    # Cálculo de competência (Tema 1234).
    if competencia is not None:
        L.append("## Competência (critério dos 210 salários mínimos)")
        L.append("")
        if competencia.get("limiar"):
            L.append(f"- Custo anual considerado: R$ {competencia['custo_anual']:,.2f}"
                     .replace(",", "X").replace(".", ",").replace("X", "."))
            L.append(f"- Salário mínimo de referência: R$ {competencia['salario_minimo']:,.2f}"
                     .replace(",", "X").replace(".", ",").replace("X", "."))
            L.append(f"- Limiar (210 SM): R$ {competencia['limiar']:,.2f}"
                     .replace(",", "X").replace(".", ",").replace("X", "."))
            L.append(f"- **Competência provável: {competencia['competencia']}**")
            L.append("")
            L.append("> Valor obtido automaticamente dos documentos ou informado "
                     "via `--custo-anual`. Confirme o custo anual pelo PMVG/CMED.")
        else:
            L.append("> Configure `parametros.salario_minimo` em "
                     "`temas_stf/temas.yaml` para calcular a competência.")
        L.append("")

    # Itens.
    L.append("## Requisitos / itens da tese")
    L.append("")
    res_por_id = {r["id"]: r for r in resultados}
    for item in tema["itens"]:
        r = res_por_id[item["id"]]
        ic = ICONE[r["status"]]
        alinea = f" ({item['alinea']})" if item.get("alinea") else ""
        obrig = "obrigatório" if item.get("obrigatorio") else "complementar"
        L.append(f"### {ic} {item['id']}{alinea} — {item['titulo']}")
        L.append(f"*Status: {ROTULO[r['status']]} · {obrig}*")
        L.append("")
        L.append(item["descricao"].strip())
        L.append("")
        L.append(f"**Prova típica:** {item.get('prova', '—').strip()}")
        L.append("")
        if r["encontrados"]:
            L.append(f"**Termos localizados:** {', '.join(r['encontrados'])}")
            L.append("")
            for ev in r["evidencias"]:
                L.append(f"> {ev}")
            L.append("")
        else:
            L.append("_Nenhuma evidência localizada nos documentos. "
                     "Providenciar/anexar a prova indicada acima._")
            L.append("")

    # Pendências obrigatórias.
    pend = [
        item for item in tema["itens"]
        if item.get("obrigatorio")
        and res_por_id[item["id"]]["status"] in ("nao_localizado", "indicio")
    ]
    L.append("## Pendências dos requisitos obrigatórios")
    L.append("")
    if pend:
        for item in pend:
            st = ROTULO[res_por_id[item["id"]]["status"]]
            L.append(f"- [ ] **{item['id']}** — {item['titulo']} ({st})")
    else:
        L.append("Todos os requisitos obrigatórios apresentam evidência. "
                 "Revisar manualmente para confirmar a suficiência.")
    L.append("")

    L.append("---")
    L.append("> Triagem automática por palavras-chave (apoio operacional). "
             "Não substitui a análise jurídica nem a leitura integral da tese "
             "e dos documentos. Confira a tese em `temas_stf/REFERENCIA_TESES.md`.")
    L.append("")
    return "\n".join(L)


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Analisador dos Temas 6 e 1234 do STF (medicamentos)."
    )
    parser.add_argument("--docs", default=str(DIR_DOCS),
                        help="Pasta com os documentos do caso (padrão: documentos/).")
    parser.add_argument("--tema", choices=["6", "1234", "todos"], default="todos",
                        help="Qual tema analisar (padrão: todos).")
    parser.add_argument("--custo-anual", type=float, default=None,
                        help="Custo anual do tratamento em R$ (para a competência "
                             "do Tema 1234). Se omitido, tenta extrair dos documentos.")
    parser.add_argument("--saida", default=str(DIR_ANALISES),
                        help="Pasta de saída dos relatórios (padrão: analises/).")
    args = parser.parse_args()

    if not BASE_TEMAS.exists():
        log(f"Base de temas não encontrada: {BASE_TEMAS}")
        return 1
    base = yaml.safe_load(BASE_TEMAS.read_text(encoding="utf-8"))
    parametros = base.get("parametros", {}) or {}
    temas = base.get("temas", []) or []

    pasta_docs = Path(args.docs)
    log(f"Lendo documentos de: {pasta_docs}")
    docs = carregar_documentos(pasta_docs)
    texto_bruto = "\n\n".join(d["texto"] for d in docs)
    texto_norm = normalizar(texto_bruto)

    # Filtra temas pedidos.
    if args.tema != "todos":
        temas = [t for t in temas if str(t["numero"]) == args.tema]

    dir_saida = Path(args.saida)
    dir_saida.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now(FUSO_BR).strftime("%Y-%m-%d_%H%M")

    for tema in temas:
        log(f"Analisando Tema {tema['numero']} ({len(tema['itens'])} itens)...")
        resultados = [analisar_item(it, texto_norm, texto_bruto) for it in tema["itens"]]

        # Competência (apenas Tema 1234, se houver item marcado).
        competencia = None
        if any(it.get("calculo_competencia") for it in tema["itens"]):
            custo = args.custo_anual
            if custo is None:
                valores = extrair_valores_reais(texto_bruto)
                custo = max(valores) if valores else 0.0
                if valores:
                    log(f"  Maior valor monetário encontrado nos documentos: "
                        f"R$ {custo:,.2f}")
            competencia = avaliar_competencia(custo or 0.0, parametros)

        relatorio = montar_relatorio(tema, resultados, docs, competencia)
        arq = dir_saida / f"tema{tema['numero']}_{carimbo}.md"
        arq.write_text(relatorio, encoding="utf-8")
        log(f"  Relatório salvo: {arq.relative_to(RAIZ)}")

        # Resumo no terminal.
        cont: dict[str, int] = {}
        for r in resultados:
            cont[r["status"]] = cont.get(r["status"], 0) + 1
        log("  Placar: " + ", ".join(
            f"{ROTULO[s]}={cont.get(s, 0)}"
            for s in ("atendido", "indicio", "nao_localizado", "manual")
        ))

    if not docs:
        log("Atenção: nenhum documento lido. Os relatórios mostram apenas os "
            "requisitos a preencher.")
    log("Concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
