#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gera o DRE (Demonstracao do Resultado) do escritorio Wendramin Advocacia.

Le dois arquivos de dados (que voce edita, sem mexer no codigo):

  - ledger.csv     -> os numeros ja apurados de cada mes (um mes por linha)
  - contratos.csv  -> os contratos parcelados ativos, usados na projecao

E escreve o resultado em:

  - saida/DRE_Wendramin_2026.csv  -> abra no Google Sheets ou Excel

Como usar (todo mes):
  1. Apure o mes novo a partir do extrato do Astrea. O script importar_extrato.py
     ajuda nisso: ele le o texto do extrato e ja sugere a linha do ledger.
  2. Acrescente essa linha no fim do ledger.csv.
  3. Atualize contratos.csv (novos clientes, contratos que encerraram).
  4. Rode:  python3 dre/gerar_dre.py
  5. Abra o arquivo saida/DRE_Wendramin_2026.csv.

So usa a biblioteca padrao do Python (nao precisa instalar nada).
"""
from __future__ import annotations

import csv
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LEDGER = RAIZ / "ledger.csv"
CONTRATOS = RAIZ / "contratos.csv"
SAIDA = RAIZ / "saida" / "DRE_Wendramin_2026.csv"

MESES_PT = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
            7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}

# Categorias de despesa, na ordem em que aparecem no DRE.
# (chave no ledger.csv, rotulo exibido no DRE)
CATEGORIAS = [
    ("desp_andrieli", "  Andrieli (assessoria + repasses)"),
    ("desp_marketing", "  Marketing e cursos"),
    ("desp_software", "  Software / TI / Site"),
    ("desp_impostos", "  Impostos e taxas"),
    ("desp_contabilidade", "  Contabilidade"),
    ("desp_energia", "  Energia eletrica"),
    ("desp_telefone", "  Telefone"),
    ("desp_custas", "  Custas e suprimentos"),
]

# Quantos meses projetar para a frente.
MESES_PROJECAO = 6


def brl(valor: str) -> float:
    """Converte texto numerico do CSV em float (aceita virgula ou ponto)."""
    valor = (valor or "0").strip()
    if not valor:
        return 0.0
    # Se vier no formato brasileiro "1.325,00", normaliza.
    if "," in valor:
        valor = valor.replace(".", "").replace(",", ".")
    return float(valor)


def rotulo_mes(aaaa_mm: str) -> str:
    ano, mes = aaaa_mm.split("-")
    return f"{MESES_PT[int(mes)]}/{ano[2:]}"


def proximo_mes(aaaa_mm: str) -> str:
    ano, mes = (int(x) for x in aaaa_mm.split("-"))
    mes += 1
    if mes > 12:
        mes = 1
        ano += 1
    return f"{ano:04d}-{mes:02d}"


def ler_ledger() -> list[dict]:
    linhas = []
    with open(LEDGER, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("mes") or "").strip():
                continue
            registro = {"mes": row["mes"].strip()}
            for chave, valor in row.items():
                if chave == "mes" or chave is None:
                    continue
                registro[chave] = brl(valor)
            linhas.append(registro)
    linhas.sort(key=lambda r: r["mes"])
    return linhas


def ler_contratos() -> list[dict]:
    contratos = []
    with open(CONTRATOS, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("cliente") or "").strip():
                continue
            contratos.append({
                "cliente": row["cliente"].strip(),
                "valor": brl(row["valor_mensal"]),
                "fim": row["mes_fim"].strip(),
            })
    return contratos


def entradas(m: dict) -> float:
    return m["receita_contratual"] + m["receita_sucumbencial"]


def saidas(m: dict) -> float:
    return sum(m[chave] for chave, _ in CATEGORIAS)


def f(x: float) -> str:
    """Formata numero com 2 casas e ponto decimal (padrao CSV)."""
    return f"{x:.2f}"


def gerar():
    meses = ler_ledger()
    contratos = ler_contratos()
    if not meses:
        raise SystemExit("ledger.csv esta vazio. Adicione pelo menos um mes.")

    rotulos = [rotulo_mes(m["mes"]) for m in meses]
    linhas: list[list[str]] = []

    def L(*campos):
        linhas.append([str(c) for c in campos])

    # ---- Cabecalho -------------------------------------------------------
    L("DRE - WENDRAMIN ADVOCACIA")
    L("Gerado automaticamente por dre/gerar_dre.py | Valores em R$ | Regime de competencia")
    L("")

    # ---- DRE MENSAL ------------------------------------------------------
    L("=== DRE MENSAL ===")
    L("ITEM", *rotulos, "TOTAL")

    def linha_valores(rotulo, func):
        vals = [func(m) for m in meses]
        L(rotulo, *[f(v) for v in vals], f(sum(vals)))

    linha_valores("RECEITA BRUTA DE HONORARIOS", entradas)
    linha_valores("  Honorarios contratuais e avulsos", lambda m: m["receita_contratual"])
    linha_valores("  Honorarios sucumbenciais", lambda m: m["receita_sucumbencial"])
    linha_valores("(-) DESPESAS TOTAIS", saidas)
    for chave, rotulo in CATEGORIAS:
        linha_valores(rotulo, lambda m, k=chave: m[k])
    linha_valores("= RESULTADO DO MES", lambda m: entradas(m) - saidas(m))

    # Margem liquida por mes
    margens = []
    for m in meses:
        ent = entradas(m)
        margens.append((entradas(m) - saidas(m)) / ent * 100 if ent else 0)
    total_ent = sum(entradas(m) for m in meses)
    total_res = sum(entradas(m) - saidas(m) for m in meses)
    margem_total = total_res / total_ent * 100 if total_ent else 0
    L("Margem liquida (%)", *[f"{x:.1f}%" for x in margens], f"{margem_total:.1f}%")

    L("")

    # ---- INDICADORES -----------------------------------------------------
    n = len(meses)
    L("=== INDICADORES (media mensal do periodo) ===")
    L("Receita media mensal", f(total_ent / n))
    L("Despesa media mensal", f(sum(saidas(m) for m in meses) / n))
    L("Resultado medio mensal", f(total_res / n))
    L("Honorarios a receber (lancados e nao recebidos no ultimo mes)",
      f(meses[-1]["nao_recebido"]))
    L("")

    # ---- PROJECAO --------------------------------------------------------
    sucumb_media = sum(m["receita_sucumbencial"] for m in meses) / n
    despesa_media = sum(saidas(m) for m in meses) / n

    L("=== PROJECAO PROXIMOS MESES ===")
    L("Contratual = soma dos contratos ativos (contratos.csv) que ainda nao encerraram")
    L(f"Sucumbenciais = media historica (R$ {f(sucumb_media)}/mes) | Despesa = media historica (R$ {f(despesa_media)}/mes)")

    meses_proj = []
    mref = meses[-1]["mes"]
    for _ in range(MESES_PROJECAO):
        mref = proximo_mes(mref)
        meses_proj.append(mref)
    rot_proj = [rotulo_mes(m) for m in meses_proj]

    L("ITEM", *rot_proj)

    contratual_proj = []
    for mp in meses_proj:
        total = sum(c["valor"] for c in contratos if c["fim"] >= mp)
        contratual_proj.append(total)
    L("Honorarios contratuais (contratos atuais)", *[f(v) for v in contratual_proj])
    L("Honorarios sucumbenciais (media)", *[f(sucumb_media) for _ in meses_proj])
    receita_proj = [c + sucumb_media for c in contratual_proj]
    L("RECEITA PROJETADA", *[f(v) for v in receita_proj])
    L("(-) Despesas estimadas (media)", *[f(despesa_media) for _ in meses_proj])
    L("= RESULTADO PROJETADO", *[f(v - despesa_media) for v in receita_proj])
    L("")
    L("Obs: projecao conservadora - considera apenas contratos que voce JA tem.")
    L("Com a entrada de clientes novos (tendencia do periodo), a receita tende a ser maior.")
    L("")

    # ---- CONTRATOS ATIVOS ------------------------------------------------
    L("=== CONTRATOS ATIVOS (fonte da projecao) ===")
    L("CLIENTE", "Valor/mes", "Encerra em")
    for c in sorted(contratos, key=lambda x: -x["valor"]):
        L(c["cliente"], f(c["valor"]), rotulo_mes(c["fim"]))

    # ---- Escrita ---------------------------------------------------------
    SAIDA.parent.mkdir(parents=True, exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8", newline="") as out:
        csv.writer(out).writerows(linhas)

    # ---- Resumo no terminal ---------------------------------------------
    print(f"DRE gerado: {SAIDA}")
    print(f"Meses no ledger: {len(meses)} ({rotulos[0]} a {rotulos[-1]})")
    print(f"Receita total:   R$ {f(total_ent)}")
    print(f"Despesa total:   R$ {f(sum(saidas(m) for m in meses))}")
    print(f"Resultado total: R$ {f(total_res)}  (margem {margem_total:.1f}%)")


if __name__ == "__main__":
    gerar()
