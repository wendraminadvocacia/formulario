# Monitoramento do DOU e do CFM — Médicos e Pacientes

Robô que, **todos os dias às 8h da manhã (horário de Brasília)**, verifica:

- o **Diário Oficial da União** (DOU — `in.gov.br`), seções DO1, DO2 e DO3; e
- o portal do **Conselho Federal de Medicina** (CFM — `portal.cfm.org.br`),

e gera um relatório com as publicações **ligadas a médicos e pacientes**.

O relatório é:

1. **salvo no próprio repositório**, na pasta [`relatorios/`](relatorios/) (arquivo por dia, ex.: `2026-06-27.md`); e
2. **enviado para uma pasta no Google Drive** (depois de configurado o acesso — veja abaixo).

Publicações que já apareceram em dias anteriores **não se repetem** (o robô guarda o que já viu em `estado/vistos.json`).

> ⚡ **Acesso rápido (ícone):** abra o arquivo [`atalho.html`](atalho.html) no navegador
> e toque em "Adicionar à Tela de Início" para criar um ícone no celular com botões
> para ver o agendamento, rodar na hora e abrir os relatórios.

---

## Como funciona

| Peça | Função |
|------|--------|
| `monitor.py` | Faz a coleta, o filtro por palavras-chave e gera o relatório. |
| `config.yaml` | Onde você ajusta as **palavras-chave** e as fontes — sem mexer no código. |
| `.github/workflows/monitoramento.yml` | Agenda a execução diária às 8h e envia para o Drive. |
| `relatorios/` | Arquivo dos relatórios diários. |
| `estado/vistos.json` | Memória do que já foi reportado, para não repetir. |

A execução roda no **GitHub Actions** (servidores do GitHub), não no seu computador.
Não é preciso deixar nada ligado.

---

## Ajustar o que é monitorado

Edite o arquivo [`config.yaml`](config.yaml). As palavras-chave **ignoram acentos
e maiúsculas** — escrever `medico` já encontra "médico", "Médico", "MÉDICOS", etc.

```yaml
palavras_chave:
  - medico
  - paciente
  - "responsabilidade medica"
  # ... adicione/remova à vontade
```

---

## Enviar os relatórios para o Google Drive (configuração única)

Por segurança, o GitHub não pode usar a sua conta do Google sozinho — é preciso
gerar **um token de acesso ao seu Drive** e guardá-lo como "segredo" no repositório.
Enquanto isso não é feito, o robô continua funcionando e salvando os relatórios na
pasta `relatorios/` do repositório.

**Passo 1 — Gerar o token (uma vez só):**

1. Instale o programa **rclone** em qualquer computador: <https://rclone.org/downloads/>
2. No terminal, rode:
   ```
   rclone authorize "drive"
   ```
3. Abrirá o navegador para você entrar na conta Google **wendraminadvocacia@gmail.com** e autorizar.
4. O comando vai imprimir um texto que começa com `{"access_token":...}`. **Copie esse texto inteiro.**

**Passo 2 — Guardar o token no GitHub:**

1. No repositório, vá em **Settings → Secrets and variables → Actions → New repository secret**.
2. Nome (Name): `GDRIVE_RCLONE_TOKEN`
3. Valor (Secret): cole o texto copiado no passo anterior.
4. Salve.

Pronto. A partir da próxima execução, o robô cria (se ainda não existir) a pasta
**"Monitoramento DOU e CFM - Médicos e Pacientes"** no seu Drive e envia os
relatórios `.txt` para lá. (O nome da pasta pode ser alterado em `config.yaml`.)

---

## Rodar manualmente (teste)

Na aba **Actions** do repositório, escolha **"Monitoramento DOU e CFM"** e clique
em **Run workflow**. Isso executa na hora, sem esperar as 8h.

---

## Observações importantes

- Para o agendamento diário funcionar, o código precisa estar na **branch padrão**
  (`main`) do repositório. O GitHub só ativa tarefas agendadas a partir dela.
- O **horário das 8h** pode sofrer pequenos atrasos: o agendador do GitHub não é
  exato em horários de pico. O relatório sempre mostra o horário real em que foi gerado.
- O GitHub **desativa agendamentos** em repositórios sem nenhuma atividade por 60
  dias. Como o robô faz um commit por dia (salvando o relatório), isso mantém o
  repositório ativo e o agendamento ligado.
- O robô depende do formato das páginas do DOU e do CFM. Se algum dia uma dessas
  páginas mudar de estrutura, o relatório registra um aviso e os logs da aba
  **Actions** mostram o que aconteceu.
