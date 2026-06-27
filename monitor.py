#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Monitoramento diário do Diário Oficial da União (DOU) e do portal do CFM.

O que faz, em ordem:
  1. Baixa as edições do dia do DOU (seções configuradas) e as publicações
     mais recentes do CFM.
  2. Filtra as publicações ligadas a médicos e pacientes usando as
     palavras-chave do arquivo config.yaml.
  3. Remove o que já apareceu em dias anteriores (controle em estado/vistos.json),
     para você não receber repetido.
  4. Gera um relatório em relatorios/AAAA-MM-DD.md e também um .txt
     (este último é o arquivo enviado ao Google Drive).

Uso:
  python monitor.py                # usa a data de hoje (horário de Brasília)
  python monitor.py --data 27-06-2026   # força uma data específica (DD-MM-AAAA)

Este script foi feito para rodar no GitHub Actions, que tem acesso livre à
internet. Ele não depende de nenhum serviço externo além do DOU e do CFM.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timezone, timedelta
from html import unescape
from pathlib import Path

import requests
import yaml
from bs4 import BeautifulSoup

# --------------------------------------------------------------------------- #
# Caminhos e constantes
# --------------------------------------------------------------------------- #

RAIZ = Path(__file__).resolve().parent
CONFIG = RAIZ / "config.yaml"
DIR_RELATORIOS = RAIZ / "relatorios"
DIR_ESTADO = RAIZ / "estado"
ARQ_ESTADO = DIR_ESTADO / "vistos.json"

# Fuso de Brasília (UTC-3, sem horário de verão desde 2019).
FUSO_BR = timezone(timedelta(hours=-3))

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)
TIMEOUT = 90          # o DOU pode demorar a responder a seção do1 (grande)
TENTATIVAS = 3        # número de tentativas por requisição
DEBUG = os.environ.get("MONITOR_DEBUG") == "1"


# --------------------------------------------------------------------------- #
# Utilidades
# --------------------------------------------------------------------------- #

def log(msg: str) -> None:
    """Imprime no log do GitHub Actions com horário."""
    agora = datetime.now(FUSO_BR).strftime("%H:%M:%S")
    print(f"[{agora}] {msg}", flush=True)


def nova_sessao() -> requests.Session:
    sessao = requests.Session()
    sessao.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "pt-BR,pt;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    return sessao


def baixar(sessao: requests.Session, url: str):
    """Faz GET com algumas tentativas; devolve o Response ou None em caso de falha."""
    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS + 1):
        try:
            resp = sessao.get(url, timeout=TIMEOUT)
            resp.raise_for_status()
            if DEBUG:
                log(f"  [debug] {url} -> HTTP {resp.status_code}, "
                    f"{len(resp.text)} bytes, url final: {resp.url}")
            return resp
        except Exception as e:
            ultimo_erro = e
            log(f"  tentativa {tentativa}/{TENTATIVAS} falhou: {e}")
            time.sleep(3 * tentativa)
    log(f"  desisti de {url}: {ultimo_erro}")
    return None


def normalizar(texto: str) -> str:
    """Tira acentos e deixa minúsculo, para a busca ignorar acentuação."""
    if not texto:
        return ""
    sem_acento = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    return sem_acento.lower()


def limpar_html(html: str, limite: int = 400) -> str:
    """Remove tags HTML e devolve um trecho de texto limpo."""
    if not html:
        return ""
    texto = BeautifulSoup(html, "lxml").get_text(" ", strip=True)
    texto = unescape(re.sub(r"\s+", " ", texto)).strip()
    return texto[:limite] + ("..." if len(texto) > limite else "")


def encontrar_termos(texto: str, chaves_norm: list[str]) -> list[str]:
    """Devolve a lista de palavras-chave (originais) encontradas no texto."""
    alvo = normalizar(texto)
    achados = []
    for original, chave in chaves_norm:
        if chave and chave in alvo:
            achados.append(original)
    return achados


# --------------------------------------------------------------------------- #
# Estado (controle do que já foi visto)
# --------------------------------------------------------------------------- #

def carregar_estado() -> set[str]:
    if ARQ_ESTADO.exists():
        try:
            dados = json.loads(ARQ_ESTADO.read_text(encoding="utf-8"))
            return set(dados.get("vistos", []))
        except Exception as e:  # arquivo corrompido não deve travar o robô
            log(f"Aviso: não consegui ler o estado ({e}). Começando do zero.")
    return set()


