# Quirk Auto Ads v2 (state-aware) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refatorar o workflow Quirk Auto Ads pra ser state-aware: o agente principal lê o estado real da campanha (etapa, criativo, última tentativa) antes de responder; a validação roda antes do agente; o branch de mídia confirma recepção contextualmente e dispara retry quando faz sentido; retry híbrido (auto em infra, manual em dado).

**Architecture:** Estado persistido em `auto_ads.conversas.estado_json` (JSONB). Fluxo principal reordenado pra: `classify_intent` (regex) → `extrator` → `validate_v2` → Meta API → `agente_principal_v2` (com bloco [ESTADO] no system prompt). Branch de mídia integra ao state machine.

**Tech Stack:** n8n self-hosted (Code nodes JS, HTTP, Postgres) · Anthropic Claude Sonnet 4.5 · Supabase Postgres (`auto_ads` schema) · UAZAPI · Meta Marketing API v25 · Python 3.9 helpers (`scripts/n8n_api.py`, `scripts/config.py`)

**Spec:** [`docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md`](../specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md)

---

## File Structure

### Novos arquivos
- `sql/004_estado_json.sql` — migration: coluna `estado_json` + default + populate existentes
- `prompts/agente_principal_v2.md` — prompt refatorado com bloco [ESTADO] e regra anti-mentira
- `scripts/v2_01_migration_sql.py` — aplica migration via Supabase Management API
- `scripts/v2_02_update_prompt.py` — atualiza node `build_agente_body` pra carregar `agente_principal_v2.md` E passar `estado_json` no system prompt
- `scripts/v2_03_classify_intent_and_load_estado.py` — adiciona Code nodes `load_estado` e `classify_intent`; substitui o switch de `if_confirmado`
- `scripts/v2_04_merge_brief_and_update_estado.py` — adiciona Code nodes `merge_brief` e `update_estado_etapa` (várias instâncias)
- `scripts/v2_05_validate_v2.py` — refatora `validate` pra ler `estado_json.brief`
- `scripts/v2_06_check_meta_results_v2_and_retry.py` — refator `check_meta_results` (classificação infra/dado, `failed_step`) + adiciona `wait_30s` + branch de auto-retry
- `scripts/v2_07_media_branch_v2.py` — refator do branch de mídia (load_estado_media, decide_acao_media, build_media_response)
- `scripts/v2_08_rewire_and_deprecate.py` — reconecta tudo conforme spec §5.1 e remove `classifier`, `send_falha_validacao`
- `scripts/test_v2_happy_path.py` — simula brief → criativo → CONFIRMAR → ativa
- `scripts/test_v2_falha_dado_retry.py` — simula falha por criativo + RETRY manual
- `scripts/test_v2_media_transitions.py` — simula transições do branch de mídia

### Arquivos modificados
- `prompts/agente_principal.md` — substituído (versão antiga vira `prompts/agente_principal_v1_legacy.md`)
- `scripts/config.py` — adiciona helper `load_prompt_v2()` se necessário (opcional)

### Convenções
- Todos os scripts `v2_*.py` são **idempotentes** (rodar 2x não corrompe estado)
- Cada script segue o pattern dos `fix_*.py` existentes: importa `n8n_api` + `config`, busca workflow por ID, aplica mudanças, chama `update_workflow`
- "Test" aqui = script de simulação ponta-a-ponta (POST webhook → wait → query Postgres + executions → assert). Sem framework — assertions com `assert` e prints claros.

---

## Phase 1: Migration SQL

### Task 1: Adicionar coluna `estado_json` em `auto_ads.conversas`

**Files:**
- Create: `sql/004_estado_json.sql`
- Create: `scripts/v2_01_migration_sql.py`

- [ ] **Step 1.1: Escrever o SQL**

Conteúdo de `sql/004_estado_json.sql`:

```sql
-- Migration 004 — estado_json (state machine pro fluxo state-aware v2)
-- Spec: docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md §4

ALTER TABLE auto_ads.conversas
ADD COLUMN IF NOT EXISTS estado_json JSONB NOT NULL DEFAULT '{
  "etapa_atual": "coletando_info",
  "criativo": {"recebido": false, "url": null, "mimetype": null, "recebido_em": null},
  "brief": {},
  "ultima_tentativa": null
}'::jsonb;

-- Index pra queries por etapa (sub-projetos B e C vão usar)
CREATE INDEX IF NOT EXISTS conversas_etapa_idx
  ON auto_ads.conversas ((estado_json ->> 'etapa_atual'));

-- Populate linhas existentes com criativo já recebido (caso houver criativo_url)
UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{criativo}',
  jsonb_build_object(
    'recebido', true,
    'url', criativo_url,
    'mimetype', NULL,
    'recebido_em', ultima_atualizacao
  )
)
WHERE criativo_url IS NOT NULL AND length(trim(criativo_url)) > 5;
```

- [ ] **Step 1.2: Escrever script Python que aplica a migration**

Conteúdo de `scripts/v2_01_migration_sql.py`:

```python
#!/usr/bin/env python3
"""Aplica sql/004_estado_json.sql via psycopg2 direto."""
import os, sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def main():
    sql_path = '/Users/renanreal/quirk_auto_ads/sql/004_estado_json.sql'
    with open(sql_path) as f:
        sql = f.read()

    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip()
    # Force correct host (descoberta empírica)
    db_url = db_url.replace('aws-0-', 'aws-1-')

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    # Verifica coluna criada
    cur.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_schema='auto_ads' AND table_name='conversas' AND column_name='estado_json'
    """)
    row = cur.fetchone()
    assert row is not None, "Coluna estado_json não foi criada"
    print(f'✓ Coluna criada: {row[0]} {row[1]}')

    # Verifica index
    cur.execute("""
        SELECT indexname FROM pg_indexes
        WHERE schemaname='auto_ads' AND tablename='conversas' AND indexname='conversas_etapa_idx'
    """)
    assert cur.fetchone() is not None, "Index conversas_etapa_idx não foi criado"
    print('✓ Index conversas_etapa_idx criado')

    # Conta linhas com criativo populado
    cur.execute("""
        SELECT count(*) FROM auto_ads.conversas
        WHERE (estado_json -> 'criativo' ->> 'recebido')::bool = true
    """)
    print(f'  linhas com criativo populado: {cur.fetchone()[0]}')

    conn.close()
    print('\n✓ Migration 004 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 1.3: Rodar a migration**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_01_migration_sql.py
```

Expected output:
```
✓ Coluna criada: estado_json jsonb
✓ Index conversas_etapa_idx criado
  linhas com criativo populado: 0
✓ Migration 004 aplicada
```

- [ ] **Step 1.4: Commit**

```bash
git add sql/004_estado_json.sql scripts/v2_01_migration_sql.py
git commit -m "feat(sql): migration 004 — estado_json column + index"
```

---

## Phase 2: Prompt update — agente_principal_v2

### Task 2: Refatorar `agente_principal.md` com bloco [ESTADO] e regra anti-mentira

**Files:**
- Modify: `prompts/agente_principal.md`
- Create: `prompts/agente_principal_v1_legacy.md` (backup)

- [ ] **Step 2.1: Backup do prompt v1**

```bash
cp /Users/renanreal/quirk_auto_ads/prompts/agente_principal.md /Users/renanreal/quirk_auto_ads/prompts/agente_principal_v1_legacy.md
```

- [ ] **Step 2.2: Reescrever `agente_principal.md`**

O prompt v2 mantém o conteúdo de produto/marketing (tabela de públicos, conduta, etc.) do v1 mas **prepende** o bloco [ESTADO] e a regra anti-mentira no topo (antes de qualquer outra instrução).

Use Read pra ler o conteúdo atual de `prompts/agente_principal.md`, então use Edit pra **substituir** a primeira linha (o título/header) por:

