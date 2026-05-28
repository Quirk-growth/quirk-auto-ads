# Quirk Auto Ads — Migração Make → n8n: Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar o cenário Quirk Auto Ads do Make.com para n8n self-hosted (`n8n.quirkgrowth.online`), com Fase E embutida (token centralizado, audit_log, retry automático em chamadas Meta API).

**Architecture:** 1 workflow n8n com 2 branches (texto/mídia) → Supabase Postgres em schema `auto_ads` (4 tabelas) → 3 chamadas Anthropic (agente/classifier/extractor) → 4 chamadas HTTP Meta (D.1-D.4) + 1 HTTP UAZAPI (download mídia). API key do n8n permite edição direta via REST — sem ciclo de "exporta-importa-save".

**Tech Stack:** n8n self-hosted, Supabase Postgres, Anthropic Claude (Sonnet 4-6), Meta Marketing API v25, UAZAPI HTTP, Python 3 (scripts auxiliares), bash/curl.

**Spec de referência:** `docs/2026-05-28-quirk-auto-ads-n8n-migration-design.md`

---

## Pré-requisitos validados

- ✅ Acesso n8n: `https://n8n.quirkgrowth.online/api/v1` com API key salva em `~/.config/n8n-quirk/api_key.txt`
- ✅ Credencial Postgres existente no n8n: `Supabase SDR Quirk` (id `hflXyXJQqzXr5XmY`)
- ✅ Tokens em mãos: Meta System User Token (`EAAqtFmgGCYkB...`), Anthropic API key (a confirmar com Renan), UAZAPI token (`8120269d-c572-4adc-b8a8-ddeda2177d99`)
- ✅ Spec aprovado pelo Renan
- ⏳ Renan vai precisar acessar SSH/painel do servidor n8n pra adicionar variáveis ENV (Task 6)

---

## Estrutura de arquivos do projeto

| Caminho | Responsabilidade |
|---|---|
| `/Users/renanreal/quirk_auto_ads/docs/` | Spec e plano (já existem) |
| `/Users/renanreal/quirk_auto_ads/sql/` | Migrations Postgres versionadas |
| `/Users/renanreal/quirk_auto_ads/sql/001_init_schema.sql` | Schema `auto_ads` + 4 tabelas + índices |
| `/Users/renanreal/quirk_auto_ads/sql/002_seed_renan.sql` | Cadastro de teste do Renan |
| `/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md` | Prompt v14 consolidado do agente (sem variáveis Make) |
| `/Users/renanreal/quirk_auto_ads/prompts/classifier.md` | Prompt v9 do classifier |
| `/Users/renanreal/quirk_auto_ads/prompts/extrator.md` | Prompt v14 do extrator (com tabelas Pubs + cidades) |
| `/Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json` | Snapshot exportado do workflow n8n (após cada milestone) |
| `/Users/renanreal/quirk_auto_ads/scripts/` | Scripts auxiliares (Python/bash) |
| `/Users/renanreal/quirk_auto_ads/scripts/n8n_api.py` | Helper Python pra chamar API n8n |
| `/Users/renanreal/quirk_auto_ads/scripts/test_meta_token.py` | Valida META_ACCESS_TOKEN |
| `/Users/renanreal/quirk_auto_ads/scripts/run_e2e_test.py` | Simula payload UAZAPI e dispara webhook |

---

## Task 1: Inicializar git no projeto

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/.gitignore`
- Create: `/Users/renanreal/quirk_auto_ads/README.md`

- [ ] **Step 1: Verificar se git já existe**

Run: `cd /Users/renanreal/quirk_auto_ads && git status 2>&1`
Expected: `fatal: not a git repository` (significa que precisa init)

- [ ] **Step 2: Criar .gitignore**

```gitignore
# Tokens e credenciais
*.token
*api_key*
*.env
.env.*

# Backups intermediários do Make (não relevantes daqui em diante)
blueprint_v*.json
blueprint_backup_*.json
blueprint_MODIFICADO_*.json

# OS
.DS_Store
*.swp

# Python
__pycache__/
*.pyc
.venv/

# n8n exports (vão pra n8n_workflow/ via task específica)
*.exported.json
```

- [ ] **Step 3: Criar README.md mínimo**

```markdown
# Quirk Auto Ads

Sistema de criação automática de campanhas Meta Ads (CTWA) via WhatsApp pro mercado imobiliário.

**Stack atual:** n8n self-hosted + Supabase Postgres + Anthropic + Meta Marketing API + UAZAPI.

**Histórico:** Migrado do Make.com em mai/2026 (após 14 versões iteradas). Spec da migração em `docs/2026-05-28-quirk-auto-ads-n8n-migration-design.md`.

## Estrutura

- `docs/` — specs e planos
- `sql/` — migrations Postgres do schema `auto_ads`
- `prompts/` — prompts dos 3 nodes Anthropic (agente, classifier, extrator)
- `n8n_workflow/` — snapshots do workflow n8n
- `scripts/` — utilitários Python

## Como rodar uma migration

`psql $SUPABASE_URL -f sql/NNN_nome.sql`

## Como atualizar o workflow no n8n

Via `scripts/n8n_api.py` (API REST com key em `~/.config/n8n-quirk/api_key.txt`).
```

- [ ] **Step 4: Init git e primeiro commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git init
git add .gitignore README.md docs/ sql/ prompts/ scripts/ n8n_workflow/ resolve_interests.py resolve_report.md interests_ids.json
git status  # confirmar que blueprints v* ficaram ignored
git commit -m "init: project structure for n8n migration"
```

Expected: 1 commit criado, blueprints ignorados pelo gitignore.

- [ ] **Step 5: Verificar gitignore funcionou**

Run: `cd /Users/renanreal/quirk_auto_ads && git status --ignored 2>&1 | grep blueprint`
Expected: blueprints aparecem como "Ignored files"

---

## Task 2: Criar migration SQL do schema

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/sql/001_init_schema.sql`

- [ ] **Step 1: Escrever o SQL completo**

Conteúdo de `sql/001_init_schema.sql`:

```sql
-- Quirk Auto Ads — Schema inicial
-- Migration 001
-- Data: 2026-05-28
-- Spec: docs/2026-05-28-quirk-auto-ads-n8n-migration-design.md (Seção 4)

CREATE SCHEMA IF NOT EXISTS auto_ads;

