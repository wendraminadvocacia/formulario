#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Le o texto de um "Extrato de lancamentos" do Astrea e sugere a linha do mes
para voce colar no ledger.csv.

Como usar:
  1. No Astrea, abra o Extrato de lancamentos do mes e copie o texto
     (ou exporte o PDF e copie o texto dele).
  2. Salve esse texto em um arquivo, por exemplo:  dre/extratos/2026-07.txt
  3. Rode:
        python3 dre/importar_extrato.py dre/extratos/2026-07.txt
  4. O script mostra os totais, a divisao por categoria e uma LINHA pronta
     para colar no fim do ledger.csv. Ele tambem confere se as somas batem
     com o total de saidas do proprio extrato (linha "OK"/"DIFERENCA").

Importante: este script e um ASSISTENTE. Os totais de entradas/saidas vem
direto do rodape do Astrea (sao exatos). A divisao por categoria e feita por
palavras-chave; confira antes de colar, principalmente em meses atipicos.

So usa a biblioteca padrao do Python.
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

# Palavras-chave por categoria, em ordem de prioridade.
REGRAS = [
    ("desp_andrieli", ["assessoria", "repasse andri", "andri repasse"]),
    ("desp_contabilidade", ["contabilidade", "contador", "ademir pinto"]),
    ("desp_energia", ["luz", "celesc", "energia"]),
    ("desp_telefone", ["telefone", "oi fixo", "datora"]),
    ("desp_software", ["software", "astrea", "google", "wix", "nic.br",
                        "registro de site", "plano google", "site escritorio"]),
    ("desp_marketing", ["mentoria", "curso", "formacao em direito", "hotmart",
                         "marketing", "ingresso"]),
    ("desp_impostos", ["iss", "anuidade", "oab", "alvara", "dare", "darf",
                        "imposto", "taxa", "gps", "inss", "tarifas", "prefeitura"]),
    ("desp_custas", ["custas", "tonner", "suprimento", "cartorio"]),
]

ORDEM_LEDGER = ["receita_contratual", "receita_sucumbencial",
                "desp_andrieli", "desp_marketing", "desp_software",
                "desp_impostos", "desp_contabilidade", "desp_energia",
                "desp_telefone", "desp_custas", "nao_recebido"]


def sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn").lower()


def brl(s: str) -> float:
    return float(s.replace(".", "").replace(",", "."))


def classificar(janela_sem_acento: str) -> str:
    for chave, palavras in REGRAS:
        if any(p in janela_sem_acento for p in palavras):
            return chave
    return "desp_outros"


def parse(texto: str) -> dict:
    # Normaliza escapes que aparecem quando o texto vem de PDF/markdown.
    t = texto.replace("\\-", "-").replace("\\#", "#").replace("\\*", "*")

    # --- Totais do rodape (exatos) ---
    def achar_ultimo(padrao):
        achados = re.findall(padrao, t, re.I)
        return brl(achados[-1]) if achados else None

    entradas = achar_ultimo(r"Total de entradas no per[ií]odo\s*R\$\s*([\d.]+,\d{2})")
    saidas = achar_ultimo(r"Total de sa[ií]das no per[ií]odo\s*-?\s*R\$\s*([\d.]+,\d{2})")
    saldo = achar_ultimo(r"\bSaldo\s*R\$\s*([\d.]+,\d{2})")

    # Corpo = tudo antes do rodape "Total de entradas".
    corte = t.lower().find("total de entradas")
    corpo = t[:corte] if corte != -1 else t

    # Divide o corpo em blocos, um por lancamento (cada lancamento comeca com
    # uma data DD/MM/AAAA). Classificar dentro do bloco evita que a descricao
    # de um lancamento "vaze" para o vizinho.
    blocos = re.split(r"(?=\d{2}/\d{2}/\d{4})", corpo)

    categorias = {chave: 0.0 for chave, _ in REGRAS}
    categorias["desp_outros"] = 0.0
    sucumbencial = 0.0
    nao_recebido = 0.0

    for bloco in blocos:
        if not bloco.strip():
            continue
        bloco_sa = sem_acento(bloco)

        # Despesas: valores negativos do bloco, classificados pelo texto do bloco.
        negativos = re.findall(r"-\s*R\$\s*([\d.]+,\d{2})", bloco)
        if negativos:
            chave = classificar(bloco_sa)
            for v in negativos:
                categorias[chave] += brl(v)

        # Honorarios sucumbenciais: bloco com a palavra e um valor positivo.
        if "sucumbenc" in bloco_sa:
            mm = re.search(r"(?<!-)R\$\s*([\d.]+,\d{2})", bloco)
            if mm:
                sucumbencial += brl(mm.group(1))

        # Honorarios lancados e nao recebidos (receita ainda nao realizada).
        if "nao recebido" in bloco_sa:
            mm = re.search(r"(?<!-)R\$\s*([\d.]+,\d{2})", bloco)
            if mm:
                nao_recebido += brl(mm.group(1))

    contratual = (entradas - sucumbencial) if entradas is not None else None

    return {
        "entradas": entradas, "saidas": saidas, "saldo": saldo,
        "receita_sucumbencial": sucumbencial,
        "receita_contratual": contratual,
        "nao_recebido": nao_recebido,
        "categorias": categorias,
    }