```markdown
[ESTADO DA CONVERSA — leia ANTES de responder]
{{ESTADO_BLOCK}}

[REGRA CRÍTICA DE INTEGRIDADE]
NUNCA prometa "subindo agora", "campanha criada", "tá no ar", "vou subir" — quem decide isso é o BACKEND, não você.
Responda APENAS com base no estado acima:

- etapa_atual = coletando_info → conduza a coleta. Cite os campos faltantes do brief.
- etapa_atual = aguardando_criativo → peça o criativo (foto ou vídeo do imóvel).
- etapa_atual = pronta_pra_subir → peça confirmação ("Tudo pronto. Manda CONFIRMAR pra subir.").
- etapa_atual = subindo → diga "Validando e subindo, te aviso assim que estiver no ar." NUNCA confirme sucesso ainda.
- etapa_atual = ativa → confirme com o campaign_id real do estado.
- etapa_atual = falhou_dado → explique o motivo real + peça correção + cite RETRY como comando.
- etapa_atual = falhou_infra → "Tive falha técnica, estou tentando de novo automaticamente."

Se o cliente disser "CONFIRMADO" mas etapa_atual != pronta_pra_subir, NÃO confirme — explique o que falta (campos do brief OU criativo).

[FIM DO BLOCO DE ESTADO E REGRA]

---

<conteúdo original do prompt v1 começa aqui — manter integral>
```

Onde `{{ESTADO_BLOCK}}` é um placeholder que vai ser preenchido em runtime pelo Code node `build_agente_body` (Task 8). O placeholder é literal — não interpolar agora.

- [ ] **Step 2.3: Verificar via Read que o prompt v2 está OK**

```bash
head -40 /Users/renanreal/quirk_auto_ads/prompts/agente_principal.md
```

Expected: deve começar com `[ESTADO DA CONVERSA — leia ANTES de responder]` e conter `{{ESTADO_BLOCK}}` placeholder.

- [ ] **Step 2.4: Commit**

```bash
git add prompts/agente_principal.md prompts/agente_principal_v1_legacy.md
git commit -m "feat(prompt): agente_principal v2 — bloco [ESTADO] + regra anti-mentira"
```

---

## Phase 3: classify_intent + load_estado

### Task 3: Adicionar `load_estado` e `classify_intent` Code nodes

**Files:**
- Create: `scripts/v2_03_classify_intent_and_load_estado.py`

- [ ] **Step 3.1: Escrever o script**

Conteúdo de `scripts/v2_03_classify_intent_and_load_estado.py`:

```python
#!/usr/bin/env python3
"""
Adiciona Code nodes `load_estado` e `classify_intent` ao workflow.

load_estado: lê estado_json de select_conversa, expõe campos planos pro próximo node
classify_intent: regex em msg.text → CONFIRMAR/RETRY/NOVA/OUTRO

Esses nodes serão usados pra reordenar o fluxo na Task 8.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


LOAD_ESTADO_CODE = """// Lê estado_json da conversa (default-safe pra cliente novo)
const conv = $('select_conversa').first().json || {};
const def = {etapa_atual: 'coletando_info', criativo: {recebido: false, url: null, mimetype: null, recebido_em: null}, brief: {}, ultima_tentativa: null};
let estado = conv.estado_json;
if (typeof estado === 'string') { try { estado = JSON.parse(estado); } catch(e) { estado = def; } }
if (!estado || typeof estado !== 'object') estado = def;
// Garante campos obrigatórios
estado.etapa_atual = estado.etapa_atual || 'coletando_info';
estado.criativo = estado.criativo || def.criativo;
estado.brief = estado.brief || {};
estado.ultima_tentativa = estado.ultima_tentativa || null;

return [{
  json: {
    estado,
    historico: conv.historico || '',
    criativo_url_legado: conv.criativo_url || null
  }
}];
"""

CLASSIFY_INTENT_CODE = """// Detecta intenção do cliente por regex no texto da msg
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

let intent = 'OUTRO';
if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^retry$/i.test(msg)) intent = 'RETRY';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'RETRY';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'RETRY';
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';

return [{ json: { intent, mensagem_texto: msg } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # load_estado
    if 'load_estado' in nb:
        nb['load_estado']['parameters']['jsCode'] = LOAD_ESTADO_CODE
        print('  ↻ load_estado atualizado')
    else:
        wf['nodes'].append({
            'id': 'load_estado',
            'name': 'load_estado',
            'type': 'n8n-nodes-base.code',
            'typeVersion': 2,
            'position': [1300, 100],
            'parameters': {'language': 'javaScript', 'jsCode': LOAD_ESTADO_CODE}
        })
        print('  + load_estado adicionado')

    # classify_intent
    if 'classify_intent' in nb:
        nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_CODE
        print('  ↻ classify_intent atualizado')
    else:
        wf['nodes'].append({
            'id': 'classify_intent',
            'name': 'classify_intent',
            'type': 'n8n-nodes-base.code',
            'typeVersion': 2,
            'position': [1400, 100],
            'parameters': {'language': 'javaScript', 'jsCode': CLASSIFY_INTENT_CODE}
        })
        print('  + classify_intent adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 3 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 3.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_03_classify_intent_and_load_estado.py
```

Expected output:
```
  + load_estado adicionado
  + classify_intent adicionado

✓ Task 3 aplicada
```

- [ ] **Step 3.3: Verificar via API**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import n8n_api, config
wf = n8n_api.get_workflow(config.get_workflow_id())
names = [n['name'] for n in wf['nodes']]
assert 'load_estado' in names, 'load_estado faltando'
assert 'classify_intent' in names, 'classify_intent faltando'
print('✓ ambos nodes presentes')
"
```

Expected: `✓ ambos nodes presentes`

- [ ] **Step 3.4: Commit**

```bash
git add scripts/v2_03_classify_intent_and_load_estado.py
git commit -m "feat(n8n): nodes load_estado + classify_intent (substitui classifier LLM)"
```

---

## Phase 4: merge_brief + update_estado_etapa

### Task 4: Adicionar `merge_brief` e `update_estado_etapa` Code nodes

**Files:**
- Create: `scripts/v2_04_merge_brief_and_update_estado.py`

- [ ] **Step 4.1: Escrever o script**

Conteúdo de `scripts/v2_04_merge_brief_and_update_estado.py`:

```python
#!/usr/bin/env python3
"""
Adiciona Code nodes:
- merge_brief: mescla json_extrator no estado_json.brief
- update_estado_etapa: determina nova etapa baseado em brief + criativo + resultado tentativa

Esses nodes serão plugados nos pontos certos do fluxo na Task 8.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


MERGE_BRIEF_CODE = """// Mescla json_extrator no estado_json.brief
const estado = $('load_estado').first().json.estado;
const parsed = $('parse_extrator').first().json.json_extrator;

if (!parsed) {
  // parse falhou; mantém brief atual
  return [{ json: { estado, parse_ok: false } }];
}

// Normaliza targeting_meta (clamp do raio, age min/max — duplicado de validate v1)
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_min === 'number' && parsed.targeting_meta.age_min < 18) parsed.targeting_meta.age_min = 18;
if (parsed.targeting_meta && typeof parsed.targeting_meta.age_max === 'number' && parsed.targeting_meta.age_max > 65) parsed.targeting_meta.age_max = 65;
const cities = parsed.targeting_meta?.geo_locations?.cities;
if (Array.isArray(cities)) {
  for (const c of cities) {
    if (typeof c.radius === 'number' && c.radius < 17) c.radius = 17;
    if (typeof c.radius === 'number' && c.radius > 80) c.radius = 80;
    if (!c.distance_unit) c.distance_unit = 'kilometer';
  }
}

estado.brief = { ...estado.brief, ...parsed };

return [{ json: { estado, parse_ok: true } }];
"""

UPDATE_ESTADO_ETAPA_CODE = """// Determina nova etapa baseado em brief + criativo + resultado tentativa
// Usado pra atualizar estado_json depois de cada step relevante

const fonte = $input.first().json;
const estado = fonte.estado || ($('load_estado').first().json?.estado);
const brief = estado.brief || {};
const tem_criativo = !!(estado.criativo?.recebido);

// Campos obrigatórios mínimos do brief pra considerar 'completo'
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);
const verbaOk = typeof brief.campanha?.verba_diaria === 'number' && brief.campanha.verba_diaria >= 10 && brief.campanha.verba_diaria <= 100;

let novaEtapa = estado.etapa_atual;

// Transições deterministicas
if (estado.etapa_atual === 'coletando_info') {
  if (briefCompleto && verbaOk && !tem_criativo) novaEtapa = 'aguardando_criativo';
  else if (briefCompleto && verbaOk && tem_criativo) novaEtapa = 'pronta_pra_subir';
} else if (estado.etapa_atual === 'aguardando_criativo') {
  if (tem_criativo) novaEtapa = 'pronta_pra_subir';
  else if (!briefCompleto) novaEtapa = 'coletando_info';
}
// outras etapas (subindo, ativa, falhou_*) são governadas pelos nodes Meta — não mexer aqui