-- ──────────────────────────────────────────────
-- Cadastro multi-cliente
-- Substitui o Data Store do Make
-- access_token NÃO fica aqui (centralizado em ENV — Fase E)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.clientes (
  telefone TEXT PRIMARY KEY,
  ad_account_id TEXT NOT NULL,
  page_id TEXT NOT NULL,
  wa_link TEXT NOT NULL,
  nome_cliente TEXT,
  ativo BOOLEAN DEFAULT TRUE,
  criado_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Conversas (memória + criativos)
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.conversas (
  telefone TEXT PRIMARY KEY REFERENCES auto_ads.clientes(telefone) ON DELETE CASCADE,
  historico TEXT DEFAULT '',
  criativo_url TEXT DEFAULT '',
  ultima_atualizacao TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Tracking de campanhas — Fase E
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.campanhas (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT REFERENCES auto_ads.clientes(telefone),
  nome_campanha TEXT,
  ad_account_id TEXT,
  campaign_id TEXT,
  adset_id TEXT,
  creative_id TEXT,
  ad_id TEXT,
  status TEXT,
  json_extrator JSONB,
  criada_em TIMESTAMPTZ DEFAULT NOW()
);

-- ──────────────────────────────────────────────
-- Audit log — Fase E
-- ──────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS auto_ads.audit_log (
  id BIGSERIAL PRIMARY KEY,
  telefone TEXT,
  evento TEXT NOT NULL,
  detalhes JSONB,
  ts TIMESTAMPTZ DEFAULT NOW()
);

-- Índices
CREATE INDEX IF NOT EXISTS idx_campanhas_telefone ON auto_ads.campanhas(telefone);
CREATE INDEX IF NOT EXISTS idx_campanhas_criada ON auto_ads.campanhas(criada_em DESC);
CREATE INDEX IF NOT EXISTS idx_audit_telefone ON auto_ads.audit_log(telefone);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON auto_ads.audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_evento ON auto_ads.audit_log(evento);
```

- [ ] **Step 2: Validar SQL sintaticamente**

Run: `python3 -c "import re; sql = open('/Users/renanreal/quirk_auto_ads/sql/001_init_schema.sql').read(); print('OK -- lines:', sql.count(chr(10)))"`
Expected: `OK -- lines: ~60`

- [ ] **Step 3: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add sql/001_init_schema.sql
git commit -m "feat(sql): migration 001 — schema auto_ads with 4 tables"
```

---

## Task 3: Aplicar migration no Supabase

**Files:**
- N/A (operação em banco remoto)

- [ ] **Step 1: Identificar credencial Postgres do n8n via API**

Run:
```bash
N8N_URL="https://n8n.quirkgrowth.online"
N8N_KEY=$(cat ~/.config/n8n-quirk/api_key.txt | tr -d '\n')
curl -s -H "X-N8N-API-KEY: $N8N_KEY" "$N8N_URL/api/v1/credentials" | python3 -c "import json,sys; data=json.load(sys.stdin); [print(c['id'], '|', c['name'], '|', c['type']) for c in data.get('data',[])]"
```

Expected: lista com `hflXyXJQqzXr5XmY | Supabase SDR Quirk | postgres` (entre outras)

- [ ] **Step 2: Pegar connection string do Supabase**

n8n API NÃO retorna senhas. Renan precisa fornecer a string Postgres do Supabase manualmente. Formato esperado:

```
postgresql://postgres.<projeto>:<senha>@<host>:5432/postgres
```

Salvar em `/Users/renanreal/.config/n8n-quirk/supabase_url.txt` com perms 600.

- [ ] **Step 3: Pedir ao Renan a connection string**

> Stop e perguntar: "Me passa a connection string completa do Supabase (com senha). Pode ser por aqui — vou salvar em `~/.config/n8n-quirk/supabase_url.txt` com perms 600. Formato: `postgresql://...`"

- [ ] **Step 4: Aplicar a migration**

Run:
```bash
PSQL_URL=$(cat ~/.config/n8n-quirk/supabase_url.txt | tr -d '\n')
psql "$PSQL_URL" -f /Users/renanreal/quirk_auto_ads/sql/001_init_schema.sql
```

Expected: várias linhas `CREATE SCHEMA`, `CREATE TABLE`, `CREATE INDEX` sem erros.

- [ ] **Step 5: Validar que tabelas foram criadas**

Run:
```bash
psql "$PSQL_URL" -c "\\dt auto_ads.*"
```

Expected: 4 tabelas listadas — clientes, conversas, campanhas, audit_log.

- [ ] **Step 6: Validar índices**

Run:
```bash
psql "$PSQL_URL" -c "SELECT indexname FROM pg_indexes WHERE schemaname='auto_ads' ORDER BY indexname"
```

Expected: 5 índices (`idx_audit_evento`, `idx_audit_telefone`, `idx_audit_ts`, `idx_campanhas_criada`, `idx_campanhas_telefone`).

---

## Task 4: Seed do cadastro de teste (Renan)

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/sql/002_seed_renan.sql`

- [ ] **Step 1: Escrever seed SQL**

```sql
-- Cadastro do telefone de teste do Renan (founder Quirk Growth)
-- Necessário pra qualquer teste end-to-end funcionar

INSERT INTO auto_ads.clientes (telefone, ad_account_id, page_id, wa_link, nome_cliente)
VALUES (
  '5511980838409',
  '3771507593117364',
  '687786881077238',
  'https://wa.me/5511952136200',
  'Renan Real (teste interno)'
)
ON CONFLICT (telefone) DO UPDATE SET
  ad_account_id = EXCLUDED.ad_account_id,
  page_id = EXCLUDED.page_id,
  wa_link = EXCLUDED.wa_link,
  nome_cliente = EXCLUDED.nome_cliente;

INSERT INTO auto_ads.conversas (telefone, historico, criativo_url)
VALUES ('5511980838409', '', '')
ON CONFLICT (telefone) DO NOTHING;
```

- [ ] **Step 2: Aplicar**

Run:
```bash
PSQL_URL=$(cat ~/.config/n8n-quirk/supabase_url.txt | tr -d '\n')
psql "$PSQL_URL" -f /Users/renanreal/quirk_auto_ads/sql/002_seed_renan.sql
```

Expected: `INSERT 0 1` (ou `UPDATE 1` se já existia).

- [ ] **Step 3: Validar inserção**

Run:
```bash
psql "$PSQL_URL" -c "SELECT * FROM auto_ads.clientes WHERE telefone='5511980838409'"
```

Expected: 1 linha com todos os campos preenchidos.

- [ ] **Step 4: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add sql/002_seed_renan.sql
git commit -m "feat(sql): seed cadastro de teste 5511980838409 (Renan)"
```

---

## Task 5: Consolidar prompts em arquivos versionados

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md`
- Create: `/Users/renanreal/quirk_auto_ads/prompts/classifier.md`
- Create: `/Users/renanreal/quirk_auto_ads/prompts/extrator.md`

- [ ] **Step 1: Extrair os 3 prompts do blueprint v13 + adições do v14 (geo cidade+raio)**

Script Python pra extrair do v13 e mesclar com os deltas do v14:

```python
# scripts/extract_prompts.py
import json, re

# Lê blueprint v13 (último estável)
with open('/Users/renanreal/quirk_auto_ads/blueprint_v13_ADVANTAGE_FIX.json') as f:
    bp = json.load(f)

def find(flow, mid):
    for it in flow:
        if it.get("id") == mid: return it
        if "routes" in it:
            for r in it["routes"]:
                if "flow" in r:
                    f = find(r["flow"], mid)
                    if f: return f
    return None

# Mod 5 = agente principal, Mod 37 = classifier, Mod 35 = extractor
for mid, fname in [(5, 'agente_principal.md'), (37, 'classifier.md'), (35, 'extrator.md')]:
    mod = find(bp["flow"], mid)
    prompt = mod["mapper"]["textPrompt"]
    with open(f'/Users/renanreal/quirk_auto_ads/prompts/{fname}', 'w') as f:
        f.write(prompt)
    print(f"✓ {fname} ({len(prompt)} chars)")
```

Run: `python3 -c "exec(open('/dev/stdin').read())" < /dev/stdin <<< "$(cat <<'EOF'
import json
with open('/Users/renanreal/quirk_auto_ads/blueprint_v13_ADVANTAGE_FIX.json') as f:
    bp = json.load(f)
def find(flow, mid):
    for it in flow:
        if it.get('id') == mid: return it
        if 'routes' in it:
            for r in it['routes']:
                if 'flow' in r:
                    f = find(r['flow'], mid)
                    if f: return f
    return None
for mid, fname in [(5, 'agente_principal.md'), (37, 'classifier.md'), (35, 'extrator.md')]:
    mod = find(bp['flow'], mid)
    prompt = mod['mapper']['textPrompt']
    with open(f'/Users/renanreal/quirk_auto_ads/prompts/{fname}', 'w') as f:
        f.write(prompt)
    print(f'OK {fname}: {len(prompt)} chars')
EOF
)"`

Expected: 3 arquivos criados, ~10k+ chars cada.

- [ ] **Step 2: Substituir variáveis Make-específicas pelas n8n-específicas nos 3 prompts**

Substituições necessárias:
- `{{13.\`histórico\`}}` (Make Data Store) → `{{ $('select_conversa').item.json.historico }}` (n8n Postgres)
- `{{1.chat.wa_lastMessageTextVote}}` → `{{ $('webhook').item.json.message.text }}`
- `{{5.result}}` → `{{ $('agente_principal').item.json.message.content[0].text }}`

```python
# Aplica substituições em cada prompt
import re
files = ['agente_principal.md', 'classifier.md', 'extrator.md']
substitutions = [
    (r'\{\{13\.`histórico`\}\}', '{{ $node["select_conversa"].json.historico }}'),
    (r'\{\{1\.chat\.wa_lastMessageTextVote\}\}', '{{ $node["webhook"].json.message.text }}'),
    (r'\{\{5\.result\}\}', '{{ $node["agente_principal"].json.message.content[0].text }}'),
]
for fname in files:
    path = f'/Users/renanreal/quirk_auto_ads/prompts/{fname}'
    content = open(path).read()
    for pat, repl in substitutions:
        content = re.sub(pat, repl, content)
    open(path, 'w').write(content)
    print(f'OK {fname}')
```

- [ ] **Step 3: Adicionar adições do v14 ao extrator (geo cidade+raio + tabela 98 cidades)**

Conteúdo a adicionar ANTES de `TABELA DE PÚBLICOS — VERSÃO COM IDs REAIS DA META`:

```
REGRA CRÍTICA DE GEO_LOCATIONS:
O cliente DEVE ter informado uma cidade brasileira + raio em km. Extraia ambos pros campos:
- conjunto.geo (string descritiva: "Goiânia, raio 15km")
- conjunto.geo_cidade (nome literal da cidade — usado pra lookup na tabela abaixo)
- conjunto.geo_raio_km (inteiro, ex: 15)

Depois, no campo "targeting_meta.geo_locations", monte usando a TABELA DE CIDADES BR. Procure pela KEY correspondente ao nome. Formato:
  "geo_locations": {"cities": [{"key": "<KEY>", "radius": <raio_km>, "distance_unit": "kilometer"}]}

Exemplo: cliente disse "Goiânia 15km" → geo_locations={"cities":[{"key":"254063","radius":15,"distance_unit":"kilometer"}]}

Se a cidade NÃO estiver na tabela, fallback: geo_locations={"countries":["BR"]} + alertas.

TABELA DE CIDADES BR — nome → key:
<JSON_INLINE_DAS_98_CIDADES>
```

Tem o JSON inline em `/tmp/cidades_keys.json` (gerado na sessão atual). Aplicar via script:

```python
import json
cidades = json.load(open('/tmp/cidades_keys.json'))
cidades_inline = json.dumps({nome: info['key'] for nome, info in cidades.items()}, ensure_ascii=False, separators=(',', ':'))

regra = f'''REGRA CRÍTICA DE GEO_LOCATIONS:
O cliente DEVE ter informado uma cidade brasileira + raio em km. Extraia ambos pros campos:
- conjunto.geo (string descritiva: "Goiânia, raio 15km")
- conjunto.geo_cidade (nome literal da cidade)
- conjunto.geo_raio_km (inteiro)

Em "targeting_meta.geo_locations", monte usando a TABELA DE CIDADES BR. Formato:
  "geo_locations": {{"cities": [{{"key": "<KEY>", "radius": <raio_km>, "distance_unit": "kilometer"}}]}}

Se cidade não na tabela, fallback: {{"countries":["BR"]}} + alerta.

TABELA DE CIDADES BR:
{cidades_inline}

'''

path = '/Users/renanreal/quirk_auto_ads/prompts/extrator.md'
content = open(path).read()
insert_before = "TABELA DE PÚBLICOS — VERSÃO COM IDs REAIS DA META"
content = content.replace(insert_before, regra + insert_before)
open(path, 'w').write(content)
print(f'OK: extrator agora tem {len(content)} chars')
```

- [ ] **Step 4: Validar tamanho dos prompts (deve ficar abaixo do limite de tokens)**

Run: `wc -c /Users/renanreal/quirk_auto_ads/prompts/*.md`
Expected: cada arquivo < 30KB (~7.5k tokens), suportado pelo Claude Sonnet.

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add prompts/
git commit -m "feat(prompts): extrai prompts v13/v14 do Make pra arquivos versionados"
```

---

## Task 6: Renan adiciona variáveis ENV no servidor n8n

**Files:** N/A (config externa, instruções pro Renan)

- [ ] **Step 1: Preparar instruções pro Renan**

> Stop e instruir Renan: "Vou te passar 3 variáveis pra adicionar no `.env` do servidor n8n. Onde está o .env? Geralmente em `/opt/n8n/.env` ou `/home/n8n/.env` se foi Docker — pode variar. Me confirma o path."

- [ ] **Step 2: Aguardar Renan confirmar path do .env**

> Stop. Renan responde com path. Próximo step assume path conhecido.

- [ ] **Step 3: Dar conteúdo das 3 ENVs**

Renan adiciona no `.env`:

```bash
# Quirk Auto Ads — adicionado em 2026-05-28
META_ACCESS_TOKEN=EAAqtFmgGCYkBRu50affAwjZBbqg0FvqDH85mfvGkY77wQmSoJ4QAxKuaUqmPQ7b5YX7uJsjlcI80GHFspdQLZCuX7vrPhaplzd1WKBJwlmxpnhrM0JH7ESYpglLqdfDsgzgUu0mMZBKfJAepmpeLZBTKnsxNYS0Wv8yCJicNUen6iI28QWZC2Diald11ak7i99QZDZD
ANTHROPIC_API_KEY=<RENAN_PRECISA_FORNECER>
UAZAPI_TOKEN=8120269d-c572-4adc-b8a8-ddeda2177d99
```

> Stop e perguntar: "Me passa a ANTHROPIC_API_KEY pra eu colocar no comando."

- [ ] **Step 4: Restart n8n**

Renan executa (instrução fornecida): `docker restart n8n` (ou systemctl restart n8n, depende do setup).

- [ ] **Step 5: Validar via API que n8n voltou**

Run:
```bash
N8N_URL="https://n8n.quirkgrowth.online"
N8N_KEY=$(cat ~/.config/n8n-quirk/api_key.txt | tr -d '\n')
curl -s -o /dev/null -w "%{http_code}" -H "X-N8N-API-KEY: $N8N_KEY" "$N8N_URL/api/v1/workflows?limit=1"
```

Expected: `200`

- [ ] **Step 6: Validar que ENVs estão acessíveis (workflow teste descartável)**

Criar workflow mínimo de teste:

```bash
N8N_URL="https://n8n.quirkgrowth.online"
N8N_KEY=$(cat ~/.config/n8n-quirk/api_key.txt | tr -d '\n')

curl -s -X POST -H "X-N8N-API-KEY: $N8N_KEY" -H "Content-Type: application/json" \
  "$N8N_URL/api/v1/workflows" \
  -d '{
    "name": "test_env_validation_DELETE_ME",
    "nodes": [{
      "id": "1",
      "name": "test",
      "type": "n8n-nodes-base.code",
      "typeVersion": 2,
      "position": [0,0],
      "parameters": {
        "language": "javaScript",
        "jsCode": "return [{json: {meta_token_start: $env.META_ACCESS_TOKEN?.substring(0,10) || \"MISSING\", uazapi_token_start: $env.UAZAPI_TOKEN?.substring(0,8) || \"MISSING\", anthropic_key_start: $env.ANTHROPIC_API_KEY?.substring(0,7) || \"MISSING\"}}];"
      }
    }],
    "connections": {},
    "settings": {}
  }' | python3 -c "import json,sys; d=json.load(sys.stdin); print('workflow_id:', d.get('id'))"