def mes_do_nome(caminho: Path) -> str:
    m = re.search(r"(20\d{2})[-_]?(\d{2})", caminho.stem)
    return f"{m.group(1)}-{m.group(2)}" if m else "AAAA-MM"


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        raise SystemExit("Informe o arquivo do extrato. Ex.: python3 dre/importar_extrato.py dre/extratos/2026-07.txt")

    caminho = Path(sys.argv[1])
    dados = parse(caminho.read_text(encoding="utf-8"))
    mes = mes_do_nome(caminho)

    cats = dados["categorias"]
    soma_cat = sum(cats.values())

    print(f"\n=== Extrato lido: {caminho.name}  (mes {mes}) ===")
    print(f"Total de entradas (Astrea): R$ {dados['entradas']:.2f}")
    print(f"Total de saidas   (Astrea): R$ {dados['saidas']:.2f}")
    if dados["saldo"] is not None:
        print(f"Saldo no extrato:           R$ {dados['saldo']:.2f}")
    print()
    print(f"  Receita contratual/avulsa: R$ {dados['receita_contratual']:.2f}")
    print(f"  Receita sucumbencial:      R$ {dados['receita_sucumbencial']:.2f}")
    print(f"  A receber (nao recebido):  R$ {dados['nao_recebido']:.2f}")
    print()
    print("  Despesas por categoria:")
    for chave, _ in REGRAS:
        print(f"    {chave:22s} R$ {cats[chave]:.2f}")
    if cats["desp_outros"]:
        print(f"    {'desp_outros':22s} R$ {cats['desp_outros']:.2f}  <- nao classificado, revisar")
    print()

    # Conferencia: soma das categorias x total de saidas do Astrea.
    if dados["saidas"] is not None:
        dif = soma_cat - dados["saidas"]
        if abs(dif) < 0.01:
            print(f"  CONFERENCIA DESPESAS: OK (soma {soma_cat:.2f} = total Astrea {dados['saidas']:.2f})")
        else:
            print(f"  CONFERENCIA DESPESAS: DIFERENCA de R$ {dif:.2f} "
                  f"(soma categorias {soma_cat:.2f} x total Astrea {dados['saidas']:.2f}) - revisar")

    # Linha pronta para o ledger (desp_outros entra junto de custas, se houver).
    valores = dict(dados["categorias"])
    valores["desp_custas"] += valores.pop("desp_outros", 0.0)
    linha = {
        "receita_contratual": dados["receita_contratual"],
        "receita_sucumbencial": dados["receita_sucumbencial"],
        "nao_recebido": dados["nao_recebido"],
    }
    linha.update(valores)
    campos = [mes] + [f"{linha[c]:.2f}" for c in ORDEM_LEDGER]
    print("\n  >>> LINHA PARA COLAR NO ledger.csv:")
    print("  " + ",".join(campos))
    print()


if __name__ == "__main__":
    main()