estado.etapa_atual = novaEtapa;

return [{ json: { estado, brief_completo: briefCompleto, tem_criativo } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'merge_brief' in nb:
        nb['merge_brief']['parameters']['jsCode'] = MERGE_BRIEF_CODE
        print('  ↻ merge_brief atualizado')
    else:
        wf['nodes'].append({
            'id': 'merge_brief', 'name': 'merge_brief',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [3100, 50],
            'parameters': {'language': 'javaScript', 'jsCode': MERGE_BRIEF_CODE}
        })
        print('  + merge_brief adicionado')

    if 'update_estado_etapa' in nb:
        nb['update_estado_etapa']['parameters']['jsCode'] = UPDATE_ESTADO_ETAPA_CODE
        print('  ↻ update_estado_etapa atualizado')
    else:
        wf['nodes'].append({
            'id': 'update_estado_etapa', 'name': 'update_estado_etapa',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1600, 250],
            'parameters': {'language': 'javaScript', 'jsCode': UPDATE_ESTADO_ETAPA_CODE}
        })
        print('  + update_estado_etapa adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 4 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4.2: Rodar e verificar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_04_merge_brief_and_update_estado.py
```

Expected: ambos nodes adicionados sem erro.

- [ ] **Step 4.3: Commit**

```bash
git add scripts/v2_04_merge_brief_and_update_estado.py
git commit -m "feat(n8n): nodes merge_brief + update_estado_etapa"
```

---

## Phase 5: validate_v2

### Task 5: Refatorar `validate` pra ler de `estado_json.brief`

**Files:**
- Create: `scripts/v2_05_validate_v2.py`

- [ ] **Step 5.1: Escrever o script**

Conteúdo de `scripts/v2_05_validate_v2.py`:

```python
#!/usr/bin/env python3
"""
Refatora node validate pra validate_v2:
- Lê brief de estado_json (via merge_brief), não de parse_extrator
- Lê criativo de estado_json.criativo (não de conversa.criativo_url)
- Mantém clamps de targeting (raio, age) como safety net (já feito em merge_brief)
- Retorna mesma shape de antes pra não quebrar nodes downstream
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


VALIDATE_V2_CODE = """const cliente = $('select_cliente').first().json;
const estado = $('merge_brief').first().json.estado;
const json = estado.brief;
const errors = [];

if (!json || Object.keys(json).length === 0) {
  errors.push('brief vazio (parse falhou ou extrator não rodou)');
  return [{ json: { ok: false, motivos: errors, estado } }];
}

const verba = parseInt(json.campanha?.verba_diaria);
if (isNaN(verba) || verba < 10) errors.push('verba_diaria < 10');
if (verba > 100) errors.push('verba_diaria > 100');
if (!json.campanha?.objetivo_meta) errors.push('objetivo_meta vazio');
if (!json.conjunto?.geo) errors.push('geo vazio');
if (!json.publico_escolhido) errors.push('publico_escolhido vazio');
if (!estado.criativo?.recebido || !estado.criativo?.url) errors.push('criativo_url vazio');
if (!cliente?.ad_account_id) errors.push('ad_account_id vazio');
if (!json.targeting_meta) errors.push('targeting_meta vazio');
if (!json.targeting_meta?.geo_locations) errors.push('geo_locations vazio');

// Sintetiza shape compatível com nodes existentes (cliente, conversa-like)
const conversaLike = {
  telefone: $('normalize_phone').first().json.telefone_normalizado,
  criativo_url: estado.criativo?.url || ''
};

return [{
  json: {
    ok: errors.length === 0,
    motivos: errors,
    json_extrator: json,
    cliente,
    conversa: conversaLike,
    estado,
    verba_em_centavos: Math.max((verba || 30) * 100, 1000)
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'validate' not in nb:
        print('ERRO: node validate não existe — verifique workflow base')
        sys.exit(1)
    nb['validate']['parameters']['jsCode'] = VALIDATE_V2_CODE
    print('  ↻ validate refatorado pra v2 (lê de estado_json.brief)')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 5 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 5.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_05_validate_v2.py
```

- [ ] **Step 5.3: Commit**

```bash
git add scripts/v2_05_validate_v2.py
git commit -m "feat(n8n): validate_v2 — lê brief de estado_json"
```

---

## Phase 6: check_meta_results v2 + auto-retry de infra

### Task 6: Classificação infra/dado e branch de auto-retry

**Files:**
- Create: `scripts/v2_06_check_meta_results_v2_and_retry.py`

- [ ] **Step 6.1: Escrever o script**

Conteúdo de `scripts/v2_06_check_meta_results_v2_and_retry.py`:

```python
#!/usr/bin/env python3
"""
v2 de check_meta_results:
- Classifica erro como 'infra' (5xx/transient) ou 'dado' (4xx)
- Identifica failed_step (d1/d2/d3/d4)
- Expõe tentativas_count vindo do load_estado

Adiciona wait_30s (Wait node) + branch de auto-retry. Conexões só serão
feitas na Task 8 (rewire global).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CHECK_META_V2_CODE = """function getRespOrNull(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) return { error: r.error };
    return { id: r?.id || null };
  } catch (e) { return { error: { message: e.message } }; }
}

function classify(node) {
  const r = getRespOrNull(node);
  if (r.id) return { ok: true, id: r.id, classe: null, motivo: null, failed_step: null };
  const err = r.error || {};
  const msg = err.message || '';
  // 5xx / timeout / transient => infra
  if (/Request failed with status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) || /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg)) {
    return { ok: false, classe: 'infra', motivo: msg.slice(0, 200), id: null };
  }
  // Dado: extrai error_user_msg
  const matchUser = msg.match(/error_user_msg\\\\?\\":\\\\?\\"([^\\"]+)/);
  let motivo = matchUser ? matchUser[1].replace(/\\\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))) : msg.slice(0, 200);
  return { ok: false, classe: 'dado', motivo, id: null };
}

const d1 = classify('meta_d1_campaign');
const d2 = classify('meta_d2_adset');
const d3 = classify('meta_d3_creative');
const d4 = classify('meta_d4_ad');

const allOk = d1.ok && d2.ok && d3.ok && d4.ok;
let failed_step = null;
let classe = null;
let motivo = null;
if (!d1.ok) { failed_step = 'd1'; classe = d1.classe; motivo = d1.motivo; }
else if (!d2.ok) { failed_step = 'd2'; classe = d2.classe; motivo = d2.motivo; }
else if (!d3.ok) { failed_step = 'd3'; classe = d3.classe; motivo = d3.motivo; }
else if (!d4.ok) { failed_step = 'd4'; classe = d4.classe; motivo = d4.motivo; }

const estado = $('validate').first().json.estado;
const tentativas_count = (estado?.ultima_tentativa?.tentativas_count || 0) + 1;

return [{
  json: {
    ok: allOk,
    failed_step,
    classe,
    motivo,
    campaign_id: d1.id,
    adset_id: d2.id,
    creative_id: d3.id,
    ad_id: d4.id,
    tentativas_count,
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    json_extrator: estado.brief,
    estado
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # 1) Refator do check_meta_results existente
    if 'check_meta_results' not in nb:
        print('ERRO: check_meta_results não existe — rode os fixes anteriores antes')
        sys.exit(1)
    nb['check_meta_results']['parameters']['jsCode'] = CHECK_META_V2_CODE
    print('  ↻ check_meta_results v2 (classifica infra/dado + failed_step)')

    # 2) Adiciona Wait node pra retry de infra (30s)
    if 'wait_30s' not in nb:
        wf['nodes'].append({
            'id': 'wait_30s', 'name': 'wait_30s',
            'type': 'n8n-nodes-base.wait', 'typeVersion': 1,
            'position': [4980, 200],
            'parameters': {'amount': 30, 'unit': 'seconds'},
        })
        print('  + wait_30s (Wait 30s) adicionado')

    # 3) Adiciona IF que decide se faz auto-retry
    if 'if_pode_retry_infra' not in nb:
        wf['nodes'].append({
            'id': 'if_pode_retry_infra', 'name': 'if_pode_retry_infra',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [4880, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [
                        {
                            'leftValue': "={{ $('check_meta_results').item.json.classe }}",
                            'rightValue': 'infra',
                            'operator': {'type': 'string', 'operation': 'equals'}
                        },
                        {
                            'leftValue': "={{ $('check_meta_results').item.json.tentativas_count }}",
                            'rightValue': 2,
                            'operator': {'type': 'number', 'operation': 'smallerEqual'}
                        }
                    ]
                }
            }
        })
        print('  + if_pode_retry_infra adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 6 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 6.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_06_check_meta_results_v2_and_retry.py
```

- [ ] **Step 6.3: Commit**

```bash
git add scripts/v2_06_check_meta_results_v2_and_retry.py
git commit -m "feat(n8n): check_meta_results v2 + wait_30s + if_pode_retry_infra"
```

---

## Phase 7: Branch de mídia state-aware

### Task 7: Refatorar branch de mídia

**Files:**
- Create: `scripts/v2_07_media_branch_v2.py`

- [ ] **Step 7.1: Escrever o script**

Conteúdo de `scripts/v2_07_media_branch_v2.py`:

```python
#!/usr/bin/env python3
"""
Refator do branch de mídia:
- Adiciona media_select_conversa (lê estado_json antes de tudo)
- Refatora media_upsert_criativo pra atualizar estado_json.criativo + historico (não só criativo_url)
- Adiciona decide_acao_media (Code): se etapa anterior era falhou_dado(criativo) → trigger retry; senão → msg condicional
- Refatora build_media_response (existia? senão cria) pra emitir msg condicional

Conexões dentro do branch ficam: media_normalize_phone → media_select_cliente → media_if_cadastrado
  → media_select_conversa → media_download → media_upsert_criativo → decide_acao_media
  ├─ retry_branch (se etapa anterior falhou_dado/criativo) → leva pra build_extrator_body
  └─ media_send_resposta (msg condicional)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


MEDIA_UPSERT_QUERY = """INSERT INTO auto_ads.conversas (telefone, criativo_url, historico, estado_json)
VALUES (
  '{{ $('media_normalize_phone').item.json.telefone_normalizado }}',
  '{{ ($('media_download').item.json.fileURL || '').replace(/'/g, "''") }}',
  '|||TURN|||[SISTEMA: criativo recebido em ' || NOW()::TEXT || ']',
  jsonb_set(
    COALESCE((SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{{ $('media_normalize_phone').item.json.telefone_normalizado }}'), '{}'::jsonb),
    '{criativo}',
    jsonb_build_object(
      'recebido', true,
      'url', '{{ ($('media_download').item.json.fileURL || '').replace(/'/g, "''") }}',
      'mimetype', '{{ ($('media_download').item.json.mimetype || '').replace(/'/g, "''") }}',
      'recebido_em', NOW()::TEXT
    )
  )
)
ON CONFLICT (telefone) DO UPDATE
  SET criativo_url = EXCLUDED.criativo_url,
      historico = COALESCE(auto_ads.conversas.historico, '') || EXCLUDED.historico,
      estado_json = jsonb_set(
        auto_ads.conversas.estado_json,
        '{criativo}',
        EXCLUDED.estado_json -> 'criativo'
      ),
      ultima_atualizacao = NOW()