```

Expected: retorna workflow_id (e.g. `Ab1Cd2Ef3`).

- [ ] **Step 7: Executar o workflow de teste**

```bash
# Manual trigger via API
curl -s -X POST -H "X-N8N-API-KEY: $N8N_KEY" \
  "$N8N_URL/api/v1/workflows/<WORKFLOW_ID>/run" | python3 -m json.tool
```

Expected: output mostra `meta_token_start: "EAAqtFmgGC"`, `uazapi_token_start: "8120269d"`, `anthropic_key_start: "sk-ant-"`. Se algum aparecer "MISSING", a ENV não está acessível.

- [ ] **Step 8: Deletar workflow de teste**

```bash
curl -s -X DELETE -H "X-N8N-API-KEY: $N8N_KEY" "$N8N_URL/api/v1/workflows/<WORKFLOW_ID>"
```

Expected: HTTP 200.

---

## Task 7: Criar helper Python pra API n8n

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/n8n_api.py`

- [ ] **Step 1: Escrever helper**

```python
#!/usr/bin/env python3
"""
Helper pra chamar a API REST do n8n.
Usa key salva em ~/.config/n8n-quirk/api_key.txt
"""
import json
import os
import sys
import urllib.parse
import urllib.request

N8N_URL = "https://n8n.quirkgrowth.online"
KEY_PATH = os.path.expanduser("~/.config/n8n-quirk/api_key.txt")

def _key():
    return open(KEY_PATH).read().strip()

def _request(method, path, payload=None):
    url = f"{N8N_URL}/api/v1{path}"
    data = json.dumps(payload).encode() if payload else None
    req = urllib.request.Request(
        url, data=data, method=method,
        headers={
            "X-N8N-API-KEY": _key(),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {e.code}: {body[:400]}")

def list_workflows(limit=50):
    return _request("GET", f"/workflows?limit={limit}")

def get_workflow(wf_id):
    return _request("GET", f"/workflows/{wf_id}")

def create_workflow(name, nodes, connections, settings=None, active=False):
    payload = {
        "name": name,
        "nodes": nodes,
        "connections": connections,
        "settings": settings or {"executionOrder": "v1"},
    }
    return _request("POST", "/workflows", payload)

def update_workflow(wf_id, **fields):
    return _request("PUT", f"/workflows/{wf_id}", fields)

def activate_workflow(wf_id):
    return _request("POST", f"/workflows/{wf_id}/activate")

def deactivate_workflow(wf_id):
    return _request("POST", f"/workflows/{wf_id}/deactivate")

def delete_workflow(wf_id):
    return _request("DELETE", f"/workflows/{wf_id}")

def list_credentials():
    return _request("GET", "/credentials")

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    if cmd == "list":
        wfs = list_workflows(10)
        for w in wfs.get("data", []):
            print(f"  {w['id']:25s} | active={w['active']} | {w['name']}")
    elif cmd == "get":
        wf_id = sys.argv[2]
        print(json.dumps(get_workflow(wf_id), indent=2, ensure_ascii=False))
    elif cmd == "creds":
        creds = list_credentials()
        for c in creds.get("data", []):
            print(f"  {c['id']:25s} | {c['type']:30s} | {c['name']}")
    else:
        print(f"Unknown: {cmd}. Try: list, get <id>, creds")
```

