# DRE — Wendramin Advocacia

Projeto para **organizar e acompanhar o faturamento** do escritório. A partir dos
extratos de lançamentos do **Astrea**, ele gera um **DRE** (Demonstração do
Resultado) com:

- **DRE mensal** — receitas, despesas por categoria e resultado de cada mês;
- **DRE consolidado** — totais do período;
- **Indicadores** — médias mensais e honorários a receber;
- **Projeção** dos próximos 6 meses, com base nos contratos parcelados ativos.

O resultado fica em [`saida/DRE_Wendramin_2026.csv`](saida/), pronto para abrir no
Google Sheets ou Excel.

> Não precisa instalar nada — os scripts usam só o Python que já vem pronto
> (Python 3). E você **nunca edita código**: só mexe em dois arquivos de dados.

---

## Os dois arquivos que você edita

| Arquivo | O que é |
|---|---|
| [`ledger.csv`](ledger.csv) | Uma linha por mês, já com os números apurados (receitas e despesas por categoria). É a "memória" do DRE. |
| [`contratos.csv`](contratos.csv) | A lista de contratos parcelados ativos (cliente, valor por mês, mês em que encerra). É o que alimenta a **projeção**. |

---

## Rotina de todo mês (passo a passo)

**1. Exporte o extrato do mês.** No Astrea, abra o *Extrato de lançamentos* do mês,
copie o texto (ou copie do PDF) e salve em um arquivo dentro de `extratos/`, com o
nome no formato `AAAA-MM.txt`. Exemplo: `dre/extratos/2026-07.txt`.

**2. Apure o mês automaticamente.** Rode:

```
python3 dre/importar_extrato.py dre/extratos/2026-07.txt
```

O script mostra os totais, a divisão por categoria e — no fim — uma **linha pronta
para colar** no `ledger.csv`. Ele também confere se as somas batem com o total de
saídas do próprio Astrea (mostra `CONFERENCIA DESPESAS: OK`).

**3. Cole a linha no `ledger.csv`.** Abra o `ledger.csv` e cole a linha sugerida no
final (uma linha por mês).

**4. Atualize os contratos.** No `contratos.csv`: adicione clientes novos, e ajuste
ou remova os contratos que encerraram. (Isso mantém a projeção realista.)

**5. Gere o DRE.** Rode:

```
python3 dre/gerar_dre.py
```

Pronto — o arquivo [`saida/DRE_Wendramin_2026.csv`](saida/) é regenerado com tudo
atualizado. Abra no Google Sheets (*Arquivo → Importar → Fazer upload*).

---

## Entendendo os números (observações importantes)

- **Regime de competência.** O DRE soma os honorários **lançados** no mês, mesmo os
  ainda "Não recebidos". Por isso o valor pode diferir do que de fato entrou na
  conta. A coluna **honorários a receber** mostra quanto ficou em aberto.
- **O "Saldo" do Astrea não é o caixa real.** Aquele saldo (na casa das centenas de
  milhar) é um acumulado contábil. O dinheiro disponível de fato é o saldo da sua
  conta no banco. Não confunda os dois para decisões de caixa.
- **Categorias de despesa.** São 8: Andrieli (assessoria + repasses), Marketing e
  cursos, Software/TI/Site, Impostos e taxas, Contabilidade, Energia, Telefone,
  Custas e suprimentos. A maior delas, historicamente, é a **Andrieli**.
- **A divisão por categoria é uma sugestão.** Os totais de entradas/saídas vêm
  exatos do Astrea; a classificação por categoria é feita por palavras-chave. Em
  meses atípicos, confira a linha sugerida antes de colar (o script avisa se a soma
  não fechar).

---

## Arquivos do projeto

```
dre/
├── README.md             (este guia)
├── ledger.csv            (dados mensais — você edita)
├── contratos.csv         (contratos ativos — você edita)
├── importar_extrato.py   (lê o extrato do Astrea e sugere a linha do mês)
├── gerar_dre.py          (gera o DRE a partir do ledger + contratos)
├── extratos/             (guarde aqui os textos dos extratos, AAAA-MM.txt)
└── saida/
    └── DRE_Wendramin_2026.csv   (resultado — abra no Sheets/Excel)
```