def salvar_estado(vistos: set[str]) -> None:
    DIR_ESTADO.mkdir(parents=True, exist_ok=True)
    # Mantém no máximo os 5000 ids mais recentes para o arquivo não crescer sem fim.
    lista = sorted(vistos)[-5000:]
    ARQ_ESTADO.write_text(
        json.dumps({"vistos": lista}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# --------------------------------------------------------------------------- #
# Coleta: Diário Oficial da União
# --------------------------------------------------------------------------- #

def buscar_dou(data_ddmmaaaa: str, secoes: list[str]) -> list[dict]:
    """
    Baixa as edições do dia do DOU e devolve todas as publicações.
    Usa a página de leitura (leiturajornal), que embute um JSON com a edição
    completa de cada seção dentro de <script id="params">.
    """
    resultados: list[dict] = []
    sessao = nova_sessao()

    for secao in secoes:
        url = f"https://www.in.gov.br/leiturajornal?secao={secao}&data={data_ddmmaaaa}"
        log(f"DOU: baixando seção {secao} ({data_ddmmaaaa})...")
        resp = baixar(sessao, url)
        if resp is None:
            continue

        soup = BeautifulSoup(resp.text, "lxml")
        # O JSON da edição fica em <script id="params"> (pode variar de id).
        script = soup.find("script", id="params")
        if not script or not script.string:
            for s in soup.find_all("script"):
                if s.string and "jsonArray" in s.string:
                    script = s
                    break
        if not script or not script.string:
            log(f"DOU: seção {secao} sem o bloco de dados (sem edição no dia?).")
            continue

        try:
            dados = json.loads(script.string)
        except Exception as e:
            log(f"DOU: não consegui interpretar o JSON da seção {secao}: {e}")
            continue

        artigos = dados.get("jsonArray", []) or []
        if DEBUG:
            log(f"  [debug] chaves do JSON: {list(dados.keys())[:12]}")
        log(f"DOU: seção {secao} trouxe {len(artigos)} publicações.")

        for art in artigos:
            url_title = (art.get("urlTitle") or "").strip()
            if url_title.startswith("http"):
                link = url_title
            elif url_title.startswith("/"):
                link = "https://www.in.gov.br" + url_title
            elif url_title:
                link = "https://www.in.gov.br/web/dou/-/" + url_title
            else:
                link = url

            ident = str(art.get("id") or link)
            resultados.append(
                {
                    "fonte": "DOU",
                    "secao": secao.upper(),
                    "id": f"dou:{ident}",
                    "titulo": (art.get("title") or "(sem título)").strip(),
                    "orgao": (art.get("artCategory") or "").strip(),
                    "trecho": limpar_html(art.get("content") or ""),
                    "url": link,
                }
            )

    return resultados


# --------------------------------------------------------------------------- #
# Coleta: Conselho Federal de Medicina
# --------------------------------------------------------------------------- #

def buscar_cfm(api_url: str, por_pagina: int) -> list[dict]:
    """
    Coleta as publicações recentes do portal do CFM pela API REST do WordPress.
    A página de notícias é carregada por JavaScript, então a raspagem do HTML
    não funciona; a API devolve os mesmos itens em JSON, de forma confiável.
    Como a fonte é do próprio CFM, todos os itens são considerados relevantes.
    """
    resultados: list[dict] = []
    sessao = nova_sessao()

    url = f"{api_url}?per_page={por_pagina}&_fields=id,date,link,title"
    log(f"CFM: consultando a API {url} ...")
    resp = baixar(sessao, url)
    if resp is None:
        return resultados

    try:
        posts = resp.json()
    except Exception as e:
        log(f"CFM: a resposta da API não é um JSON válido: {e}")
        return resultados

    if not isinstance(posts, list):
        log(f"CFM: resposta inesperada da API: {str(posts)[:200]}")
        return resultados

    log(f"CFM: API retornou {len(posts)} publicações recentes.")
    for p in posts:
        titulo_html = (p.get("title") or {}).get("rendered", "")
        titulo = BeautifulSoup(titulo_html, "lxml").get_text(" ", strip=True)
        link = p.get("link", "")
        if not titulo or not link:
            continue
        ident = f"cfm:{p.get('id') or link}"
        data_pub = (p.get("date") or "")[:10]
        resultados.append(
            {
                "fonte": "CFM",
                "secao": f"Publicação de {data_pub}" if data_pub else "Publicação",
                "id": ident,
                "titulo": titulo,
                "orgao": "Conselho Federal de Medicina",
                "trecho": "",
                "url": link,
            }
        )

    return resultados


# --------------------------------------------------------------------------- #
# Relatório
# --------------------------------------------------------------------------- #

def montar_relatorio(data_ddmmaaaa: str, novos: list[dict], erros: list[str]) -> str:
    linhas: list[str] = []
    linhas.append(f"# Monitoramento DOU + CFM — {data_ddmmaaaa}")
    linhas.append("")
    linhas.append(f"Publicações ligadas a médicos e pacientes encontradas: **{len(novos)}**")
    linhas.append("")
    gerado = datetime.now(FUSO_BR).strftime("%d/%m/%Y %H:%M")
    linhas.append(f"_Gerado automaticamente em {gerado} (horário de Brasília)._")
    linhas.append("")

    if erros:
        linhas.append("> ⚠️ Avisos durante a coleta:")
        for e in erros:
            linhas.append(f"> - {e}")
        linhas.append("")

    if not novos:
        linhas.append("Nenhuma nova publicação relevante encontrada hoje.")
        linhas.append("")
        return "\n".join(linhas)

    # Agrupa por fonte (DOU / CFM).
    por_fonte: dict[str, list[dict]] = {}
    for item in novos:
        por_fonte.setdefault(item["fonte"], []).append(item)

    for fonte in sorted(por_fonte):
        itens = por_fonte[fonte]
        linhas.append(f"## {fonte} ({len(itens)})")
        linhas.append("")
        for item in itens:
            linhas.append(f"### {item['titulo']}")
            meta = []
            if item.get("secao"):
                meta.append(item["secao"])
            if item.get("orgao"):
                meta.append(item["orgao"])
            if meta:
                linhas.append(f"*{' — '.join(meta)}*")
            if item.get("termos"):
                linhas.append(f"Palavras-chave: {', '.join(sorted(set(item['termos'])))}")
            if item.get("trecho"):
                linhas.append("")
                linhas.append(f"> {item['trecho']}")
            linhas.append("")
            linhas.append(f"🔗 {item['url']}")
            linhas.append("")

    return "\n".join(linhas)


def markdown_para_texto(md: str) -> str:
    """Converte o relatório para texto simples (versão enviada ao Drive)."""
    texto = re.sub(r"^#+\s*", "", md, flags=re.MULTILINE)
    texto = texto.replace("**", "").replace("*", "").replace("> ", "").replace("_", "")
    return texto


# --------------------------------------------------------------------------- #
# Programa principal
# --------------------------------------------------------------------------- #

def main() -> int:
    parser = argparse.ArgumentParser(description="Monitoramento DOU + CFM")
    parser.add_argument(
        "--data",
        help="Data a verificar no formato DD-MM-AAAA (padrão: hoje em Brasília).",
    )
    args = parser.parse_args()

    config = yaml.safe_load(CONFIG.read_text(encoding="utf-8"))
    palavras = config.get("palavras_chave", [])
    chaves_norm = [(p, normalizar(p)) for p in palavras]
    secoes = config.get("dou", {}).get("secoes", ["do1"])
    cfm_cfg = config.get("cfm", {})
    cfm_api = cfm_cfg.get("api", "https://portal.cfm.org.br/wp-json/wp/v2/posts")
    cfm_por_pagina = cfm_cfg.get("por_pagina", 30)

    data = args.data or datetime.now(FUSO_BR).strftime("%d-%m-%Y")
    log(f"Iniciando monitoramento para {data}.")

    erros: list[str] = []

    # ----- Coleta -----
    try:
        dou_itens = buscar_dou(data, secoes)
    except Exception as e:
        dou_itens = []
        erros.append(f"Erro geral na coleta do DOU: {e}")
        log(erros[-1])

    try:
        cfm_itens = buscar_cfm(cfm_api, cfm_por_pagina)
    except Exception as e:
        cfm_itens = []
        erros.append(f"Erro geral na coleta do CFM: {e}")
        log(erros[-1])

    # ----- Filtragem -----
    relevantes: list[dict] = []
    for item in dou_itens:
        termos = encontrar_termos(
            f"{item['titulo']} {item['orgao']} {item['trecho']}", chaves_norm
        )
        if termos:
            item["termos"] = termos
            relevantes.append(item)
    log(f"DOU: {len(relevantes)} de {len(dou_itens)} publicações são relevantes.")

    # CFM: a fonte já é médica; inclui tudo (mas marca palavras-chave se houver).
    for item in cfm_itens:
        item["termos"] = encontrar_termos(item["titulo"], chaves_norm)
        relevantes.append(item)

    # ----- Remoção do que já foi visto -----
    vistos = carregar_estado()
    novos = [i for i in relevantes if i["id"] not in vistos]
    log(f"Total relevante: {len(relevantes)} | Novos (não vistos antes): {len(novos)}")

    # ----- Relatório -----
    DIR_RELATORIOS.mkdir(parents=True, exist_ok=True)
    data_iso = datetime.strptime(data, "%d-%m-%Y").strftime("%Y-%m-%d")
    md = montar_relatorio(data, novos, erros)

    arq_md = DIR_RELATORIOS / f"{data_iso}.md"
    arq_txt = DIR_RELATORIOS / f"{data_iso}.txt"
    arq_md.write_text(md, encoding="utf-8")
    arq_txt.write_text(markdown_para_texto(md), encoding="utf-8")
    log(f"Relatório salvo em {arq_md.relative_to(RAIZ)} e {arq_txt.relative_to(RAIZ)}.")

    # ----- Atualiza estado -----
    for i in novos:
        vistos.add(i["id"])
    salvar_estado(vistos)

    # Deixa o caminho do .txt disponível para o passo de upload do workflow.
    print(f"::set-output-arquivo::{arq_txt}")
    Path(RAIZ / ".ultimo_relatorio.txt").write_text(str(arq_txt), encoding="utf-8")

    log("Concluído.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