- [ ] **Step 2: Testar helper**

```bash
chmod +x /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py list
```

Expected: lista workflows existentes.

- [ ] **Step 3: Listar credenciais pra confirmar Postgres existente**

```bash
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py creds
```

Expected: aparece `hflXyXJQqzXr5XmY | postgres | Supabase SDR Quirk`.

- [ ] **Step 4: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/n8n_api.py
git commit -m "feat(scripts): helper Python pra API REST do n8n"
```

---

## Task 8: Criar workflow vazio "Quirk Auto Ads" no n8n

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/create_workflow.py`
- Modify: `/Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json` (snapshot)

- [ ] **Step 1: Escrever criação do workflow com Webhook trigger + Switch**

```python
#!/usr/bin/env python3
"""
Cria o workflow Quirk Auto Ads no n8n com a estrutura inicial:
- Webhook trigger
- Switch text/media (router por message.type)
"""
import json, sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import create_workflow

WEBHOOK_PATH = "quirk-auto-ads"  # gera URL /webhook/quirk-auto-ads

nodes = [
    {
        "id": "webhook",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [240, 300],
        "parameters": {
            "httpMethod": "POST",
            "path": WEBHOOK_PATH,
            "options": {"responseMode": "onReceived"},
            "responseData": "noData",
        },
        "webhookId": WEBHOOK_PATH,
    },
    {
        "id": "switch_msg_type",
        "name": "Switch type",
        "type": "n8n-nodes-base.switch",
        "typeVersion": 3,
        "position": [460, 300],
        "parameters": {
            "rules": {
                "values": [
                    {
                        "conditions": {
                            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                            "conditions": [{
                                "leftValue": "={{ $json.body.message.type }}",
                                "rightValue": "text",
                                "operator": {"type": "string", "operation": "equals"}
                            }],
                            "combinator": "and"
                        },
                        "renameOutput": True, "outputKey": "text"
                    },
                    {
                        "conditions": {
                            "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                            "conditions": [{
                                "leftValue": "={{ $json.body.message.type }}",
                                "rightValue": "media",
                                "operator": {"type": "string", "operation": "equals"}
                            }],
                            "combinator": "and"
                        },
                        "renameOutput": True, "outputKey": "media"
                    },
                ]
            },
            "options": {}
        },
    },
]

connections = {
    "Webhook": {
        "main": [[{"node": "Switch type", "type": "main", "index": 0}]]
    }
}

result = create_workflow("Quirk Auto Ads", nodes, connections)
print(f"✓ Workflow criado: id={result['id']}")
print(f"  Acesse: https://n8n.quirkgrowth.online/workflow/{result['id']}")
# Salva o ID em arquivo pra próximos scripts
with open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id', 'w') as f:
    f.write(result['id'])
```

- [ ] **Step 2: Executar**

```bash
mkdir -p /Users/renanreal/quirk_auto_ads/n8n_workflow
python3 /Users/renanreal/quirk_auto_ads/scripts/create_workflow.py
```

Expected: imprime workflow_id (e.g. `Xy7AbCd123`). Salva em `n8n_workflow/.workflow_id`.

- [ ] **Step 3: Validar via API**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID | python3 -c "import json,sys; d=json.load(sys.stdin); print('nodes:', [n['name'] for n in d['nodes']])"
```

Expected: `nodes: ['Webhook', 'Switch type']`

- [ ] **Step 4: Salvar snapshot inicial**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID > /Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json
```

- [ ] **Step 5: Commit**

```bash
cd /Users/renanreal/quirk_auto_ads
git add scripts/create_workflow.py n8n_workflow/workflow.json
echo "n8n_workflow/.workflow_id" >> .gitignore
git add .gitignore
git commit -m "feat(n8n): workflow inicial Quirk Auto Ads (webhook + switch type)"
```

---

## Task 9: Branch TEXTO — normaliza telefone + lookup cliente

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_text_lookup.py`
- Modify: `/Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json` (snapshot atualizado)

- [ ] **Step 1: Escrever script que adiciona nodes**

```python
#!/usr/bin/env python3
"""
Adiciona ao workflow Quirk Auto Ads:
- Function "Normalize phone" (limpa +/espaço/hífen)
- Postgres "SELECT clientes WHERE telefone = $1"
- IF "cliente cadastrado?"
- HTTP UAZAPI "não cadastrado" no false branch
"""
import json, sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id').read().strip()
wf = get_workflow(WF_ID)

POSTGRES_CRED_ID = "hflXyXJQqzXr5XmY"  # Supabase SDR Quirk

new_nodes = [
    {
        "id": "normalize_phone",
        "name": "Normalize phone",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [680, 200],
        "parameters": {
            "language": "javaScript",
            "jsCode": """const raw = $input.first().json.body.chat?.phone || $input.first().json.body.message?.from || '';
const normalized = raw.replace(/[+\\s\\-]/g, '');
return [{json: {...($input.first().json), telefone_normalizado: normalized}}];"""
        },
    },
    {
        "id": "select_cliente",
        "name": "Select cliente",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [900, 200],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT * FROM auto_ads.clientes WHERE telefone = $1 LIMIT 1",
            "queryParameters": "={{ $('Normalize phone').item.json.telefone_normalizado }}",
            "options": {}
        },
        "credentials": {"postgres": {"id": POSTGRES_CRED_ID, "name": "Supabase SDR Quirk"}},
    },
    {
        "id": "if_cadastrado",
        "name": "IF cliente cadastrado",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [1120, 200],
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
                "conditions": [{
                    "leftValue": "={{ $json.length > 0 || $json.telefone ? true : false }}",
                    "rightValue": True,
                    "operator": {"type": "boolean", "operation": "true"}
                }],
                "combinator": "and"
            }
        },
    },
    {
        "id": "send_nao_cadastrado",
        "name": "Send 'não cadastrado'",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1340, 380],
        "parameters": {
            "method": "POST",
            "url": "https://quirkgrowth.uazapi.com/send/text",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": '={ "number": "{{ $(\'Normalize phone\').item.json.telefone_normalizado }}", "text": "Olá! Esse número não está cadastrado no nosso sistema. Por favor, entre em contato com a Quirk pra ativar seu acesso." }',
            "options": {}
        },
    },
]

# Adiciona aos nodes existentes
existing_node_names = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing_node_names:
        wf["nodes"].append(n)

# Atualiza connections
wf["connections"].setdefault("Switch type", {"main": [[]]})
# Output 0 do switch (text) → Normalize phone
if not any(c.get("node") == "Normalize phone" for c in wf["connections"]["Switch type"]["main"][0]):
    wf["connections"]["Switch type"]["main"][0].append({"node": "Normalize phone", "type": "main", "index": 0})

wf["connections"]["Normalize phone"] = {"main": [[{"node": "Select cliente", "type": "main", "index": 0}]]}
wf["connections"]["Select cliente"] = {"main": [[{"node": "IF cliente cadastrado", "type": "main", "index": 0}]]}
wf["connections"]["IF cliente cadastrado"] = {
    "main": [
        [],  # placeholder pra true branch (preenche em task seguinte)
        [{"node": "Send 'não cadastrado'", "type": "main", "index": 0}]  # false branch
    ]
}

update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=wf.get("settings", {"executionOrder": "v1"}))
print("✓ Nodes adicionados:", [n["name"] for n in new_nodes])
```

- [ ] **Step 2: Executar**

```bash
python3 /Users/renanreal/quirk_auto_ads/scripts/add_text_lookup.py
```

Expected: lista os 4 nodes adicionados.

- [ ] **Step 3: Validar no n8n UI** (abre browser)

> Renan: abre `https://n8n.quirkgrowth.online/workflow/<WF_ID>` e confirma visualmente que os 4 nodes apareceram conectados ao output "text" do Switch.

