# Quirk Auto Ads

Sistema de criação automática de campanhas Meta Ads (CTWA) via WhatsApp pro mercado imobiliário.

**Stack atual (pós-migração 2026-05-28):**
- **Orquestração:** n8n self-hosted em `https://n8n.quirkgrowth.online`
- **Storage:** Supabase Postgres, schema `auto_ads`
- **IA:** Anthropic Claude Sonnet 4-6 (3 chamadas — agente principal, classifier, extrator)
- **Execução:** Meta Marketing API v25 (4 chamadas — D.1 a D.4)
- **WhatsApp:** UAZAPI (`quirkgrowth.uazapi.com`)

**Histórico:** Migrado do Make.com em mai/2026 após 14 versões iteradas. Spec da migração em `docs/2026-05-28-quirk-auto-ads-n8n-migration-design.md`.

## Estrutura

| Pasta | Conteúdo |
|---|---|
| `docs/` | Spec, plano de implementação, e outras notas técnicas |
| `sql/` | Migrations versionadas do schema `auto_ads` |
| `prompts/` | Prompts dos 3 nodes Anthropic (agente principal, classifier, extrator) |
| `n8n_workflow/` | Snapshots do workflow exportado (uma cópia por milestone) |
| `scripts/` | Utilitários Python para automatizar API n8n, helpers de teste |

## Como rodar uma migration

```bash
PSQL_URL=$(cat ~/.config/n8n-quirk/supabase_url.txt | tr -d '\n')
psql "$PSQL_URL" -f sql/NNN_nome.sql
```

## Como atualizar o workflow no n8n

Via `scripts/n8n_api.py` (API REST com key em `~/.config/n8n-quirk/api_key.txt`).

```bash
python3 scripts/n8n_api.py list    # listar workflows
python3 scripts/n8n_api.py get <id>  # detalhes de um workflow
python3 scripts/n8n_api.py creds   # listar credenciais
```

## Multi-cliente

Cada cliente cadastrado em `auto_ads.clientes` tem:
- `telefone` (PK, formato `5511999999999` normalizado)
- `ad_account_id` — conta de anúncio Meta dele (sem prefixo `act_`)
- `page_id` — página Facebook
- `wa_link` — `https://wa.me/<numero>` dele

Token Meta é **único** (System User QuirkOps), centralizado em ENV var `META_ACCESS_TOKEN` do servidor n8n.