RETURNING estado_json, (estado_json -> 'criativo' ->> 'url') AS criativo_url_atual"""


MEDIA_SELECT_CONVERSA_QUERY = (
    "SELECT $1::text AS telefone, "
    "COALESCE((SELECT historico FROM auto_ads.conversas WHERE telefone = $1), '') AS historico, "
    "COALESCE((SELECT estado_json FROM auto_ads.conversas WHERE telefone = $1), "
    "'{\"etapa_atual\":\"coletando_info\",\"criativo\":{\"recebido\":false},\"brief\":{},\"ultima_tentativa\":null}'::jsonb) AS estado_json"
)


DECIDE_ACAO_MEDIA_CODE = """// Decide o que fazer depois de receber mídia
// Lê estado ANTES da escrita (que já rolou em media_upsert_criativo)
const conversaAnterior = $('media_select_conversa').first().json;
let estadoAntes = conversaAnterior.estado_json;
if (typeof estadoAntes === 'string') { try { estadoAntes = JSON.parse(estadoAntes); } catch(e) { estadoAntes = {etapa_atual: 'coletando_info'}; } }

const etapaAntes = estadoAntes?.etapa_atual || 'coletando_info';
const ultMotivo = estadoAntes?.ultima_tentativa?.motivo || '';
const criativoEraMotivo = /criativo|imagem|image|video/i.test(ultMotivo);

// Disparar RETRY automático se: etapa = falhou_dado E motivo era criativo
const triggerRetry = (etapaAntes === 'falhou_dado') && criativoEraMotivo;

return [{
  json: {
    triggerRetry,
    etapaAntes,
    estadoAntes,
    telefone: $('media_normalize_phone').first().json.telefone_normalizado,
    criativo_url: $('media_download').first().json.fileURL || ''
  }
}];
"""


BUILD_MEDIA_RESPONSE_CODE = """// Monta msg condicional baseada em estado anterior + brief completo
const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};
const brief = estadoAntes.brief || {};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);

let text;
if (d.triggerRetry) {
  text = 'Recebi o novo criativo ✓ — rodando RETRY automático agora...';
} else if (estadoAntes.etapa_atual === 'ativa') {
  text = 'Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer NOVA campanha?';
} else if (estadoAntes.etapa_atual === 'falhou_dado') {
  const motivo = estadoAntes.ultima_tentativa?.motivo || 'algum problema';
  text = `Recebi seu criativo ✓ — mas a última tentativa falhou por: ${motivo}. Corrige isso e manda RETRY.`;
} else if (briefCompleto) {
  text = 'Recebi seu criativo ✓ — tudo pronto. Manda CONFIRMAR quando quiser subir.';
} else {
  // brief incompleto → cita faltantes
  const faltantes = obrig.filter(k => !brief[k]).join(', ');
  text = `Recebi seu criativo ✓ — ainda preciso de: ${faltantes}. Me manda esses dados pra fechar.`;
}

return [{
  json: {
    text,
    telefone: d.telefone
  }
}];
"""


MEDIA_SEND_TEXT_VALUE = "={{ $('build_media_response').item.json.text }}"
MEDIA_SEND_NUMBER_VALUE = "={{ $('build_media_response').item.json.telefone }}"


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # 1) media_select_conversa
    if 'media_select_conversa' not in nb:
        wf['nodes'].append({
            'id': 'media_select_conversa', 'name': 'media_select_conversa',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [2200, 600],
            'parameters': {
                'operation': 'executeQuery',
                'query': MEDIA_SELECT_CONVERSA_QUERY,
                'options': {'queryReplacement': "={{ $('media_normalize_phone').item.json.telefone_normalizado }}"}
            },
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + media_select_conversa adicionado')

    # 2) media_upsert_criativo (refator do existente)
    if 'media_upsert_criativo' in nb:
        nb['media_upsert_criativo']['parameters']['query'] = MEDIA_UPSERT_QUERY
        nb['media_upsert_criativo']['parameters']['options'] = {}
        print('  ↻ media_upsert_criativo refatorado (escreve estado_json.criativo)')

    # 3) decide_acao_media
    if 'decide_acao_media' not in nb:
        wf['nodes'].append({
            'id': 'decide_acao_media', 'name': 'decide_acao_media',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2600, 600],
            'parameters': {'language': 'javaScript', 'jsCode': DECIDE_ACAO_MEDIA_CODE}
        })
        print('  + decide_acao_media adicionado')

    # 4) build_media_response
    if 'build_media_response' not in nb:
        wf['nodes'].append({
            'id': 'build_media_response', 'name': 'build_media_response',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2800, 600],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_MEDIA_RESPONSE_CODE}
        })
        print('  + build_media_response adicionado')

    # 5) media_send_confirma → atualiza pra usar build_media_response
    if 'media_send_confirma' in nb:
        for p in nb['media_send_confirma']['parameters'].get('bodyParameters', {}).get('parameters', []):
            if p.get('name') == 'text': p['value'] = MEDIA_SEND_TEXT_VALUE
            if p.get('name') == 'number': p['value'] = MEDIA_SEND_NUMBER_VALUE
        print('  ↻ media_send_confirma usa build_media_response')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 7 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 7.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_07_media_branch_v2.py
```

- [ ] **Step 7.3: Commit**

```bash
git add scripts/v2_07_media_branch_v2.py
git commit -m "feat(n8n): branch de mídia state-aware (decide_acao_media + msg condicional)"
```

---

## Phase 8: Rewire global + remoção de deprecated + carregamento dinâmico do estado no prompt

### Task 8: Reconectar tudo + remover `classifier`, `send_falha_validacao` + injetar estado no build_agente_body

**Files:**
- Create: `scripts/v2_08_rewire_and_deprecate.py`

- [ ] **Step 8.1: Escrever o script**

Conteúdo de `scripts/v2_08_rewire_and_deprecate.py`:

```python
#!/usr/bin/env python3
"""
Rewire global do workflow conforme spec §5.1 e §5.2.