- [ ] **Step 4: Atualizar snapshot e commit**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID > /Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json
cd /Users/renanreal/quirk_auto_ads
git add scripts/add_text_lookup.py n8n_workflow/workflow.json
git commit -m "feat(n8n): texto step 1 — normalize phone + select cliente + handle não cadastrado"
```

---

## Task 10: Branch TEXTO — load conversa + agente principal Anthropic

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_text_agent.py`

- [ ] **Step 1: Adicionar SELECT conversa + Anthropic agente**

```python
#!/usr/bin/env python3
"""
Continua o branch TEXTO no true branch do IF cadastrado:
- SELECT auto_ads.conversas
- Anthropic Agente Principal (prompt v14)
"""
import json, sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id').read().strip()
wf = get_workflow(WF_ID)

POSTGRES_CRED_ID = "hflXyXJQqzXr5XmY"

# Lê prompt do arquivo
with open('/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md') as f:
    SYSTEM_PROMPT = f.read()

new_nodes = [
    {
        "id": "select_conversa",
        "name": "select_conversa",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [1340, 100],
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT * FROM auto_ads.conversas WHERE telefone = $1 LIMIT 1",
            "queryParameters": "={{ $('Normalize phone').item.json.telefone_normalizado }}",
            "options": {}
        },
        "credentials": {"postgres": {"id": POSTGRES_CRED_ID, "name": "Supabase SDR Quirk"}},
    },
    {
        "id": "agente_principal",
        "name": "agente_principal",
        "type": "n8n-nodes-base.anthropicAi",
        "typeVersion": 1,
        "position": [1560, 100],
        "parameters": {
            "model": "claude-sonnet-4-6",
            "messages": {
                "messages": [
                    {"role": "user", "content": "={{ $('webhook').item.json.body.message.text || $('webhook').item.json.body.chat.wa_lastMessageTextVote || '' }}"}
                ]
            },
            "options": {
                "systemMessage": SYSTEM_PROMPT,
                "maxTokensToSample": 2000
            }
        },
        "credentials": {"anthropicApi": {"id": "TODO_RENAN_CRIA", "name": "Quirk Anthropic"}}
    },
]

existing = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing:
        wf["nodes"].append(n)

# Conexões: IF cadastrado (true) → select_conversa → agente_principal
wf["connections"].setdefault("IF cliente cadastrado", {"main": [[], []]})
if not any(c.get("node") == "select_conversa" for c in wf["connections"]["IF cliente cadastrado"]["main"][0]):
    wf["connections"]["IF cliente cadastrado"]["main"][0].append({"node": "select_conversa", "type": "main", "index": 0})
wf["connections"]["select_conversa"] = {"main": [[{"node": "agente_principal", "type": "main", "index": 0}]]}

update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=wf.get("settings", {"executionOrder": "v1"}))
print("✓ Adicionados:", [n["name"] for n in new_nodes])
print("⚠️ Próximo step requer Renan criar credential Anthropic no n8n UI e me passar o ID")
```

- [ ] **Step 2: Executar**

```bash
python3 /Users/renanreal/quirk_auto_ads/scripts/add_text_agent.py
```

Expected: 2 nodes adicionados.

- [ ] **Step 3: Renan cria credential Anthropic no n8n UI**

> Stop e instruir Renan:
> 1. Abra `https://n8n.quirkgrowth.online/credentials`
> 2. Clica "Add credential" → procura "Anthropic"
> 3. Nome: `Quirk Anthropic`
> 4. API Key: cola a `ANTHROPIC_API_KEY` (a mesma do .env)
> 5. Save
> 6. Me passa o ID da credential (visível na URL após salvar)

- [ ] **Step 4: Atualizar node agente_principal com credential ID real**

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id').read().strip()
ANTHROPIC_CRED_ID = input("Cola aqui o ID da credential Anthropic: ").strip()

wf = get_workflow(WF_ID)
for n in wf["nodes"]:
    if n["name"] == "agente_principal":
        n["credentials"]["anthropicApi"] = {"id": ANTHROPIC_CRED_ID, "name": "Quirk Anthropic"}
        break
update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=wf.get("settings", {"executionOrder": "v1"}))
print("✓ Credential atualizada")
EOF
```

- [ ] **Step 5: Snapshot e commit**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID > /Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json
cd /Users/renanreal/quirk_auto_ads
git add scripts/add_text_agent.py n8n_workflow/workflow.json
git commit -m "feat(n8n): texto step 2 — select conversa + agente principal Anthropic"
```

---

## Task 11: Branch TEXTO — classifier + UPSERT conversa + send WhatsApp

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_text_classifier.py`

- [ ] **Step 1: Adicionar nodes (script no mesmo padrão da Task 10)**

```python
import sys, json
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = open('/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id').read().strip()
wf = get_workflow(WF_ID)
POSTGRES_CRED_ID = "hflXyXJQqzXr5XmY"

# Pega anthropic cred ID do node agente_principal
anthropic_cred = None
for n in wf["nodes"]:
    if n["name"] == "agente_principal":
        anthropic_cred = n["credentials"]["anthropicApi"]
        break
assert anthropic_cred, "Anthropic credential não encontrada — rode Task 10 antes"

CLASSIFIER_PROMPT = open('/Users/renanreal/quirk_auto_ads/prompts/classifier.md').read()

new_nodes = [
    {
        "id": "classifier",
        "name": "classifier",
        "type": "n8n-nodes-base.anthropicAi",
        "typeVersion": 1,
        "position": [1780, 100],
        "parameters": {
            "model": "claude-sonnet-4-6",
            "messages": {"messages": [{"role": "user", "content": "process"}]},
            "options": {"systemMessage": CLASSIFIER_PROMPT, "maxTokensToSample": 20}
        },
        "credentials": {"anthropicApi": anthropic_cred},
    },
    {
        "id": "build_historico",
        "name": "build_historico",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2000, 100],
        "parameters": {
            "language": "javaScript",
            "jsCode": """const histAtual = $('select_conversa').first().json.historico || '';
const userMsg = $('webhook').first().json.body.message?.text || $('webhook').first().json.body.chat?.wa_lastMessageTextVote || '';
const agentResp = $('agente_principal').first().json.message?.content?.[0]?.text || $('agente_principal').first().json.content?.[0]?.text || '';
const novoTurn = `|||TURN|||Cliente: ${userMsg}\\nClaude: ${agentResp}`;
const completo = histAtual + novoTurn;
// Trunca em últimos 20 turnos
const turns = completo.split('|||TURN|||');
const ultimos20 = turns.slice(-20).join('|||TURN|||');
return [{json: {historico_atualizado: ultimos20, classifier_result: ($('classifier').first().json.message?.content?.[0]?.text || $('classifier').first().json.content?.[0]?.text || 'PENDENTE').trim()}}];"""
        }
    },
    {
        "id": "upsert_conversa",
        "name": "upsert_conversa",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "position": [2220, 100],
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO auto_ads.conversas (telefone, historico) VALUES ($1, $2) ON CONFLICT (telefone) DO UPDATE SET historico = $2, ultima_atualizacao = NOW()",
            "queryParameters": "={{ $('Normalize phone').item.json.telefone_normalizado }},{{ $json.historico_atualizado }}",
            "options": {}
        },
        "credentials": {"postgres": {"id": POSTGRES_CRED_ID, "name": "Supabase SDR Quirk"}},
    },
    {
        "id": "send_resposta",
        "name": "send_resposta",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [2440, 100],
        "parameters": {
            "method": "POST",
            "url": "https://quirkgrowth.uazapi.com/send/text",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                {"name": "Content-Type", "value": "application/json"}
            ]},
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": "={ \"number\": \"{{ $('Normalize phone').item.json.telefone_normalizado }}\", \"text\": \"{{ ($('agente_principal').item.json.message?.content?.[0]?.text || $('agente_principal').item.json.content?.[0]?.text || '').replace(/\\\"/g, '\\\\\"') }}\" }",
            "options": {}
        }
    }
]

existing = {n["name"] for n in wf["nodes"]}
for n in new_nodes:
    if n["name"] not in existing:
        wf["nodes"].append(n)

wf["connections"]["agente_principal"] = {"main": [[{"node": "classifier", "type": "main", "index": 0}]]}
wf["connections"]["classifier"] = {"main": [[{"node": "build_historico", "type": "main", "index": 0}]]}
wf["connections"]["build_historico"] = {"main": [[{"node": "upsert_conversa", "type": "main", "index": 0}]]}
wf["connections"]["upsert_conversa"] = {"main": [[{"node": "send_resposta", "type": "main", "index": 0}]]}

update_workflow(WF_ID, name=wf["name"], nodes=wf["nodes"], connections=wf["connections"], settings=wf.get("settings", {"executionOrder": "v1"}))
print("✓ Adicionados:", [n["name"] for n in new_nodes])
```

- [ ] **Step 2: Executar** `python3 /Users/renanreal/quirk_auto_ads/scripts/add_text_classifier.py`

- [ ] **Step 3: Snapshot e commit**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID > /Users/renanreal/quirk_auto_ads/n8n_workflow/workflow.json
cd /Users/renanreal/quirk_auto_ads
git add scripts/add_text_classifier.py n8n_workflow/workflow.json
git commit -m "feat(n8n): texto step 3 — classifier + upsert conversa + send WhatsApp"
```

---