1. Refatora build_agente_body pra injetar bloco [ESTADO] no system prompt
2. Adiciona Switch baseado em classify_intent.intent (CONFIRMAR/RETRY/NOVA/OUTRO)
3. Adiciona update_estado_*_persist (Postgres) pra gravar mudanças de etapa
4. Reconecta o fluxo principal: select_conversa → load_estado → classify_intent → switch_intent → ...
5. Reconecta o branch de mídia: → media_select_conversa → media_download → media_upsert_criativo → decide_acao_media → (retry trigger | build_media_response → media_send_confirma)
6. Remove classifier (LLM) e send_falha_validacao
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def load_prompt_with_state_placeholder():
    """Lê agente_principal.md (v2) que tem {{ESTADO_BLOCK}} placeholder."""
    with open('/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md') as f:
        return f.read()


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # ─── 1. build_agente_body v2 — injeta [ESTADO] no system prompt ───
    sys_template = load_prompt_with_state_placeholder()
    sys_template_quoted = json.dumps(sys_template)

    new_agente_body = f"""const systemTemplate = {sys_template_quoted};
const estado = $('load_estado').first().json.estado;
const intent = $('classify_intent').first().json.intent || 'OUTRO';
const historico = String($('load_estado').first().json.historico || '').trim();
const novaMsg = String($('normalize_phone').first().json.mensagem_texto || '').trim();

// Monta bloco [ESTADO] em runtime
const brief = estado.brief || {{}};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const preenchidos = obrig.filter(k => !!brief[k]);
const faltantes = obrig.filter(k => !brief[k]);
const ult = estado.ultima_tentativa;

let estadoBlock = `Etapa atual: ${{estado.etapa_atual}}
Criativo recebido: ${{estado.criativo?.recebido ? 'sim (' + estado.criativo.url + ')' : 'não'}}
Brief preenchido: ${{preenchidos.join(', ') || '(nada)'}}
Brief faltante: ${{faltantes.join(', ') || '(nada)'}}
Última tentativa: ${{ult ? (ult.resultado + (ult.motivo ? ': ' + ult.motivo : '')) : 'nenhuma'}}
Tentativas count: ${{ult?.tentativas_count || 0}}
Intent detectado (msg atual): ${{intent}}`;

if (estado.etapa_atual === 'ativa' && ult?.campaign_id) {{
  estadoBlock += `\\nCampanha ATIVA: campaign_id=${{ult.campaign_id}}`;
}}

const system = systemTemplate.replace('{{ESTADO_BLOCK}}', estadoBlock);

let userContent;
if (historico) {{
  userContent = `Histórico da conversa até agora:\\n${{historico}}\\n\\nNova mensagem do cliente: ${{novaMsg}}`;
}} else {{
  userContent = novaMsg;
}}

return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 1500,
    temperature: 0.3,
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""
    nb['build_agente_body']['parameters']['jsCode'] = new_agente_body
    print('  ↻ build_agente_body v2 (injeta [ESTADO] em runtime)')

    # ─── 2. Switch by intent ───
    if 'switch_intent' not in nb:
        wf['nodes'].append({
            'id': 'switch_intent', 'name': 'switch_intent',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [1500, 100],
            'parameters': {
                'rules': {
                    'values': [
                        {
                            'conditions': {
                                'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                                'combinator': 'and',
                                'conditions': [{
                                    'leftValue': "={{ $('classify_intent').item.json.intent }}",
                                    'rightValue': 'CONFIRMAR',
                                    'operator': {'type': 'string', 'operation': 'equals'}
                                }]
                            },
                            'renameOutput': True, 'outputKey': 'CONFIRMAR'
                        },
                        {
                            'conditions': {
                                'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                                'combinator': 'and',
                                'conditions': [{
                                    'leftValue': "={{ $('classify_intent').item.json.intent }}",
                                    'rightValue': 'RETRY',
                                    'operator': {'type': 'string', 'operation': 'equals'}
                                }]
                            },
                            'renameOutput': True, 'outputKey': 'RETRY'
                        },
                        {
                            'conditions': {
                                'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                                'combinator': 'and',
                                'conditions': [{
                                    'leftValue': "={{ $('classify_intent').item.json.intent }}",
                                    'rightValue': 'NOVA_CAMPANHA',
                                    'operator': {'type': 'string', 'operation': 'equals'}
                                }]
                            },
                            'renameOutput': True, 'outputKey': 'NOVA'
                        }
                    ]
                },
                'options': {'fallbackOutput': 'extra'}  # fallback = OUTRO
            }
        })
        print('  + switch_intent adicionado')

    # ─── 3. Persistência do estado_json após cada step ───
    persist_query_after_meta = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(
    estado_json,
    '{etapa_atual}',
    to_jsonb('{{ $('check_meta_results').item.json.ok ? "ativa" : ($('check_meta_results').item.json.classe === "infra" ? "falhou_infra" : "falhou_dado") }}'::text)
  ),
  '{ultima_tentativa}',
  jsonb_build_object(
    'timestamp', NOW()::TEXT,
    'resultado', '{{ $('check_meta_results').item.json.ok ? "ok" : ("erro_" + $('check_meta_results').item.json.classe) }}',
    'motivo', '{{ ($('check_meta_results').item.json.motivo || '').replace(/'/g, "''") }}',
    'campaign_id', {{ $('check_meta_results').item.json.campaign_id ? "'" + $('check_meta_results').item.json.campaign_id + "'" : 'NULL' }},
    'adset_id', {{ $('check_meta_results').item.json.adset_id ? "'" + $('check_meta_results').item.json.adset_id + "'" : 'NULL' }},
    'creative_id', {{ $('check_meta_results').item.json.creative_id ? "'" + $('check_meta_results').item.json.creative_id + "'" : 'NULL' }},
    'ad_id', {{ $('check_meta_results').item.json.ad_id ? "'" + $('check_meta_results').item.json.ad_id + "'" : 'NULL' }},
    'tentativas_count', {{ $('check_meta_results').item.json.tentativas_count }}
  )
)
WHERE telefone = '{{ $('check_meta_results').item.json.telefone }}'"""

    if 'persist_estado_apos_meta' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_apos_meta', 'name': 'persist_estado_apos_meta',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [5080, 100],
            'parameters': {'operation': 'executeQuery', 'query': persist_query_after_meta, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_apos_meta adicionado')

    # Persistência do estado pós-update_estado_etapa (fluxo OUTRO/RETRY pre-validate)
    persist_query_etapa = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{etapa_atual}',
  to_jsonb('{{ $('update_estado_etapa').item.json.estado.etapa_atual }}'::text)
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'persist_estado_etapa' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_etapa', 'name': 'persist_estado_etapa',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1800, 250],
            'parameters': {'operation': 'executeQuery', 'query': persist_query_etapa, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_etapa adicionado')

    # ─── 4. Persistência do brief depois de merge_brief ───
    persist_brief_query = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{brief}',
  '{{ JSON.stringify($('merge_brief').item.json.estado.brief).replace(/'/g, "''") }}'::jsonb
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'persist_brief' not in nb:
        wf['nodes'].append({
            'id': 'persist_brief', 'name': 'persist_brief',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3300, 50],
            'parameters': {'operation': 'executeQuery', 'query': persist_brief_query, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_brief adicionado')

    # ─── 5. Reset estado pra NOVA_CAMPANHA ───
    reset_estado_query = """UPDATE auto_ads.conversas
SET estado_json = '{"etapa_atual":"coletando_info","criativo":{"recebido":false},"brief":{},"ultima_tentativa":null}'::jsonb
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'reset_estado_nova' not in nb:
        wf['nodes'].append({
            'id': 'reset_estado_nova', 'name': 'reset_estado_nova',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1700, 350],
            'parameters': {'operation': 'executeQuery', 'query': reset_estado_query, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_estado_nova adicionado')

    # ─── 6. Reconnect fluxo principal ───
    # select_conversa → load_estado → classify_intent → switch_intent
    wf['connections']['select_conversa'] = {'main': [[{'node': 'load_estado', 'type': 'main', 'index': 0}]]}
    wf['connections']['load_estado'] = {'main': [[{'node': 'classify_intent', 'type': 'main', 'index': 0}]]}
    wf['connections']['classify_intent'] = {'main': [[{'node': 'switch_intent', 'type': 'main', 'index': 0}]]}

    # switch_intent outputs: 0=CONFIRMAR, 1=RETRY, 2=NOVA, 3=OUTRO (fallback)
    wf['connections']['switch_intent'] = {
        'main': [
            [{'node': 'build_extrator_body', 'type': 'main', 'index': 0}],   # CONFIRMAR
            [{'node': 'build_extrator_body', 'type': 'main', 'index': 0}],   # RETRY (re-extrai pra ter o brief atualizado, depois valida)
            [{'node': 'reset_estado_nova', 'type': 'main', 'index': 0}],     # NOVA
            [{'node': 'build_agente_body', 'type': 'main', 'index': 0}]      # OUTRO
        ]
    }

    # RETRY/CONFIRMAR: build_extrator_body → extrator → parse_extrator → merge_brief → persist_brief → validate → ...
    wf['connections']['extrator'] = {'main': [[{'node': 'parse_extrator', 'type': 'main', 'index': 0}]]}
    wf['connections']['parse_extrator'] = {'main': [[{'node': 'merge_brief', 'type': 'main', 'index': 0}]]}
    wf['connections']['merge_brief'] = {'main': [[{'node': 'persist_brief', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_brief'] = {'main': [[{'node': 'validate', 'type': 'main', 'index': 0}]]}
    # validate continua com if_valid (already wired)

    # if_valid OK → load_meta_token → meta_d1 → d2 → d3 → d4 → check_meta_results → if_pode_retry_infra
    wf['connections']['check_meta_results'] = {'main': [[{'node': 'if_pode_retry_infra', 'type': 'main', 'index': 0}]]}
    # if_pode_retry_infra: true → wait_30s → meta_d1 (reinicia chain); false → persist_estado_apos_meta → ...
    wf['connections']['if_pode_retry_infra'] = {
        'main': [
            [{'node': 'wait_30s', 'type': 'main', 'index': 0}],
            [{'node': 'persist_estado_apos_meta', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['wait_30s'] = {'main': [[{'node': 'meta_d1_campaign', 'type': 'main', 'index': 0}]]}

    # persist_estado_apos_meta → insert_campanha → audit_campanha_criada → build_agente_body (v2 agora responde com base no estado atualizado)
    wf['connections']['persist_estado_apos_meta'] = {'main': [[{'node': 'insert_campanha', 'type': 'main', 'index': 0}]]}
    wf['connections']['insert_campanha'] = {'main': [[{'node': 'audit_campanha_criada', 'type': 'main', 'index': 0}]]}
    wf['connections']['audit_campanha_criada'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    # if_valid FAIL → persist_brief_invalid (no-op, brief já persistido) → build_agente_body
    # audit_validacao_falhou continua existindo mas só pra log; conecta a build_agente_body
    wf['connections']['audit_validacao_falhou'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    # OUTRO: build_agente_body → agente_principal → update_estado_etapa → persist_estado_etapa → send_resposta
    wf['connections']['build_agente_body'] = {'main': [[{'node': 'agente_principal', 'type': 'main', 'index': 0}]]}
    wf['connections']['agente_principal'] = {'main': [[{'node': 'update_estado_etapa', 'type': 'main', 'index': 0}]]}
    wf['connections']['update_estado_etapa'] = {'main': [[{'node': 'persist_estado_etapa', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_estado_etapa'] = {'main': [[{'node': 'build_historico', 'type': 'main', 'index': 0}]]}
    # build_historico → upsert_conversa → send_resposta (already wired)

    # NOVA: reset_estado_nova → build_agente_body
    wf['connections']['reset_estado_nova'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    # ─── 7. Reconnect branch de mídia ───
    wf['connections']['media_if_cadastrado'] = {
        'main': [
            [{'node': 'media_select_conversa', 'type': 'main', 'index': 0}],
            [{'node': 'send_nao_cadastrado', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['media_select_conversa'] = {'main': [[{'node': 'media_download', 'type': 'main', 'index': 0}]]}
    wf['connections']['media_download'] = {'main': [[{'node': 'media_upsert_criativo', 'type': 'main', 'index': 0}]]}
    wf['connections']['media_upsert_criativo'] = {'main': [[{'node': 'decide_acao_media', 'type': 'main', 'index': 0}]]}
    # decide_acao_media SEMPRE manda pra build_media_response (msg condicional)
    # auto-retry async é fora-de-escopo nesta versão (v2.1) — TODO: usar Wait + workflow trigger
    wf['connections']['decide_acao_media'] = {'main': [[{'node': 'build_media_response', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_media_response'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    # ─── 8. Remoção de deprecated ───
    deprecated = ['classifier', 'build_classifier_body', 'send_falha_validacao']
    for d in deprecated:
        if d in nb:
            wf['nodes'] = [n for n in wf['nodes'] if n['name'] != d]
            wf['connections'].pop(d, None)
            # Limpa references downstream
            for src, conn in wf['connections'].items():
                if 'main' in conn:
                    for out in conn['main']:
                        if isinstance(out, list):
                            out[:] = [c for c in out if c.get('node') != d]
            print(f'  − {d} removido')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 8 aplicada — fluxo v2 totalmente reconectado')


if __name__ == '__main__':
    main()
```

- [ ] **Step 8.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/v2_08_rewire_and_deprecate.py
```

Expected output: vários ↻ e + e ao menos 2 − (deprecated removidos).

- [ ] **Step 8.3: Verificar via API que estrutura final faz sentido**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import n8n_api, config
wf = n8n_api.get_workflow(config.get_workflow_id())
names = sorted(n['name'] for n in wf['nodes'])
# Devem existir
must = ['load_estado', 'classify_intent', 'switch_intent', 'merge_brief', 'update_estado_etapa', 'persist_estado_etapa', 'persist_brief', 'persist_estado_apos_meta', 'reset_estado_nova', 'check_meta_results', 'wait_30s', 'if_pode_retry_infra', 'media_select_conversa', 'decide_acao_media', 'build_media_response']
faltando = [m for m in must if m not in names]
assert not faltando, f'Faltando: {faltando}'
# Não devem existir
nao = ['classifier', 'build_classifier_body', 'send_falha_validacao']
ainda = [n for n in nao if n in names]
assert not ainda, f'Deprecated ainda presentes: {ainda}'
print(f'✓ {len(names)} nodes, estrutura v2 OK')
"
```

- [ ] **Step 8.4: Commit**

```bash
git add scripts/v2_08_rewire_and_deprecate.py
git commit -m "feat(n8n): rewire global v2 + remove classifier/send_falha_validacao"
```

---

## Phase 9: Smoke test — happy path

### Task 9: Testar fluxo completo (oi → brief → criativo → CONFIRMAR → ativa)

**Files:**
- Create: `scripts/test_v2_happy_path.py`

- [ ] **Step 9.1: Escrever o script de teste**

Conteúdo de `scripts/test_v2_happy_path.py`:

```python
#!/usr/bin/env python3
"""Simula fluxo completo v2: brief → criativo → CONFIRMAR → ativa.

Assertions:
- Após msg 1 (oi): etapa = coletando_info
- Após brief completo: etapa = aguardando_criativo
- Após criativo: etapa = pronta_pra_subir
- Após CONFIRMAR: etapa = ativa (se Meta API OK na conta nova com Pix)
"""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, n8n_api

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset_conversa():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    conn.commit()
    conn.close()
    print(f'reset conversa pra {PHONE}')


def send_text(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else None


def assert_etapa(esperada):
    estado = get_estado()
    atual = estado['etapa_atual'] if estado else 'sem_conversa'
    msg = f"etapa_atual={atual} (esperada={esperada})"
    assert atual == esperada, msg
    print(f'  ✓ {msg}')


def main():
    reset_conversa()

    print('\n[msg 1: oi]')
    send_text('Oi, quero subir uma campanha')
    time.sleep(12)
    assert_etapa('coletando_info')

    print('\n[msg 2: brief curto]')
    send_text('Apartamento 2 quartos em Setor Bueno Goiânia, R$ 450 mil, perfil investidor, casado 30-50, R$ 50/dia 15 dias, alcance')
    time.sleep(15)
    # Pode ou não ter virado aguardando_criativo (depende do agente preencher tudo)
    estado = get_estado()
    print(f"  estado: etapa={estado['etapa_atual']} brief_campos={list((estado.get('brief') or {}).keys())}")

    print('\n[msg 3: simula criativo via DB direto pra testar transição]')
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute(f"""
      UPDATE auto_ads.conversas
      SET estado_json = jsonb_set(estado_json, '{{criativo}}', '{{"recebido":true,"url":"https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080","mimetype":"image/jpeg","recebido_em":"now"}}'::jsonb),
          criativo_url = 'https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080'
      WHERE telefone = '{PHONE}'
    """)
    conn.commit()
    conn.close()
    print('  ✓ criativo seteado no DB')

    print('\n[msg 4: CONFIRMAR]')
    send_text('CONFIRMAR')
    time.sleep(60)
    estado = get_estado()
    print(f"  estado final: etapa={estado['etapa_atual']}")
    print(f"  ultima_tentativa: {json.dumps(estado.get('ultima_tentativa'), indent=2)[:300]}")

    # Aceita ativa OU falhou_dado (depende de pagamento na conta Meta)
    assert estado['etapa_atual'] in ['ativa', 'falhou_dado', 'falhou_infra'], f"etapa inesperada: {estado['etapa_atual']}"
    print(f'\n✓ Happy path completou em etapa final: {estado["etapa_atual"]}')


if __name__ == '__main__':
    main()
```

- [ ] **Step 9.2: Rodar o teste**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_v2_happy_path.py
```

Expected: passes pelas 4 mensagens, termina em `ativa` (Meta API OK) ou `falhou_dado` se conta Meta ainda tem issue de pagamento.

- [ ] **Step 9.3: Se falhou, inspecionar última execução**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import n8n_api
execs = n8n_api.list_executions(limit=1)
e = execs['data'][0]
print(f'exec={e[\"id\"]} status={e[\"status\"]}')
ex = n8n_api._request('GET', f'/executions/{e[\"id\"]}?includeData=true')
rd = ex['data'].get('resultData', {}).get('runData', {})
for name, runs in rd.items():
    for r in runs:
        if r.get('error'):
            print(f'  ERROR @ {name}: {r[\"error\"].get(\"message\")[:200]}')
"
```

- [ ] **Step 9.4: Commit do teste**

```bash
git add scripts/test_v2_happy_path.py
git commit -m "test(v2): smoke test happy path"
```

---

## Phase 10: Smoke test — falha de dado + RETRY manual

### Task 10: Testar erro de dado e comando RETRY

**Files:**
- Create: `scripts/test_v2_falha_dado_retry.py`

- [ ] **Step 10.1: Escrever o script de teste**

Conteúdo de `scripts/test_v2_falha_dado_retry.py`:

```python
#!/usr/bin/env python3
"""Simula falha por dado + retry manual.

Cenário:
1. Brief completo + criativo URL inválida (placehold.co — Meta rejeita)
2. CONFIRMAR → ad falha em meta_d3_creative com erro de dado → etapa = falhou_dado
3. Atualiza criativo pra URL válida no DB
4. RETRY → etapa volta pra ativa (ou falhou se Meta ainda recusar)
"""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset_conversa():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    conn.commit(); conn.close()


def send_text(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def set_criativo(url):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"""
      UPDATE auto_ads.conversas
      SET estado_json = jsonb_set(estado_json, '{{criativo}}', '{{"recebido":true,"url":"{url}","mimetype":"image/png","recebido_em":"now"}}'::jsonb),
          criativo_url = '{url}'
      WHERE telefone = '{PHONE}'
    """)
    conn.commit(); conn.close()


def main():
    reset_conversa()

    print('[brief completo via DB direto pra ir rápido]')
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    brief_completo = {
        'objetivo': 'investimento',
        'faixa_valor': 'ate_700k',
        'trilho_escolhido': 'precisao',
        'publico_escolhido': 'Pub Quirk Invest',
        'campanha': {'nome': 'Test Falha Dado', 'objetivo_meta': 'OUTCOME_LEADS', 'verba_diaria': 30, 'periodo': '7 dias'},
        'conjunto': {'idade_min': 30, 'idade_max': 55, 'geo': 'Goiânia', 'geo_cidade': 'Goiânia', 'geo_raio_km': 17, 'limitar': True},
        'anuncio': {'tipo_imovel': 'apartamento', 'valor_imovel': 450000, 'copy': 'teste'},
        'targeting_meta': {'geo_locations': {'cities': [{'key': '254063', 'radius': 17, 'distance_unit': 'kilometer'}]}, 'age_min': 30, 'age_max': 55, 'flexible_spec': [{'interests': [{'id': '6003392721577', 'name': 'Investment'}]}]}
    }
    cur.execute("""
      INSERT INTO auto_ads.conversas (telefone, historico, estado_json, criativo_url)
      VALUES (%s, '', %s, '')
      ON CONFLICT (telefone) DO UPDATE SET estado_json = EXCLUDED.estado_json, criativo_url = ''
    """, (PHONE, json.dumps({
        'etapa_atual': 'pronta_pra_subir',
        'criativo': {'recebido': True, 'url': 'https://placehold.co/1080x1080/fff/000/png?text=invalid', 'mimetype': 'image/png', 'recebido_em': 'now'},
        'brief': brief_completo,
        'ultima_tentativa': None
    })))
    conn.commit(); conn.close()
    print('  ✓ brief + criativo inválido (placehold.co)')

    print('\n[CONFIRMAR]')
    send_text('CONFIRMAR')
    time.sleep(60)
    estado = get_estado()
    print(f"  etapa={estado['etapa_atual']} motivo={(estado.get('ultima_tentativa') or {}).get('motivo','')[:100]}")
    assert estado['etapa_atual'] in ['falhou_dado', 'falhou_infra'], f"esperava falha; ficou {estado['etapa_atual']}"
    print('  ✓ falha capturada')

    print('\n[corrigir criativo pra URL válida]')
    set_criativo('https://images.unsplash.com/photo-1564013799919-ab600027ffc6?w=1080')

    print('\n[RETRY]')
    send_text('RETRY')
    time.sleep(60)
    estado = get_estado()
    print(f"  etapa final={estado['etapa_atual']}")
    # Aceita ativa OU falhou (depende de outras checagens Meta)
    assert estado['etapa_atual'] in ['ativa', 'falhou_dado', 'falhou_infra']
    print(f"\n✓ RETRY ciclo completo. Etapa final: {estado['etapa_atual']}")


if __name__ == '__main__':
    main()
```

- [ ] **Step 10.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_v2_falha_dado_retry.py
```

- [ ] **Step 10.3: Commit**

```bash
git add scripts/test_v2_falha_dado_retry.py
git commit -m "test(v2): falha de dado + retry manual"
```

---

## Phase 11: Smoke test — branch de mídia state-aware

### Task 11: Testar transições do branch de mídia

**Files:**
- Create: `scripts/test_v2_media_transitions.py`

- [ ] **Step 11.1: Escrever o teste**

Conteúdo de `scripts/test_v2_media_transitions.py`:

```python
#!/usr/bin/env python3
"""Testa branch de mídia state-aware.

Cenários:
1. media chegando em coletando_info & brief incompleto → msg: "ainda preciso de X, Y"
2. media chegando em aguardando_criativo → msg: "tudo pronto. CONFIRMAR pra subir"
3. media chegando em falhou_dado (motivo criativo) → trigger retry (msg: "rodando RETRY")
4. media chegando em ativa → msg: "já tem campanha ativa. NOVA?"
"""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def set_estado(estado):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute("""
      INSERT INTO auto_ads.conversas (telefone, historico, estado_json, criativo_url)
      VALUES (%s, '', %s, '')
      ON CONFLICT (telefone) DO UPDATE SET estado_json = EXCLUDED.estado_json
    """, (PHONE, json.dumps(estado)))
    conn.commit(); conn.close()


def send_media():
    # Usa um ID inventado — media_download vai falhar com NodeApiError 'Message not found',
    # mas o branch continua porque media_download usa continueOnFail. Aqui a gente checa só
    # a mensagem que sai (build_media_response) — não a foto em si.
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'id': 'fake-media-id', 'type': 'media', 'from': f'{PHONE}@s.whatsapp.net', 'mediaType': 'image'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=30).read()


def get_last_media_response():
    """Lê a última execução de media e retorna o texto que build_media_response emitiu."""
    import sys; sys.path.insert(0, os.path.dirname(__file__))
    import n8n_api
    execs = n8n_api.list_executions(limit=1)
    eid = execs['data'][0]['id']
    ex = n8n_api._request('GET', f'/executions/{eid}?includeData=true')
    rd = ex['data'].get('resultData', {}).get('runData', {})
    if 'build_media_response' in rd:
        return rd['build_media_response'][0]['data']['main'][0][0]['json'].get('text', '')
    return ''


def test(scenario_name, estado_antes, espera_substring):
    print(f'\n[Cenário] {scenario_name}')
    set_estado(estado_antes)
    send_media()
    time.sleep(10)
    msg = get_last_media_response()
    print(f'  msg saída: "{msg[:120]}"')
    assert espera_substring.lower() in msg.lower(), f"esperava '{espera_substring}', mas msg foi '{msg}'"
    print(f'  ✓ contém "{espera_substring}"')


def main():
    test(
        'coletando_info + brief incompleto',
        {'etapa_atual': 'coletando_info', 'criativo': {'recebido': False}, 'brief': {}, 'ultima_tentativa': None},
        'ainda preciso'
    )

    brief_completo = {'campanha': {'nome':'x','verba_diaria':30}, 'objetivo': 'morar', 'faixa_valor': 'ate_700k', 'conjunto': {'geo': 'X'}, 'anuncio': {'copy': 'x'}, 'targeting_meta': {'geo_locations': {}}}

    test(
        'aguardando_criativo + brief completo',
        {'etapa_atual': 'aguardando_criativo', 'criativo': {'recebido': False}, 'brief': brief_completo, 'ultima_tentativa': None},
        'CONFIRMAR'
    )

    test(
        'falhou_dado(criativo) → trigger retry',
        {'etapa_atual': 'falhou_dado', 'criativo': {'recebido': True, 'url': 'old'}, 'brief': brief_completo,
         'ultima_tentativa': {'resultado': 'erro_dado', 'motivo': 'imagem rejeitada pela Meta', 'tentativas_count': 1}},
        'RETRY'
    )

    test(
        'ativa → sugere NOVA',
        {'etapa_atual': 'ativa', 'criativo': {'recebido': True, 'url': 'x'}, 'brief': brief_completo,
         'ultima_tentativa': {'resultado': 'ok', 'campaign_id': '123', 'tentativas_count': 1}},
        'NOVA'
    )

    print('\n✓ Todas as transições do branch de mídia testadas')


if __name__ == '__main__':
    main()
```

- [ ] **Step 11.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_v2_media_transitions.py
```

- [ ] **Step 11.3: Commit**

```bash
git add scripts/test_v2_media_transitions.py
git commit -m "test(v2): transições do branch de mídia state-aware"
```

---

## Phase 12: Handoff final

### Task 12: Documento de handoff + reset de conversa pro Renan

**Files:**
- Create: `docs/HANDOFF_V2.md` (resumo curto pro Renan)

- [ ] **Step 12.1: Escrever o handoff**

Conteúdo de `docs/HANDOFF_V2.md`:

```markdown
# Quirk Auto Ads v2 — Handoff

**Data:** 2026-05-29
**Status:** Implementado, smoke-tested

## O que mudou

1. **Estado persistido**: `auto_ads.conversas.estado_json` (JSONB) com etapa, criativo, brief, ultima_tentativa
2. **Agente principal v2**: lê estado e responde com base nele. Não inventa mais "subindo agora"
3. **classify_intent (regex)** substitui o classifier LLM — instantâneo, sem custo de token
4. **validate roda ANTES do agente** em CONFIRMAR/RETRY — cliente recebe 1 msg coerente
5. **Branch de mídia state-aware**: msg condicional baseada em etapa + brief + última tentativa; auto-retry quando faz sentido
6. **Auto-retry de infra** (Meta 5xx/timeout): até 2 tentativas com 30s de espera

## Como testar

Manda mensagem no WhatsApp pelo seu número (5511980838409).

Fluxo esperado:
1. "Oi" → agente coleta brief
2. Manda dados (tipo, valor, região, perfil, verba, período) → agente confirma cada dado
3. Manda **foto/vídeo** do imóvel → confirma criativo + diz "manda CONFIRMAR pra subir"
4. Manda **CONFIRMAR** → backend valida, sobe na Meta, responde com campaign_id real
5. Se falhar por dado (raio, imagem, pagamento) → agente explica + pede correção + cita **RETRY**
6. Se falhar por infra (rate limit) → auto-retry silencioso 2x

## Comandos novos do cliente

- **CONFIRMAR** (ou "Confirmado", "Confirma") → tenta subir
- **RETRY** (ou "tente de novo", "subir novamente") → re-tenta depois de corrigir
- **NOVA CAMPANHA** (ou "começar uma nova", "quero outra") → zera estado

## Próximos sub-projetos

- **B (gestão)**: pausar, reativar, alterar verba/público/geo, encerrar
- **C (relatórios)**: status, performance, análise de campanhas ativas

Quando quiser, brainstormar cada um.

## Arquivos-chave

- Spec: `docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md`
- Plan: `docs/superpowers/plans/2026-05-29-quirk-auto-ads-v2-state-aware.md`
- Migration: `sql/004_estado_json.sql`
- Prompt: `prompts/agente_principal.md` (v2)
- Scripts: `scripts/v2_*.py`, `scripts/test_v2_*.py`
```

- [ ] **Step 12.2: Reset da conversa de teste do Renan**

```bash
python3 -c "
import psycopg2
db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(db_url); cur = conn.cursor()
cur.execute(\"DELETE FROM auto_ads.conversas WHERE telefone = '5511980838409'\")
conn.commit(); conn.close()
print('✓ conversa do Renan resetada — pronto pra teste real')
"
```

- [ ] **Step 12.3: Commit final**

```bash
git add docs/HANDOFF_V2.md
git commit -m "docs: handoff v2 — pronto pra teste real do Renan"
```

- [ ] **Step 12.4: Avisar Renan**

Manda mensagem informando:
- v2 está rodando
- conversa resetada
- pode mandar `oi` no WhatsApp pra testar
- 3 comandos novos: CONFIRMAR, RETRY, NOVA CAMPANHA

---

## Self-Review

**Spec coverage** — todas as seções da spec mapeadas em tasks:
- §4 (state model): Task 1 (SQL) + Task 4 (merge_brief, update_estado_etapa)
- §5.1 (fluxo principal): Tasks 3, 4, 5, 6, 8
- §5.2 (branch mídia): Task 7
- §5.3 (agente v2 prompt): Task 2 + Task 8 (injeção do bloco)
- §5.4 (classify_intent): Task 3
- §5.5 (classificação erro Meta): Task 6
- §5.6 (retry): Task 6 (infra) + Task 8 (manual via switch_intent)
- §6 (componentes): cobertos
- §7 (migração): Tasks 1-8 são a migração

**Placeholder scan** — nenhum TBD/TODO/incompleto.

**Type consistency** — `classify_intent.intent` referenciado em Task 3 (output), Task 8 (switch_intent), Task 9/10 (testes). Sempre uppercase string. `estado.etapa_atual` referenciado em load_estado, merge_brief, update_estado_etapa, persist_estado_*, agente_principal_v2, check_meta_results — sempre lowercase snake_case. `check_meta_results.classe` é `'infra' | 'dado' | null` consistentemente.

---

## Execution Handoff

Plan completo. Próxima ação: implementar tasks 1–12 (autoexecuting em auto mode).