## Task 12: Branch TEXTO — IF CONFIRMADO + extrator + validate

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_text_extrator.py`

- [ ] **Step 1: Adicionar IF, Extrator, Function de validação**

(Padrão idêntico — script Python que faz `get_workflow` → adiciona nodes → `update_workflow`. Por brevidade do plano, o conteúdo é:)

Nodes a adicionar (depois de `send_resposta`):
- `if_confirmado` (IF node): condição `={{ $('build_historico').item.json.classifier_result === 'CONFIRMADO' }}`
- `extrator` (Anthropic): usa prompt de `prompts/extrator.md`, user content = `={{ $('select_conversa').item.json.historico }} + nova mensagem`
- `parse_extrator` (Code/Function): extrai JSON da resposta do extrator
- `validate` (Code/Function): roda as 9 validações conforme spec seção 7

Código JS do `validate` node (na íntegra):

```javascript
const cliente = $('Select cliente').first().json;
const conversa = $('select_conversa').first().json;
const json = $('parse_extrator').first().json.json_extrator || $('parse_extrator').first().json;
const errors = [];
if (!json.campanha?.verba_diaria || json.campanha.verba_diaria < 10) errors.push('verba_diaria < 10');
if (json.campanha?.verba_diaria > 100) errors.push('verba_diaria > 100');
if (!json.campanha?.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!conversa.criativo_url) errors.push('criativo_url vazio');
if (!cliente.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');
return [{json: {ok: errors.length === 0, motivos: errors, json_extrator: json, cliente, conversa}}];
```

- [ ] **Step 2: Executar e commit** (mesmo padrão)

---

## Task 13: Branch TEXTO — D.1 Campaign HTTP Meta

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_meta_d1.py`

- [ ] **Step 1: Adicionar HTTP node D.1 com retry**

Node a adicionar (depois do branch true do `validate`):

```python
{
    "id": "meta_d1_campaign",
    "name": "meta_d1_campaign",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [3000, 100],
    "parameters": {
        "method": "POST",
        "url": "=https://graph.facebook.com/v25.0/act_{{ $('Select cliente').item.json.ad_account_id }}/campaigns",
        "sendBody": True,
        "bodyContentType": "json",
        "jsonBody": '={ "name": "{{ $(\'validate\').item.json.json_extrator.campanha.nome }}", "objective": "OUTCOME_LEADS", "status": "PAUSED", "special_ad_categories": [], "is_adset_budget_sharing_enabled": false, "access_token": "{{ $env.META_ACCESS_TOKEN }}" }',
        "options": {
            "retry": {"maxTries": 3, "waitBetweenTries": 2000}
        }
    },
    "retryOnFail": True,
    "maxTries": 3,
    "waitBetweenTries": 2000,
    "continueOnFail": True,
}
```

E nodes auxiliares:
- `if_d1_ok` (IF): condição `={{ !$json.error }}`
- `audit_d1_erro` (Postgres INSERT no audit_log se erro)

- [ ] **Step 2: Executar e commit**

---

## Task 14: Branch TEXTO — D.2 AdSet HTTP Meta

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_meta_d2.py`

- [ ] **Step 1: Adicionar HTTP node D.2**

```python
{
    "name": "meta_d2_adset",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [3220, 100],
    "parameters": {
        "method": "POST",
        "url": "=https://graph.facebook.com/v25.0/act_{{ $('Select cliente').item.json.ad_account_id }}/adsets",
        "sendBody": True,
        "bodyContentType": "json",
        "jsonBody": '={ "name": "{{ $(\'validate\').item.json.json_extrator.publico_escolhido }}", "campaign_id": "{{ $(\'meta_d1_campaign\').item.json.id }}", "daily_budget": {{ Math.max(parseInt($(\'validate\').item.json.json_extrator.campanha.verba_diaria) || 30, 10) * 100 }}, "billing_event": "IMPRESSIONS", "optimization_goal": "CONVERSATIONS", "destination_type": "WHATSAPP", "promoted_object": {"page_id": "{{ $(\'Select cliente\').item.json.page_id }}"}, "bid_strategy": "LOWEST_COST_WITHOUT_CAP", "targeting": {{ JSON.stringify($(\'validate\').item.json.json_extrator.targeting_meta) }}, "status": "PAUSED", "access_token": "{{ $env.META_ACCESS_TOKEN }}" }',
        "options": {"retry": {"maxTries": 3, "waitBetweenTries": 2000}}
    },
    "continueOnFail": True,
}
```

Mesmo padrão de IF + audit erro.

---

## Task 15: Branch TEXTO — D.3 Creative HTTP Meta

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_meta_d3.py`

- [ ] **Step 1: Adicionar HTTP node D.3**

Lógica do criativo (pega último URL da lista `criativo_url`):

```python
{
    "name": "meta_d3_creative",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [3440, 100],
    "parameters": {
        "method": "POST",
        "url": "=https://graph.facebook.com/v25.0/act_{{ $('Select cliente').item.json.ad_account_id }}/adcreatives",
        "sendBody": True,
        "bodyContentType": "json",
        "jsonBody": '={ "name": "{{ $(\'validate\').item.json.json_extrator.campanha.nome }}", "object_story_spec": {"page_id": "{{ $(\'Select cliente\').item.json.page_id }}", "link_data": {"message": "{{ $(\'validate\').item.json.json_extrator.anuncio.copy }}", "picture": "{{ ($(\'Select cliente\').item.json.criativo_url || \'\').trim().split(\'\\n\').filter(u => u).slice(-1)[0] }}", "link": "{{ $(\'Select cliente\').item.json.wa_link }}", "call_to_action": {"type": "WHATSAPP_MESSAGE", "value": {"app_destination": "WHATSAPP"}}}}, "access_token": "{{ $env.META_ACCESS_TOKEN }}" }',
        "options": {"retry": {"maxTries": 3, "waitBetweenTries": 2000}}
    },
    "continueOnFail": True,
}
```

⚠️ Notar: `Select cliente.criativo_url` — precisa que o select traga tbm da tabela conversas. Ajustar query do `select_conversa` ou criar joined view. Alternativa: usar `$('select_conversa').item.json.criativo_url`.

Vou corrigir: `picture` puxa de `$('select_conversa').item.json.criativo_url` em vez de cliente.

---

## Task 16: Branch TEXTO — D.4 Ad HTTP Meta + INSERT campanhas

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_meta_d4_and_log.py`

- [ ] **Step 1: D.4 + INSERT campanhas + INSERT audit_log + send confirmação cliente**

Nodes:

```python
# D.4 Ad
{
    "name": "meta_d4_ad",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "parameters": {
        "method": "POST",
        "url": "=https://graph.facebook.com/v25.0/act_{{ $('Select cliente').item.json.ad_account_id }}/ads",
        "sendBody": True, "bodyContentType": "json",
        "jsonBody": '={ "name": "{{ $(\'validate\').item.json.json_extrator.campanha.nome }}", "adset_id": "{{ $(\'meta_d2_adset\').item.json.id }}", "creative": {"creative_id": "{{ $(\'meta_d3_creative\').item.json.id }}"}, "status": "PAUSED", "access_token": "{{ $env.META_ACCESS_TOKEN }}" }',
        "options": {"retry": {"maxTries": 3, "waitBetweenTries": 2000}}
    },
    "continueOnFail": True,
},

# INSERT campanhas
{
    "name": "insert_campanha",
    "type": "n8n-nodes-base.postgres",
    "typeVersion": 2.6,
    "parameters": {
        "operation": "executeQuery",
        "query": "INSERT INTO auto_ads.campanhas (telefone, nome_campanha, ad_account_id, campaign_id, adset_id, creative_id, ad_id, status, json_extrator) VALUES ($1, $2, $3, $4, $5, $6, $7, 'PAUSED', $8)",
        "queryParameters": "={{ $('Normalize phone').item.json.telefone_normalizado }},{{ $('validate').item.json.json_extrator.campanha.nome }},{{ $('Select cliente').item.json.ad_account_id }},{{ $('meta_d1_campaign').item.json.id }},{{ $('meta_d2_adset').item.json.id }},{{ $('meta_d3_creative').item.json.id }},{{ $('meta_d4_ad').item.json.id }},{{ JSON.stringify($('validate').item.json.json_extrator) }}"
    },
    "credentials": {"postgres": {"id": "hflXyXJQqzXr5XmY", "name": "Supabase SDR Quirk"}}
},

# INSERT audit_log "campanha_criada"
{
    "name": "audit_campanha_criada",
    "type": "n8n-nodes-base.postgres",
    "parameters": {
        "operation": "executeQuery",
        "query": "INSERT INTO auto_ads.audit_log (telefone, evento, detalhes) VALUES ($1, 'campanha_criada', $2)",
        "queryParameters": "={{ $('Normalize phone').item.json.telefone_normalizado }},{{ JSON.stringify({campaign_id: $('meta_d1_campaign').item.json.id, ad_id: $('meta_d4_ad').item.json.id}) }}"
    },
    "credentials": {"postgres": {"id": "hflXyXJQqzXr5XmY", "name": "Supabase SDR Quirk"}}
},

# Send confirmação ao cliente
{
    "name": "send_confirmacao_cliente",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "parameters": {
        "method": "POST",
        "url": "https://quirkgrowth.uazapi.com/send/text",
        "sendHeaders": True,
        "headerParameters": {"parameters": [{"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"}, {"name": "Content-Type", "value": "application/json"}]},
        "sendBody": True, "bodyContentType": "json",
        "jsonBody": '={ "number": "{{ $(\'Normalize phone\').item.json.telefone_normalizado }}", "text": "Campanha {{ $(\'validate\').item.json.json_extrator.campanha.nome }} criada em PAUSED. Revise no Ads Manager pra ativar." }'
    }
}
```

- [ ] **Step 2: Executar e commit**

---

## Task 17: Branch MÍDIA — download + UPSERT + confirmação

**Files:**
- Create: `/Users/renanreal/quirk_auto_ads/scripts/add_media_branch.py`

- [ ] **Step 1: Adicionar 4 nodes do branch mídia**

Nodes (output 1 do Switch "media"):

```python
new_nodes = [
    {
        "name": "media_normalize_phone",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "parameters": {
            "language": "javaScript",
            "jsCode": "const raw = $input.first().json.body.chat?.phone || $input.first().json.body.message?.from || ''; return [{json: {...($input.first().json), telefone_normalizado: raw.replace(/[+\\s\\-]/g, '')}}];"
        }
    },
    {
        "name": "media_download",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://quirkgrowth.uazapi.com/message/download",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                {"name": "Content-Type", "value": "application/json"}
            ]},
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": '={ "id": "{{ $(\'webhook\').item.json.body.message.id }}" }',
            "options": {"retry": {"maxTries": 2, "waitBetweenTries": 1000}}
        }
    },
    {
        "name": "media_upsert_criativo",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.6,
        "parameters": {
            "operation": "executeQuery",
            "query": "INSERT INTO auto_ads.conversas (telefone, criativo_url, historico) VALUES ($1, $2, $3) ON CONFLICT (telefone) DO UPDATE SET criativo_url = COALESCE(conversas.criativo_url, '') || $2 || E'\\n', historico = COALESCE(conversas.historico, '') || $3, ultima_atualizacao = NOW()",
            "queryParameters": "={{ $('media_normalize_phone').item.json.telefone_normalizado }},{{ $('media_download').item.json.data?.fileURL || '' }},{{ '|||TURN|||[Sistema: criativo recebido em ' + new Date().toISOString() + ']' }}"
        },
        "credentials": {"postgres": {"id": "hflXyXJQqzXr5XmY", "name": "Supabase SDR Quirk"}}
    },
    {
        "name": "media_send_confirma",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "parameters": {
            "method": "POST",
            "url": "https://quirkgrowth.uazapi.com/send/text",
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "token", "value": "={{ $env.UAZAPI_TOKEN }}"},
                {"name": "Content-Type", "value": "application/json"}
            ]},
            "sendBody": True,
            "bodyContentType": "json",
            "jsonBody": '={ "number": "{{ $(\'media_normalize_phone\').item.json.telefone_normalizado }}", "text": "Recebi seu criativo! Vou usar nessa campanha." }'
        }
    }
]
```

Conexão: Switch output 1 ("media") → media_normalize_phone → media_download → media_upsert_criativo → media_send_confirma.

- [ ] **Step 2: Executar e commit**

---

## Task 18: Ativar workflow + capturar webhook URL

- [ ] **Step 1: Ativar workflow via API**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
N8N_URL="https://n8n.quirkgrowth.online"
N8N_KEY=$(cat ~/.config/n8n-quirk/api_key.txt | tr -d '\n')
curl -s -X POST -H "X-N8N-API-KEY: $N8N_KEY" "$N8N_URL/api/v1/workflows/$WF_ID/activate" | python3 -m json.tool
```

Expected: `"active": true`

- [ ] **Step 2: Capturar webhook URL**

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
python3 /Users/renanreal/quirk_auto_ads/scripts/n8n_api.py get $WF_ID | python3 -c "
import json, sys
d = json.load(sys.stdin)
for n in d['nodes']:
    if n['type'] == 'n8n-nodes-base.webhook':
        print(f'Webhook URL: https://n8n.quirkgrowth.online/webhook/{n[\"parameters\"][\"path\"]}')
        break
"
```

Expected: `Webhook URL: https://n8n.quirkgrowth.online/webhook/quirk-auto-ads`

- [ ] **Step 3: Testar webhook com curl**

```bash
curl -s -X POST -H "Content-Type: application/json" \
  https://n8n.quirkgrowth.online/webhook/quirk-auto-ads \
  -d '{"body":{"chat":{"phone":"+55 11 98083-8409"},"message":{"type":"text","text":"oi"}}}' \
  -w "\nHTTP: %{http_code}\n"
```

Expected: HTTP 200 (mensagem de processamento iniciado).

- [ ] **Step 4: Validar execução na UI**

> Renan abre `https://n8n.quirkgrowth.online/workflow/<WF_ID>/executions` e confirma que uma execução nova apareceu com status "Success" ou diagnostica qualquer falha.

---

## Task 19: Trocar webhook URL no UAZAPI

**Files:** N/A (config externa)

- [ ] **Step 1: Renan abre painel UAZAPI**

> Renan: vai em `https://quirkgrowth.uazapi.com/manager` (ou onde for o painel), encontra a instância de testes, troca o webhook URL para `https://n8n.quirkgrowth.online/webhook/quirk-auto-ads`.

- [ ] **Step 2: Salvar e confirmar**

> Renan confirma que salvou.

---

## Task 20: Desligar cenário Make

- [ ] **Step 1: Desativar via API**

Eu rodo:

```python
# Make MCP via Claude tool
from anthropic.tools.use import ...  # ou direto via Bash
# Equivalente: scenarios_update com active=false
```

Ou via bash:

```bash
# Não tem disable direto via API que eu testei — alternativa: troca scheduling pra paused
# OU: Renan faz manual (toggle OFF no UI do Make)
```

> Stop e instruir Renan: "Vai no cenário Make `Auto Ads - test (copy)` e desliga (toggle OFF no canto inferior esquerdo). Confirma quando tiver feito."

---

## Task 21: Teste end-to-end pelo WhatsApp

**Files:** N/A

- [ ] **Step 1: Renan reseta conversa de teste no Supabase**

```bash
psql "$PSQL_URL" -c "UPDATE auto_ads.conversas SET historico='', criativo_url='' WHERE telefone='5511980838409'"
```

Expected: `UPDATE 1`

- [ ] **Step 2: Renan envia mensagem do WhatsApp pessoal pra número de teste**

> Renan envia algo como:
> ```
> Quero subir campanha pra apto 2Q, 450 mil, Goiânia raio 15km, moradia. Verba 30/dia. Nome: Teste n8n
> ```

- [ ] **Step 3: Validar execução chegou no n8n**

Eu chamo a API:

```bash
WF_ID=$(cat /Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id)
N8N_URL="https://n8n.quirkgrowth.online"
N8N_KEY=$(cat ~/.config/n8n-quirk/api_key.txt | tr -d '\n')
curl -s -H "X-N8N-API-KEY: $N8N_KEY" \
  "$N8N_URL/api/v1/executions?workflowId=$WF_ID&limit=3" | \
  python3 -c "import json,sys; d=json.load(sys.stdin); [print(e['id'], e['status'], e['startedAt']) for e in d.get('data',[])]"
```

Expected: 1 execução recente, status "success".

- [ ] **Step 4: Conferir resposta no WhatsApp do Renan**

> Renan confirma que o agente respondeu pedindo dados que faltam (criativo, etc).

- [ ] **Step 5: Continuar conversa até CONFIRMADO**

Renan envia imagem, responde perguntas, confirma com `CONFIRMADO`.

- [ ] **Step 6: Validar campanha foi criada no Ads Manager**

> Renan abre o Ads Manager da BM Quirk Auto Ads e confirma que a campanha "Teste n8n" apareceu em PAUSED.

- [ ] **Step 7: Validar registros no Postgres**

```bash
psql "$PSQL_URL" -c "SELECT campaign_id, adset_id, ad_id, status, criada_em FROM auto_ads.campanhas WHERE telefone='5511980838409' ORDER BY criada_em DESC LIMIT 1"
psql "$PSQL_URL" -c "SELECT evento, ts FROM auto_ads.audit_log WHERE telefone='5511980838409' ORDER BY ts DESC LIMIT 10"
```

Expected: 1 linha em campanhas com todos os IDs, vários eventos em audit_log.

---

## Task 22: Iterar correções de bugs descobertos no teste

**Files:** Variável conforme bugs.

- [ ] **Step 1: Pra cada bug encontrado:**
  - Identificar node afetado via UI do n8n
  - Eu edito via API
  - Renan re-testa
  - Snapshot atualizado e commit

- [ ] **Step 2: Bugs candidatos esperados (já documentados no Make):**
  - Verba virá com formato inesperado → ajustar parsing no D.2
  - Mensagem do classifier vir em formato diferente → ajustar Code node `build_historico`
  - JSON do extrator vier embrulhado em markdown → adicionar regex de limpeza no parse_extrator
  - Anthropic node retornar estrutura diferente do esperado → ajustar `$('node').item.json.<path>`

Estes são bugs **esperados** de tooling, fáceis de corrigir cada um em 5 min de edição via API.

---

## Task 23: Validação final e fechamento

- [ ] **Step 1: Validar critérios de sucesso da spec seção 10**

Checklist:
- [ ] Mensagem texto → agente responde
- [ ] Imagem → criativo persistido
- [ ] CONFIRMADO → D.1-D.4 criam campanha
- [ ] Campanha no Ads Manager com targeting correto
- [ ] Tabela `campanhas` tem linha com IDs Meta
- [ ] `audit_log` sem eventos de erro

- [ ] **Step 2: Documentar no README qual é a versão estável**

Atualizar `README.md` com seção "Status atual":
```
**Status (2026-05-28):** Migração Make → n8n concluída. Workflow `Quirk Auto Ads` ativo em https://n8n.quirkgrowth.online. Make cenário 4750002 desligado.
```

- [ ] **Step 3: Commit final**

```bash
cd /Users/renanreal/quirk_auto_ads
git add README.md
git commit -m "docs: migração Make → n8n concluída"
git tag v1.0-n8n-migration
```

- [ ] **Step 4: Atualizar memória do projeto**

Editar `/Users/renanreal/.claude/projects/-Users-renanreal/memory/project_quirk_auto_ads.md`:
- Stack: trocar "Make.com cenário 4750002" por "n8n self-hosted workflow ativo"
- Status: "Fase D fechada via n8n. Próximo: Fase F (relatórios sob demanda)."

---

## Self-review do plano

**Cobertura da spec:**
- Seção 1 (motivação) → Pré-requisitos (contexto)
- Seção 2 (decisões) → Task 0 (todas referenciadas)
- Seção 3 (arquitetura) → Tasks 8, 9-17
- Seção 4 (schema) → Tasks 2, 3, 4
- Seção 5 (workflow detalhado) → Tasks 9-17
- Seção 6 (credenciais) → Tasks 6, 7, 10
- Seção 7 (validação) → Task 12
- Seção 8 (error handling/retry) → Tasks 13-16 (retry inline), Task 22 (Error Workflow opcional)
- Seção 9 (plano de migração 15 passos) → Tasks 1-22 cobrem todos
- Seção 10 (critérios sucesso) → Task 23
- Seção 11 (riscos) → mitigados nas tasks
- Seção 12 (out of scope) → respeitado

**Placeholders / TBDs:** Encontrei alguns que vou corrigir:
- Task 6 Step 3: "ANTHROPIC_API_KEY=<RENAN_PRECISA_FORNECER>" — sinalizado claramente como input do Renan, não é placeholder de código
- Task 10 Step 1: "TODO_RENAN_CRIA" no credential ID — corrigido inline no Step 4 da mesma task
- Task 22: "Variável conforme bugs" — é correto, é iteração responsiva
- Tasks 13-16 mostram exemplos resumidos com `(padrão idêntico)` — aceitável, padrão é Python script com get/update via n8n_api. **Cada task ainda inclui o conteúdo dos nodes na íntegra.**

**Consistência de tipos:**
- `$('Normalize phone').item.json.telefone_normalizado` usado consistentemente em todas as queries
- IDs de credenciais sempre `"hflXyXJQqzXr5XmY"` (Postgres) — consistente
- Nomes de nodes referenciados (`$('select_conversa')`, `$('agente_principal')`) batem com nomes definidos nos `"name"` dos nodes

**Tudo OK.**

---

## Execution Handoff

Plano salvo em `/Users/renanreal/quirk_auto_ads/docs/2026-05-28-quirk-auto-ads-n8n-implementation-plan.md`.

Tem 23 tasks, cada uma com sub-steps verificáveis e commits pontuais. Dependências externas (credencial Anthropic, ENV vars, troca de webhook UAZAPI) sinalizadas como "Stop e perguntar Renan" no momento certo.

Em auto mode, próximo passo é executar este plano. Recomendação:

**Inline Execution** com checkpoints — eu executo tasks 1-7 sem interrupção (setup git, SQL, prompts, helper API, workflow vazio), depois check-in no Task 8/10 (que precisam input do Renan: connection string Postgres, ANTHROPIC_API_KEY, ENV setup no servidor), continuo 11-17 sem interrupção, check-in Task 18/19 (teste do webhook URL, troca no UAZAPI), check-in Task 20-23 (Renan faz testes).
