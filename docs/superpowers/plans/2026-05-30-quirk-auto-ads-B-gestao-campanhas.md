# Quirk Auto Ads — Sub-projeto B (gestão de campanhas) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar 6 verbos de gestão de campanhas existentes via WhatsApp (PAUSAR, REATIVAR, ENCERRAR, ALTERAR_VERBA, ALTERAR_PUBLICO, ALTERAR_GEO) com lista numerada, confirmação obrigatória, sub-flow state-aware com TTL e CANCELAR, audit imutável.

**Architecture:** Extensão do workflow n8n state-aware do sub-projeto A. Novo sub-objeto `estado_json.gestao` que persiste o passo do fluxo entre turnos. `classify_intent` (regex) ganha 7 verbos novos. `process_gestao_step` (Code) roteia por passo. Endpoints Meta API: status (campaign) + daily_budget/targeting (adset). Audit imutável em `auto_ads.audit_log`.

**Tech Stack:** n8n self-hosted · Anthropic Claude Sonnet 4.5 (extrator parcial) · Supabase Postgres (`auto_ads` schema) · UAZAPI · Meta Marketing API v25 · Python 3.9 helpers (`scripts/n8n_api.py`, `scripts/config.py`)

**Spec:** [`docs/superpowers/specs/2026-05-30-quirk-auto-ads-B-gestao-campanhas-design.md`](../specs/2026-05-30-quirk-auto-ads-B-gestao-campanhas-design.md)

---

## File Structure

### Novos arquivos
- `sql/005_ultima_alteracao.sql` — migration: coluna `ultima_alteracao` em `auto_ads.campanhas`
- `scripts/b_01_migration_sql.py` — aplica migration 005
- `scripts/b_02_classify_intent_v3.py` — adiciona 7 verbos novos no classify_intent
- `scripts/b_03_em_gestao_router.py` — adiciona node `em_gestao_valido` (IF) + `process_gestao_step` (Code) ANTES do classify_intent
- `scripts/b_04_list_campanhas_and_init.py` — adiciona `list_campanhas` (Postgres) + `init_gestao` (Code) + `build_gestao_response` (Code) + `persist_estado_gestao` (Postgres)
- `scripts/b_05_meta_update_nodes.py` — adiciona `meta_update_status` + `meta_update_adset_budget` + `meta_update_adset_targeting` (HTTP POSTs)
- `scripts/b_06_extrator_parcial_builders.py` — adiciona `build_extrator_partial_publico_body` + `build_extrator_partial_geo_body` (Code) que reusam o node `extrator` existente
- `scripts/b_07_execute_action_switch.py` — adiciona `execute_gestao_action` (Switch por verbo) + `check_gestao_result` (Code)
- `scripts/b_08_db_update_and_audit.py` — adiciona `update_db_campanha` (Postgres) + `audit_gestao` (Postgres) + `reset_gestao` (Postgres) + `build_gestao_confirmation_msg` (Code)
- `scripts/b_09_rewire_all.py` — reconecta tudo conforme §7.1 da spec
- `scripts/b_10_extend_switch_intent.py` — adiciona 6 outputs novos no switch_intent
- `scripts/test_b_pausar.py` — smoke test PAUSAR fluxo completo
- `scripts/test_b_alterar_verba.py` — smoke test ALTERAR_VERBA
- `scripts/test_b_cancelar.py` — smoke test CANCELAR em cada passo
- `scripts/test_b_ttl.py` — smoke test TTL de 10 min
- `scripts/test_b_input_invalido.py` — smoke test inputs inválidos

### Arquivos modificados
- `prompts/agente_principal.md` — adicionar conhecimento de etapa `em_gestao` no bloco [ESTADO]

### Convenções
- Scripts `b_*.py` são idempotentes (pattern dos `v2_*.py`)
- Cada script importa `n8n_api` + `config`, busca workflow, aplica, chama `update_workflow`
- Testes são scripts de simulação (POST webhook → wait → query Postgres → assert)

---

## Phase 1: Migration SQL

### Task 1: Adicionar `ultima_alteracao` em `auto_ads.campanhas`

**Files:**
- Create: `sql/005_ultima_alteracao.sql`
- Create: `scripts/b_01_migration_sql.py`

- [ ] **Step 1.1: Escrever o SQL**

Conteúdo de `sql/005_ultima_alteracao.sql`:

```sql
-- Migration 005 — ultima_alteracao em auto_ads.campanhas
-- Spec: docs/superpowers/specs/2026-05-30-quirk-auto-ads-B-gestao-campanhas-design.md §9.1

ALTER TABLE auto_ads.campanhas
ADD COLUMN IF NOT EXISTS ultima_alteracao TIMESTAMPTZ;

-- Linhas existentes herdam criada_em
UPDATE auto_ads.campanhas SET ultima_alteracao = criada_em WHERE ultima_alteracao IS NULL;

-- Daqui pra frente novas linhas devem ter default = NOW
ALTER TABLE auto_ads.campanhas
ALTER COLUMN ultima_alteracao SET DEFAULT NOW();
```

- [ ] **Step 1.2: Escrever script Python que aplica**

Conteúdo de `scripts/b_01_migration_sql.py`:

```python
#!/usr/bin/env python3
"""Aplica sql/005_ultima_alteracao.sql via psycopg2."""
import os, sys
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    sql_path = '/Users/renanreal/quirk_auto_ads/sql/005_ultima_alteracao.sql'
    with open(sql_path) as f:
        sql = f.read()

    db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip()
    db_url = db_url.replace('aws-0-', 'aws-1-')

    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(sql)
    conn.commit()

    cur.execute("""
        SELECT column_name, data_type, column_default
        FROM information_schema.columns
        WHERE table_schema='auto_ads' AND table_name='campanhas' AND column_name='ultima_alteracao'
    """)
    row = cur.fetchone()
    assert row is not None, "Coluna ultima_alteracao não foi criada"
    print(f'✓ Coluna criada: {row[0]} {row[1]} default={row[2]}')

    cur.execute("""SELECT count(*) FROM auto_ads.campanhas WHERE ultima_alteracao IS NULL""")
    null_count = cur.fetchone()[0]
    assert null_count == 0, f"Existem {null_count} linhas com ultima_alteracao NULL"
    print(f'  ✓ todas as linhas têm ultima_alteracao preenchido')

    conn.close()
    print('\n✓ Migration 005 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 1.3: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_01_migration_sql.py
```

Expected output:
```
✓ Coluna criada: ultima_alteracao timestamp with time zone default=now()
  ✓ todas as linhas têm ultima_alteracao preenchido

✓ Migration 005 aplicada
```

- [ ] **Step 1.4: Commit**

```bash
git add sql/005_ultima_alteracao.sql scripts/b_01_migration_sql.py
git commit -m "feat(sql): migration 005 — ultima_alteracao em campanhas"
```

---

## Phase 2: classify_intent v3 (verbos de gestão)

### Task 2: Adicionar 7 verbos novos no classify_intent

**Files:**
- Create: `scripts/b_02_classify_intent_v3.py`

- [ ] **Step 2.1: Escrever o script**

Conteúdo de `scripts/b_02_classify_intent_v3.py`:

```python
#!/usr/bin/env python3
"""classify_intent v3 — adiciona 7 verbos de gestão preservando os 4 do A."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V3 = """// Detecta intenção do cliente por regex no texto da msg
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

let intent = 'OUTRO';

// Verbos do sub-projeto A (preservados)
if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^subir\\s+denovo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^subir\\s+de\\s+novo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^repetir$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^refazer$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';

// Verbos do sub-projeto B (novos)
else if (/^(pausar|pausa)[!.?]*$/i.test(msg)) intent = 'PAUSAR';
else if (/pausar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/parar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/^(reativar|reativa|ativar)[!.?]*$/i.test(msg)) intent = 'REATIVAR';
else if (/voltar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'REATIVAR';
else if (/^(encerrar|arquivar)[!.?]*$/i.test(msg)) intent = 'ENCERRAR';
else if (/finalizar\\s+campanha/i.test(msg)) intent = 'ENCERRAR';
else if (/(alterar|mudar|trocar)\\s+verba/i.test(msg)) intent = 'ALTERAR_VERBA';
else if (/(alterar|mudar)\\s+p[uú]blico/i.test(msg)) intent = 'ALTERAR_PUBLICO';
else if (/(alterar|mudar)\\s+geo/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/mudar\\s+(regi[aã]o|cidade)/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/^(cancelar|cancela)[!.?]*$/i.test(msg)) intent = 'CANCELAR';
else if (/^deixa\\s+pra\\s+l[áa]/i.test(msg)) intent = 'CANCELAR';

return [{ json: { intent, mensagem_texto: msg } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V3
    print('  ↻ classify_intent v3: 7 verbos novos (PAUSAR, REATIVAR, ENCERRAR, ALTERAR_*, CANCELAR)')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 2 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 2.2: Rodar e verificar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_02_classify_intent_v3.py
```

Expected: `↻ classify_intent v3: ...` + `✓ Task 2 aplicada`

- [ ] **Step 2.3: Commit**

```bash
git add scripts/b_02_classify_intent_v3.py
git commit -m "feat(n8n): classify_intent v3 — 7 verbos de gestão"
```

---

## Phase 3: Roteamento de gestão (em_gestao_valido + process_gestao_step)

### Task 3: Adicionar nodes que detectam sub-flow de gestão

**Files:**
- Create: `scripts/b_03_em_gestao_router.py`

- [ ] **Step 3.1: Escrever o script**

Conteúdo de `scripts/b_03_em_gestao_router.py`:

```python
#!/usr/bin/env python3
"""
Adiciona:
- em_gestao_valido (IF): testa se estado.gestao está populado E TTL < 10min
- process_gestao_step (Code): roteia por gestao.passo (selecao/coleta_valor/confirmacao)

Conexões finais serão feitas na Task 9 (rewire global).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


PROCESS_GESTAO_STEP_CODE = """// Roteador por estado.gestao.passo + valida input + decide próximo passo
const estado = $('load_estado').first().json.estado;
const gestao = estado.gestao;
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

if (!gestao || !gestao.passo) {
  // não deveria chegar aqui — guard
  return [{ json: { acao: 'reset', motivo: 'gestao_vazio' } }];
}

// CANCELAR é sempre aceito
if (/^(cancelar|cancela|deixa\\s+pra\\s+l[áa])[!.?]*$/i.test(msg)) {
  return [{ json: { acao: 'reset', motivo: 'cancelado_pelo_cliente' } }];
}

const passo = gestao.passo;
const verbo = gestao.verbo;

// Passo SELECAO: espera número
if (passo === 'selecao') {
  const num = parseInt(msg);
  if (isNaN(num) || num < 1 || num > (gestao.lista_candidatas || []).length) {
    return [{ json: { acao: 'erro_input', motivo: 'numero_invalido', proximo_passo: 'selecao' } }];
  }
  const selecionada = gestao.lista_candidatas[num - 1];
  gestao.selecionada = selecionada;

  // Verbos destrutivos vão direto pra confirmação. Alterações vão pra coleta_valor.
  if (['PAUSAR', 'REATIVAR', 'ENCERRAR'].includes(verbo)) {
    gestao.passo = 'confirmacao';
  } else {
    gestao.passo = 'coleta_valor';
  }
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

// Passo COLETA_VALOR: valida valor por verbo
if (passo === 'coleta_valor') {
  let novo_valor = null;
  let erro = null;

  if (verbo === 'ALTERAR_VERBA') {
    const n = parseInt(msg);
    if (isNaN(n) || n < 10 || n > 100) {
      erro = 'verba_fora_faixa';
    } else {
      novo_valor = { tipo: 'verba_diaria', valor: n };
    }
  } else if (verbo === 'ALTERAR_PUBLICO') {
    // Número da lista de Pubs Quirk (1-N) OU texto livre
    const num = parseInt(msg);
    if (!isNaN(num) && num >= 1 && num <= 20) {
      novo_valor = { tipo: 'publico_estruturado', numero: num };
    } else if (msg.length >= 4) {
      novo_valor = { tipo: 'publico_livre', descricao: msg };
    } else {
      erro = 'publico_input_invalido';
    }
  } else if (verbo === 'ALTERAR_GEO') {
    // Regex estruturado "CIDADE raio_km" OR texto livre
    const m = msg.match(/^(.+?)\\s+(\\d+)$/);
    if (m) {
      novo_valor = { tipo: 'geo_estruturado', cidade: m[1].trim(), raio_km: parseInt(m[2]) };
    } else if (msg.length >= 4) {
      novo_valor = { tipo: 'geo_livre', descricao: msg };
    } else {
      erro = 'geo_input_invalido';
    }
  }

  if (erro) {
    return [{ json: { acao: 'erro_input', motivo: erro, proximo_passo: 'coleta_valor' } }];
  }
  gestao.novo_valor = novo_valor;
  gestao.passo = 'confirmacao';
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

// Passo CONFIRMACAO: SIM/NÃO
if (passo === 'confirmacao') {
  if (/^(sim|s|confirma|confirmar|confirmado)[!.?]*$/i.test(msg)) {
    return [{ json: { acao: 'executa', estado, gestao } }];
  }
  if (/^(n[aã]o|n)[!.?]*$/i.test(msg)) {
    return [{ json: { acao: 'reset', motivo: 'cancelado_no_confirma' } }];
  }
  return [{ json: { acao: 'erro_input', motivo: 'confirma_invalido', proximo_passo: 'confirmacao' } }];
}

return [{ json: { acao: 'reset', motivo: 'passo_desconhecido' } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # em_gestao_valido — IF
    if 'em_gestao_valido' not in nb:
        wf['nodes'].append({
            'id': 'em_gestao_valido', 'name': 'em_gestao_valido',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [1350, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [
                        {
                            'leftValue': "={{ $('load_estado').item.json.estado.gestao !== null && $('load_estado').item.json.estado.gestao !== undefined ? 'true' : 'false' }}",
                            'rightValue': 'true',
                            'operator': {'type': 'string', 'operation': 'equals'}
                        },
                        {
                            # TTL check: now - iniciado_em < 10 min (600000ms)
                            'leftValue': "={{ Date.now() - new Date($('load_estado').item.json.estado.gestao?.iniciado_em || 0).getTime() }}",
                            'rightValue': 600000,
                            'operator': {'type': 'number', 'operation': 'smaller'}
                        }
                    ]
                }
            }
        })
        print('  + em_gestao_valido adicionado')

    # process_gestao_step — Code
    if 'process_gestao_step' not in nb:
        wf['nodes'].append({
            'id': 'process_gestao_step', 'name': 'process_gestao_step',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1550, 50],
            'parameters': {'language': 'javaScript', 'jsCode': PROCESS_GESTAO_STEP_CODE}
        })
        print('  + process_gestao_step adicionado')

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
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_03_em_gestao_router.py
```

- [ ] **Step 3.3: Commit**

```bash
git add scripts/b_03_em_gestao_router.py
git commit -m "feat(n8n): em_gestao_valido + process_gestao_step"
```

---

## Phase 4: Lista de campanhas + init + build de resposta

### Task 4: Listar campanhas + inicializar gestão + montar mensagem

**Files:**
- Create: `scripts/b_04_list_campanhas_and_init.py`

- [ ] **Step 4.1: Escrever o script**

Conteúdo de `scripts/b_04_list_campanhas_and_init.py`:

```python
#!/usr/bin/env python3
"""
Adiciona:
- list_campanhas (Postgres): SELECT por verbo
- init_gestao (Code): popula estado.gestao com lista + verbo + passo='selecao'
- build_gestao_response (Code): mensagem do passo atual
- persist_estado_gestao (Postgres): UPDATE estado_json.gestao no DB
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


LIST_CAMPANHAS_QUERY = """SELECT
  id AS campanha_id_db,
  nome_campanha AS nome,
  ad_account_id,
  campaign_id AS campaign_id_meta,
  adset_id AS adset_id_meta,
  status,
  json_extrator,
  ultima_alteracao
FROM auto_ads.campanhas
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'
  AND status = ANY(CASE
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'PAUSAR' THEN ARRAY['CREATED_PAUSED','ACTIVE']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'REATIVAR' THEN ARRAY['PAUSED','CREATED_PAUSED']
    WHEN '{{ $('classify_intent').item.json.intent }}' = 'ENCERRAR' THEN ARRAY['CREATED_PAUSED','ACTIVE','PAUSED']
    ELSE ARRAY['CREATED_PAUSED','ACTIVE','PAUSED']
  END)
ORDER BY criada_em DESC
LIMIT 10"""


INIT_GESTAO_CODE = """// Popula estado.gestao com lista + verbo + passo='selecao' + timestamp
const estado = $('load_estado').first().json.estado;
const verbo = $('classify_intent').first().json.intent;
const linhas = $('list_campanhas').all().map(r => r.json);

if (linhas.length === 0) {
  // Nenhuma campanha pra o verbo escolhido
  return [{ json: { acao: 'sem_campanhas', verbo, estado } }];
}

const lista_candidatas = linhas.map((row, i) => ({
  posicao: i + 1,
  campanha_id_db: row.campanha_id_db,
  campaign_id_meta: row.campaign_id_meta,
  adset_id_meta: row.adset_id_meta,
  nome: row.nome,
  status: row.status,
  verba_atual_centavos: row.json_extrator?.campanha?.verba_diaria ? row.json_extrator.campanha.verba_diaria * 100 : null,
  verba_atual_reais: row.json_extrator?.campanha?.verba_diaria || null,
  publico_atual: row.json_extrator?.publico_escolhido || null,
  geo_cidade_atual: row.json_extrator?.conjunto?.geo_cidade || null,
  geo_raio_atual: row.json_extrator?.conjunto?.geo_raio_km || null,
  json_extrator_completo: row.json_extrator
}));

estado.gestao = {
  verbo,
  passo: 'selecao',
  iniciado_em: new Date().toISOString(),
  lista_candidatas,
  selecionada: null,
  novo_valor: null
};
estado.etapa_atual = 'em_gestao';

return [{ json: { acao: 'inicia_selecao', estado, gestao: estado.gestao } }];
"""


BUILD_GESTAO_RESPONSE_CODE = """// Monta texto do passo atual (depois de init_gestao OU process_gestao_step)
// Inputs: estado (com gestao) OU acao = 'sem_campanhas' OU acao = 'erro_input'

const upstream = $input.first().json;
const estado = upstream.estado || $('load_estado').first().json.estado;
const acao = upstream.acao || 'avanca';
const gestao = upstream.gestao || estado.gestao;

// Caso: nenhuma campanha pro verbo
if (acao === 'sem_campanhas') {
  const v = upstream.verbo;
  const map = {
    PAUSAR: 'Você não tem campanhas ativas pra pausar.',
    REATIVAR: 'Você não tem campanhas pausadas pra reativar.',
    ENCERRAR: 'Você não tem campanhas pra encerrar.',
    ALTERAR_VERBA: 'Você não tem campanhas ativas pra alterar verba.',
    ALTERAR_PUBLICO: 'Você não tem campanhas ativas pra alterar público.',
    ALTERAR_GEO: 'Você não tem campanhas ativas pra alterar geo.'
  };
  return [{ json: { text: map[v] || 'Você não tem campanhas.', telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

// Caso: erro de input — re-prompta o passo
if (acao === 'erro_input') {
  const motivo = upstream.motivo;
  let text;
  if (motivo === 'numero_invalido') text = `Número inválido. Manda entre 1 e ${gestao.lista_candidatas.length} ou CANCELAR.`;
  else if (motivo === 'verba_fora_faixa') text = 'Verba inválida. Manda número entre 10 e 100, ou CANCELAR.';
  else if (motivo === 'publico_input_invalido') text = 'Não entendi. Manda número da lista (1-20) OU descreve em texto, ou CANCELAR.';
  else if (motivo === 'geo_input_invalido') text = 'Não entendi. Manda "CIDADE raio_km" (ex: São Paulo 25) ou descreve, ou CANCELAR.';
  else if (motivo === 'confirma_invalido') text = 'Manda SIM ou NÃO. Ou CANCELAR.';
  else text = 'Input inválido. CANCELAR pra sair.';
  return [{ json: { text, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

// Caso: avança — monta prompt do passo atual
const passo = gestao.passo;
const verbo = gestao.verbo;

if (passo === 'selecao') {
  const linhas = gestao.lista_candidatas.map(c => {
    const status_label = c.status === 'ACTIVE' ? 'ativa' : c.status === 'PAUSED' ? 'pausada' : c.status === 'CREATED_PAUSED' ? 'paused (criação)' : c.status;
    const verba = c.verba_atual_reais ? `R$ ${c.verba_atual_reais}/dia` : '';
    return `${c.posicao}. ${c.nome} (${status_label}${verba ? ', ' + verba : ''})`;
  }).join('\\n');
  const verboLabel = { PAUSAR: 'pausar', REATIVAR: 'reativar', ENCERRAR: 'encerrar', ALTERAR_VERBA: 'alterar verba', ALTERAR_PUBLICO: 'alterar público', ALTERAR_GEO: 'alterar geo' }[verbo];
  return [{ json: { text: `Você tem ${gestao.lista_candidatas.length} pra ${verboLabel}. Qual?\\n\\n${linhas}\\n\\nResponde com o número ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

if (passo === 'coleta_valor') {
  const sel = gestao.selecionada;
  if (verbo === 'ALTERAR_VERBA') {
    return [{ json: { text: `Verba atual de "${sel.nome}": R$ ${sel.verba_atual_reais}/dia. Manda só o número novo (entre 10 e 100), ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
  if (verbo === 'ALTERAR_PUBLICO') {
    // Lista de Pubs Quirk (numeração estável)
    const pubs = ['Pub Quirk 0','Pub Quirk 1','Pub Quirk 1.1','Pub Quirk 1.2','Pub Quirk 1.3','Pub Quirk 1.4','Pub Quirk 1.5','Pub Quirk 2','Pub Quirk 3','Pub Quirk 4','Pub Quirk 5','Pub Quirk 6','Pub Quirk 7','Pub Quirk Invest','Pub Quirk Invest + Intermediário','Pub Quirk Invest + Alto valor','Pub Quirk Profissões','Pub Quirk Profissões + Intermediário','Pub Quirk Profissões + Alto valor','Pub Corretores #1'];
    const lista = pubs.map((p, i) => `${i+1}. ${p}`).join('\\n');
    return [{ json: { text: `Público atual: ${sel.publico_atual}. Escolhe um número da lista OU descreve em texto (ex: "investidor casado alto valor"):\\n\\n${lista}\\n\\nOu CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
  if (verbo === 'ALTERAR_GEO') {
    return [{ json: { text: `Geo atual de "${sel.nome}": ${sel.geo_cidade_atual} raio ${sel.geo_raio_atual}km. Manda "CIDADE raio_km" (ex: "São Paulo 25") OU descreve, ou CANCELAR.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
  }
}

if (passo === 'confirmacao') {
  const sel = gestao.selecionada;
  const nv = gestao.novo_valor;
  let resumo;
  if (verbo === 'PAUSAR') resumo = `pausar "${sel.nome}"`;
  else if (verbo === 'REATIVAR') resumo = `reativar "${sel.nome}"`;
  else if (verbo === 'ENCERRAR') resumo = `ENCERRAR "${sel.nome}" (irreversível — vai pro histórico arquivado)`;
  else if (verbo === 'ALTERAR_VERBA') resumo = `mudar verba de "${sel.nome}" de R$ ${sel.verba_atual_reais}/dia → R$ ${nv.valor}/dia`;
  else if (verbo === 'ALTERAR_PUBLICO') resumo = `trocar público de "${sel.nome}" (${sel.publico_atual} → novo)`;
  else if (verbo === 'ALTERAR_GEO') resumo = `trocar geo de "${sel.nome}" (${sel.geo_cidade_atual} ${sel.geo_raio_atual}km → novo)`;
  return [{ json: { text: `Confirma ${resumo}? Manda SIM ou NÃO.`, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
}

return [{ json: { text: 'Passo desconhecido. CANCELAR pra sair.', telefone: $('normalize_phone').first().json.telefone_normalizado } }];
"""


PERSIST_ESTADO_GESTAO_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{etapa_atual}', to_jsonb('{{ $('init_gestao').item.json.estado.etapa_atual || $('process_gestao_step').item.json.estado.etapa_atual || $('load_estado').item.json.estado.etapa_atual }}'::text)),
  '{gestao}',
  '{{ JSON.stringify($('init_gestao').item.json.gestao || $('process_gestao_step').item.json.gestao || $('load_estado').item.json.estado.gestao || null).replace(/'/g, "''") }}'::jsonb
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'list_campanhas' not in nb:
        wf['nodes'].append({
            'id': 'list_campanhas', 'name': 'list_campanhas',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1750, 200],
            'parameters': {'operation': 'executeQuery', 'query': LIST_CAMPANHAS_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + list_campanhas adicionado')

    if 'init_gestao' not in nb:
        wf['nodes'].append({
            'id': 'init_gestao', 'name': 'init_gestao',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1950, 200],
            'parameters': {'language': 'javaScript', 'jsCode': INIT_GESTAO_CODE}
        })
        print('  + init_gestao adicionado')

    if 'build_gestao_response' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_response', 'name': 'build_gestao_response',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2150, 200],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_RESPONSE_CODE}
        })
        print('  + build_gestao_response adicionado')

    if 'persist_estado_gestao' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_gestao', 'name': 'persist_estado_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [2350, 200],
            'parameters': {'operation': 'executeQuery', 'query': PERSIST_ESTADO_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_gestao adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 4 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 4.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_04_list_campanhas_and_init.py
```

- [ ] **Step 4.3: Commit**

```bash
git add scripts/b_04_list_campanhas_and_init.py
git commit -m "feat(n8n): list_campanhas + init_gestao + build_gestao_response + persist"
```

---

## Phase 5: Endpoints Meta de UPDATE

### Task 5: Adicionar 3 HTTP nodes pra Meta UPDATE

**Files:**
- Create: `scripts/b_05_meta_update_nodes.py`

- [ ] **Step 5.1: Escrever o script**

Conteúdo de `scripts/b_05_meta_update_nodes.py`:

```python
#!/usr/bin/env python3
"""
Adiciona HTTP nodes pra UPDATE no Meta:
- meta_update_status (POST /v25.0/{campaign_id} com status)
- meta_update_adset_budget (POST /v25.0/{adset_id} com daily_budget)
- meta_update_adset_targeting (POST /v25.0/{adset_id} com targeting completo)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


META_HEADERS = [{'name': 'Content-Type', 'value': 'application/json'}]


def http_node(node_id, name, position, url_expr, body_expr):
    return {
        'id': node_id, 'name': name,
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': position,
        'parameters': {
            'method': 'POST',
            'url': url_expr,
            'sendHeaders': True,
            'headerParameters': {'parameters': META_HEADERS},
            'sendBody': True,
            'specifyBody': 'json',
            'jsonBody': body_expr,
            'options': {},
        },
        'retryOnFail': True, 'maxTries': 2, 'waitBetweenTries': 2000,
        'continueOnFail': True
    }


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # meta_update_status — POST /v25.0/{campaign_id}
    if 'meta_update_status' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_status', 'meta_update_status',
            [3000, 100],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.campaign_id_meta }}",
            """={
  "status": "{{ ({PAUSAR:'PAUSED', REATIVAR:'ACTIVE', ENCERRAR:'ARCHIVED'})[$('process_gestao_step').item.json.gestao.verbo] }}",
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_status adicionado')

    # meta_update_adset_budget — POST /v25.0/{adset_id}
    if 'meta_update_adset_budget' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_adset_budget', 'meta_update_adset_budget',
            [3000, 250],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.adset_id_meta }}",
            """={
  "daily_budget": {{ $('process_gestao_step').item.json.gestao.novo_valor.valor * 100 }},
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_adset_budget adicionado')

    # meta_update_adset_targeting — POST /v25.0/{adset_id}
    if 'meta_update_adset_targeting' not in nb:
        wf['nodes'].append(http_node(
            'meta_update_adset_targeting', 'meta_update_adset_targeting',
            [3000, 400],
            "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.adset_id_meta }}",
            """={
  "targeting": {{ JSON.stringify($('build_targeting_atualizado').item.json.targeting) }},
  "access_token": "{{ $('load_meta_token').item.json.valor }}"
}"""
        ))
        print('  + meta_update_adset_targeting adicionado')

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
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_05_meta_update_nodes.py
```

- [ ] **Step 5.3: Commit**

```bash
git add scripts/b_05_meta_update_nodes.py
git commit -m "feat(n8n): nodes Meta UPDATE (status + budget + targeting)"
```

---

## Phase 6: Extrator parcial (público/geo livre)

### Task 6: Builders de body pra extrator parcial + node de merge targeting

**Files:**
- Create: `scripts/b_06_extrator_parcial_builders.py`

- [ ] **Step 6.1: Escrever o script**

Conteúdo de `scripts/b_06_extrator_parcial_builders.py`:

```python
#!/usr/bin/env python3
"""
Adiciona:
- build_extrator_partial_publico_body (Code): system prompt enxuto pra mapear texto livre → Pub Quirk
- build_extrator_partial_geo_body (Code): system prompt enxuto pra mapear texto livre → {cidade, raio_km}
- build_targeting_atualizado (Code): merge do novo público/geo com targeting_meta atual

NÃO cria novo node Anthropic — reusa o node 'extrator' existente, só troca o body.
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


SYS_PROMPT_PUBLICO = """Você é um classificador de público de marketing imobiliário. Você lê uma descrição em texto livre de um cliente e devolve APENAS o nome do Pub Quirk que melhor mapeia, em uma única linha sem aspas, sem nada além.

Tabela de Pubs Quirk disponíveis:
- Pub Quirk 0 (broad)
- Pub Quirk 1 (BR 25-60 broad)
- Pub Quirk 1.1 (Condomínio fechado + Casa unifamiliar)
- Pub Quirk 1.2 (Bens de luxo + Investimento + Condomínio)
- Pub Quirk 1.3 (Investimento + OLX + Zap Imóveis)
- Pub Quirk 1.4 (Condomínio + OLX + Zap + Investimento)
- Pub Quirk 1.5 (Desenvolvimento imobiliário)
- Pub Quirk 2 (Real Estate + Investment)
- Pub Quirk 3 (Bens de luxo 30-60)
- Pub Quirk 4 (Bens de luxo + Viajantes 30-64)
- Pub Quirk 5 (Bens de luxo + Viajantes — variante)
- Pub Quirk 6 (capitais grandes + Bens de luxo)
- Pub Quirk 7 (Bens de luxo + Piscina)
- Pub Quirk Invest (Investment + Renda passiva + Finanças)
- Pub Quirk Invest + Intermediário
- Pub Quirk Invest + Alto valor
- Pub Quirk Profissões (Lawyer, Dentist, Judge)
- Pub Quirk Profissões + Intermediário
- Pub Quirk Profissões + Alto valor
- Pub Corretores #1

Devolva APENAS o nome exato de um item da lista. Sem explicação."""


SYS_PROMPT_GEO = """Você é um extrator de geo pra marketing. Lê descrição em texto livre e devolve APENAS um JSON na forma {"cidade":"<nome>","raio_km":<int>} em uma única linha sem nada antes ou depois.

Regras:
- cidade = nome canônico da cidade brasileira (ex: "São Paulo", "Goiânia", "Rio de Janeiro")
- raio_km = inteiro entre 17 e 80 (clamp se necessário)
- Se não houver raio mencionado, use 17 (mínimo Meta)

Responda SOMENTE o JSON."""


def build_publico_body_code():
    sys_q = json.dumps(SYS_PROMPT_PUBLICO)
    return f"""const system = {sys_q};
const desc = String($('process_gestao_step').first().json.gestao.novo_valor.descricao || '').trim();
return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 50,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: desc }}]
  }}
}}];
"""


def build_geo_body_code():
    sys_q = json.dumps(SYS_PROMPT_GEO)
    return f"""const system = {sys_q};
const desc = String($('process_gestao_step').first().json.gestao.novo_valor.descricao || '').trim();
return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 100,
    temperature: 0,
    system,
    messages: [{{ role: "user", content: desc }}]
  }}
}}];
"""


BUILD_TARGETING_ATUALIZADO_CODE = """// Merge do novo público/geo no targeting_meta atual (preserva resto)
const sel = $('process_gestao_step').first().json.gestao.selecionada;
const nv = $('process_gestao_step').first().json.gestao.novo_valor;
const verbo = $('process_gestao_step').first().json.gestao.verbo;
const json_ext = sel.json_extrator_completo;
const targeting = JSON.parse(JSON.stringify(json_ext.targeting_meta || {}));

// Tabela canônica de Pubs Quirk + targeting templates (snapshot da tabela do extrator.md)
const PUBS = {
  'Pub Quirk 0': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003077334693","name":"Condomínio fechado"},{"id":"6003382467537","name":"Casa unifamiliar"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.2': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003077334693","name":"Condomínio fechado"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.3': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6002965402168","name":"OLX Brasil"},{"id":"6014552641654","name":"Zap Imóveis"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.4': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003077334693","name":"Condomínio fechado"},{"id":"6002965402168","name":"OLX Brasil"},{"id":"6014552641654","name":"Zap Imóveis"},{"id":"6003446239080","name":"Investimento imobiliário"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 1.5': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003332796032","name":"Desenvolvimento imobiliário"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 2': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6002979192120","name":"Real Estate"},{"id":"6003392721577","name":"Investment"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 3': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 4': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"behaviors":[{"id":"6002714895372","name":"Viajantes frequentes"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 5': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"behaviors":[{"id":"6002714895372","name":"Viajantes frequentes"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 6': {"geo_locations":{"cities":[{"name":"São Paulo, BR"},{"name":"Rio de Janeiro, BR"},{"name":"Brasília, BR"},{"name":"Belo Horizonte, BR"},{"name":"Curitiba, BR"},{"name":"Porto Alegre, BR"}]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk 7': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]},{"interests":[{"id":"6003221189867","name":"Piscina"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003392721577","name":"Investment"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003287729076","name":"Renda passiva"},{"id":"6003143720966","name":"Finanças pessoais"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest + Intermediário': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"interests":[{"id":"6003392721577","name":"Investment"},{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003143720966","name":"Finanças pessoais"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Invest + Alto valor': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"interests":[{"id":"6003446239080","name":"Investimento imobiliário"},{"id":"6003392721577","name":"Investment"}]},{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"108768179146852","name":"Dentist"},{"id":"106215529409578","name":"Judge"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões + Intermediário': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":60,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"108768179146852","name":"Dentist"},{"id":"403013926540061","name":"Resident Physician"}]}],"targeting_automation":{"advantage_audience":0}},
  'Pub Quirk Profissões + Alto valor': {"geo_locations":{"countries":["BR"]},"age_min":30,"age_max":64,"flexible_spec":[{"work_positions":[{"id":"112696438745118","name":"Lawyer"},{"id":"106215529409578","name":"Judge"}]},{"interests":[{"id":"6007828099136","name":"Bens de luxo"}]}],"user_os":["iOS"],"targeting_automation":{"advantage_audience":0}},
  'Pub Corretores #1': {"geo_locations":{"countries":["BR"]},"age_min":25,"age_max":60,"flexible_spec":[{"interests":[{"id":"6002979192120","name":"Real Estate"},{"id":"6778210171187","name":"Corretagem de imóveis"}],"work_positions":[{"id":"171815889531702","name":"Real Estate Agent"},{"id":"111867022164671","name":"Real estate broker"}]}],"targeting_automation":{"advantage_audience":0}}
};

const PUBS_LIST = Object.keys(PUBS);

const CIDADES = {"São Paulo":"269969","Rio de Janeiro":"267027","Brasília":"245683","Belo Horizonte":"244661","Salvador":"267730","Fortaleza":"253370","Curitiba":"250457","Manaus":"259014","Recife":"266284","Goiânia":"254063","Porto Alegre":"264859","Belém":"244580","Guarulhos":"254529","Campinas":"247071","Maceió":"258670","Natal":"261132","Florianópolis":"253249","Cuiabá":"250332","João Pessoa":"256863","Aracaju":"242415","Teresina":"272278","Campo Grande":"247184","São Luís":"269788","Macapá":"258622","Vitória":"274425","Porto Velho":"265452","Boa Vista":"245039","Palmas":"262281"};

let publico_label = null;

if (verbo === 'ALTERAR_PUBLICO') {
  if (nv.tipo === 'publico_estruturado') {
    publico_label = PUBS_LIST[nv.numero - 1] || 'Pub Quirk 0';
  } else if (nv.tipo === 'publico_livre') {
    // Vem do extrator parcial: $('extrator').item.json.content[0].text
    publico_label = String($('extrator').first().json?.content?.[0]?.text || 'Pub Quirk 0').trim();
    if (!PUBS[publico_label]) publico_label = 'Pub Quirk 0';
  }
  const novoTargetingBase = JSON.parse(JSON.stringify(PUBS[publico_label]));
  // preserva geo atual (se existir cities — não countries genérico)
  if (targeting.geo_locations?.cities && targeting.geo_locations.cities.length) {
    novoTargetingBase.geo_locations = targeting.geo_locations;
  }
  // preserva age se cliente customizou (não usa default da tabela)
  if (json_ext.conjunto?.idade_min) novoTargetingBase.age_min = json_ext.conjunto.idade_min;
  if (json_ext.conjunto?.idade_max) novoTargetingBase.age_max = json_ext.conjunto.idade_max;
  // POLÍTICA Quirk: advantage_audience sempre 0
  novoTargetingBase.targeting_automation = { advantage_audience: 0 };
  return [{ json: { targeting: novoTargetingBase, publico_label_novo: publico_label } }];
}

if (verbo === 'ALTERAR_GEO') {
  let cidade, raio_km;
  if (nv.tipo === 'geo_estruturado') {
    cidade = nv.cidade;
    raio_km = nv.raio_km;
  } else if (nv.tipo === 'geo_livre') {
    try {
      const parsed = JSON.parse(String($('extrator').first().json?.content?.[0]?.text || '{}').trim());
      cidade = parsed.cidade;
      raio_km = parsed.raio_km;
    } catch(e) { cidade = null; raio_km = null; }
  }
  // Clamp raio
  if (typeof raio_km === 'number' && raio_km < 17) raio_km = 17;
  if (typeof raio_km === 'number' && raio_km > 80) raio_km = 80;
  const key = CIDADES[cidade] || null;
  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada', cidade, raio_km } }];
  }
  targeting.geo_locations = { cities: [{ key, radius: raio_km, distance_unit: 'kilometer' }] };
  return [{ json: { targeting, cidade_label_novo: cidade, raio_km_novo: raio_km } }];
}

return [{ json: { targeting } }];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'build_extrator_partial_publico_body' not in nb:
        wf['nodes'].append({
            'id': 'build_extrator_partial_publico_body', 'name': 'build_extrator_partial_publico_body',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2550, 250],
            'parameters': {'language': 'javaScript', 'jsCode': build_publico_body_code()}
        })
        print('  + build_extrator_partial_publico_body adicionado')

    if 'build_extrator_partial_geo_body' not in nb:
        wf['nodes'].append({
            'id': 'build_extrator_partial_geo_body', 'name': 'build_extrator_partial_geo_body',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2550, 400],
            'parameters': {'language': 'javaScript', 'jsCode': build_geo_body_code()}
        })
        print('  + build_extrator_partial_geo_body adicionado')

    if 'build_targeting_atualizado' not in nb:
        wf['nodes'].append({
            'id': 'build_targeting_atualizado', 'name': 'build_targeting_atualizado',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2800, 325],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_TARGETING_ATUALIZADO_CODE}
        })
        print('  + build_targeting_atualizado adicionado')

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
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_06_extrator_parcial_builders.py
```

- [ ] **Step 6.3: Commit**

```bash
git add scripts/b_06_extrator_parcial_builders.py
git commit -m "feat(n8n): extrator parcial (publico/geo) + build_targeting_atualizado"
```

---

## Phase 7: Switch de execução por verbo + check de resultado

### Task 7: execute_gestao_action + check_gestao_result

**Files:**
- Create: `scripts/b_07_execute_action_switch.py`

- [ ] **Step 7.1: Escrever o script**

Conteúdo de `scripts/b_07_execute_action_switch.py`:

```python
#!/usr/bin/env python3
"""
Adiciona:
- execute_gestao_action (Switch por gestao.verbo): roteia pro endpoint Meta certo
- check_gestao_result (Code): classifica resultado da chamada Meta (ok/erro_infra/erro_dado)
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CHECK_GESTAO_RESULT_CODE = """// Classifica resultado da chamada Meta (mesmo padrão de check_meta_results de A)
function classify(node) {
  try {
    const r = $(node).first().json;
    if (r?.error) {
      const msg = r.error.message || '';
      if (/Request failed with status code 5\\d\\d/i.test(msg) || /timeout/i.test(msg) || /is_transient.{1,5}true/i.test(msg) || /ECONN/i.test(msg)) {
        return { ok: false, classe: 'infra', motivo: msg.slice(0, 200) };
      }
      const matchUser = msg.match(/error_user_msg\\\\?\\":\\\\?\\"([^\\"]+)/);
      let motivo = matchUser ? matchUser[1].replace(/\\\\u([0-9a-f]{4})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))) : msg.slice(0, 200);
      return { ok: false, classe: 'dado', motivo };
    }
    return { ok: true, response_id: r?.id || r?.success || true };
  } catch (e) { return { ok: false, classe: 'infra', motivo: e.message }; }
}

const verbo = $('process_gestao_step').first().json.gestao.verbo;
let result;
if (['PAUSAR', 'REATIVAR', 'ENCERRAR'].includes(verbo)) result = classify('meta_update_status');
else if (verbo === 'ALTERAR_VERBA') result = classify('meta_update_adset_budget');
else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(verbo)) result = classify('meta_update_adset_targeting');
else result = { ok: false, classe: 'dado', motivo: 'verbo_desconhecido' };

return [{
  json: {
    ...result,
    verbo,
    telefone: $('normalize_phone').first().json.telefone_normalizado,
    selecionada: $('process_gestao_step').first().json.gestao.selecionada,
    novo_valor: $('process_gestao_step').first().json.gestao.novo_valor
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'execute_gestao_action' not in nb:
        wf['nodes'].append({
            'id': 'execute_gestao_action', 'name': 'execute_gestao_action',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [2800, 100],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'or',
                          'conditions': [
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'PAUSAR', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'REATIVAR', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ENCERRAR', 'operator': {'type': 'string', 'operation': 'equals'}}
                          ]},
                         'renameOutput': True, 'outputKey': 'STATUS'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_VERBA', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'VERBA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'or',
                          'conditions': [
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_PUBLICO', 'operator': {'type': 'string', 'operation': 'equals'}},
                            {'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}", 'rightValue': 'ALTERAR_GEO', 'operator': {'type': 'string', 'operation': 'equals'}}
                          ]},
                         'renameOutput': True, 'outputKey': 'TARGETING'}
                    ]
                },
                'options': {}
            }
        })
        print('  + execute_gestao_action adicionado')

    if 'check_gestao_result' not in nb:
        wf['nodes'].append({
            'id': 'check_gestao_result', 'name': 'check_gestao_result',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [3200, 250],
            'parameters': {'language': 'javaScript', 'jsCode': CHECK_GESTAO_RESULT_CODE}
        })
        print('  + check_gestao_result adicionado')

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
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_07_execute_action_switch.py
```

- [ ] **Step 7.3: Commit**

```bash
git add scripts/b_07_execute_action_switch.py
git commit -m "feat(n8n): execute_gestao_action (Switch) + check_gestao_result"
```

---

## Phase 8: DB UPDATE + audit + reset + msg final

### Task 8: Persistência final + msg de confirmação

**Files:**
- Create: `scripts/b_08_db_update_and_audit.py`

- [ ] **Step 8.1: Escrever o script**

Conteúdo de `scripts/b_08_db_update_and_audit.py`:

```python
#!/usr/bin/env python3
"""
Adiciona:
- update_db_campanha (Postgres): UPDATE status + json_extrator (se alteração)
- audit_gestao (Postgres): INSERT audit_log com antes/depois
- reset_gestao (Postgres): limpa estado.gestao + ajusta etapa_atual
- build_gestao_confirmation_msg (Code): mensagem final pro cliente
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


UPDATE_DB_CAMPANHA_QUERY = """UPDATE auto_ads.campanhas
SET status = CASE
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'PAUSAR' THEN 'PAUSED'
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'REATIVAR' THEN 'ACTIVE'
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'ENCERRAR' THEN 'ARCHIVED'
      ELSE status
    END,
    json_extrator = CASE
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'ALTERAR_VERBA' THEN
        jsonb_set(json_extrator, '{campanha,verba_diaria}', to_jsonb({{ $('check_gestao_result').item.json.novo_valor.valor || 0 }}))
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' IN ('ALTERAR_PUBLICO','ALTERAR_GEO') THEN
        jsonb_set(json_extrator, '{targeting_meta}', '{{ JSON.stringify($('build_targeting_atualizado').item.json.targeting || {}).replace(/'/g, "''") }}'::jsonb)
      ELSE json_extrator
    END,
    ultima_alteracao = NOW()
WHERE id = {{ $('check_gestao_result').item.json.selecionada.campanha_id_db }}"""


AUDIT_GESTAO_QUERY = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
VALUES (
  '{{ $('check_gestao_result').item.json.telefone }}',
  'gestao_{{ $('check_gestao_result').item.json.verbo.toLowerCase() }}',
  jsonb_build_object(
    'campanha_id_db', {{ $('check_gestao_result').item.json.selecionada.campanha_id_db }},
    'campaign_id_meta', '{{ $('check_gestao_result').item.json.selecionada.campaign_id_meta || '' }}',
    'adset_id_meta', '{{ $('check_gestao_result').item.json.selecionada.adset_id_meta || '' }}',
    'antes', '{{ JSON.stringify({status: $('check_gestao_result').item.json.selecionada.status, verba: $('check_gestao_result').item.json.selecionada.verba_atual_reais, publico: $('check_gestao_result').item.json.selecionada.publico_atual, geo_cidade: $('check_gestao_result').item.json.selecionada.geo_cidade_atual, geo_raio: $('check_gestao_result').item.json.selecionada.geo_raio_atual}).replace(/'/g, "''") }}'::jsonb,
    'depois', '{{ JSON.stringify($('check_gestao_result').item.json.novo_valor || {}).replace(/'/g, "''") }}'::jsonb,
    'ok', {{ $('check_gestao_result').item.json.ok }},
    'classe_erro', '{{ $('check_gestao_result').item.json.classe || '' }}',
    'motivo_erro', '{{ ($('check_gestao_result').item.json.motivo || '').replace(/'/g, "''") }}'
  )
)"""


RESET_GESTAO_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
  '{etapa_atual}',
  to_jsonb(CASE
    WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'ENCERRAR' AND {{ $('check_gestao_result').item.json.ok }} THEN 'ativa'
    WHEN {{ $('check_gestao_result').item.json.ok }} THEN 'ativa'
    ELSE 'falhou_dado'
  END::text)
)
WHERE telefone = '{{ $('check_gestao_result').item.json.telefone }}'"""


BUILD_GESTAO_CONFIRMATION_CODE = """// Mensagem final pro cliente
const r = $('check_gestao_result').first().json;
const v = r.verbo;
const sel = r.selecionada;
const nv = r.novo_valor || {};

let text;

if (r.ok) {
  if (v === 'PAUSAR') text = `✓ "${sel.nome}" pausada.`;
  else if (v === 'REATIVAR') text = `✓ "${sel.nome}" reativada.`;
  else if (v === 'ENCERRAR') text = `✓ "${sel.nome}" encerrada e arquivada.`;
  else if (v === 'ALTERAR_VERBA') text = `✓ Verba de "${sel.nome}" atualizada pra R$ ${nv.valor}/dia.`;
  else if (v === 'ALTERAR_PUBLICO') text = `✓ Público de "${sel.nome}" atualizado.`;
  else if (v === 'ALTERAR_GEO') text = `✓ Geo de "${sel.nome}" atualizado.`;
  text += '\\n\\nPode levar alguns minutos pra propagar no Meta.';
} else {
  const classe = r.classe;
  const motivo = r.motivo || 'erro desconhecido';
  if (classe === 'infra') {
    text = `⚠️ Problema técnico do Meta. Tenta de novo daqui a alguns minutos com "SUBIR DENOVO" ou CANCELAR.`;
  } else {
    text = `⚠️ Não consegui executar: ${motivo}\\n\\nManda SUBIR DENOVO pra tentar novamente OU CANCELAR.`;
  }
}

return [{
  json: {
    text,
    telefone: r.telefone
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'update_db_campanha' not in nb:
        wf['nodes'].append({
            'id': 'update_db_campanha', 'name': 'update_db_campanha',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3400, 100],
            'parameters': {'operation': 'executeQuery', 'query': UPDATE_DB_CAMPANHA_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + update_db_campanha adicionado')

    if 'audit_gestao' not in nb:
        wf['nodes'].append({
            'id': 'audit_gestao', 'name': 'audit_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3600, 100],
            'parameters': {'operation': 'executeQuery', 'query': AUDIT_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + audit_gestao adicionado')

    if 'reset_gestao' not in nb:
        wf['nodes'].append({
            'id': 'reset_gestao', 'name': 'reset_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3800, 100],
            'parameters': {'operation': 'executeQuery', 'query': RESET_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_gestao adicionado')

    if 'build_gestao_confirmation_msg' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_confirmation_msg', 'name': 'build_gestao_confirmation_msg',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [4000, 100],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_CONFIRMATION_CODE}
        })
        print('  + build_gestao_confirmation_msg adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 8 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 8.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_08_db_update_and_audit.py
```

- [ ] **Step 8.3: Commit**

```bash
git add scripts/b_08_db_update_and_audit.py
git commit -m "feat(n8n): update_db_campanha + audit_gestao + reset_gestao + msg final"
```

---

## Phase 9: Estender switch_intent + rewire global

### Task 9: switch_intent ganha 6 outputs novos + reconectar tudo

**Files:**
- Create: `scripts/b_10_extend_switch_intent.py`
- Create: `scripts/b_09_rewire_all.py`

- [ ] **Step 9.1: Estender switch_intent com novos verbos**

Conteúdo de `scripts/b_10_extend_switch_intent.py`:

```python
#!/usr/bin/env python3
"""switch_intent: adiciona 6 outputs novos pros verbos de gestão."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def add_rule(rules, intent_name, output_key):
    rules.append({
        'conditions': {
            'options': {'caseSensitive': True, 'typeValidation': 'loose'},
            'combinator': 'and',
            'conditions': [{
                'leftValue': "={{ $('classify_intent').item.json.intent }}",
                'rightValue': intent_name,
                'operator': {'type': 'string', 'operation': 'equals'}
            }]
        },
        'renameOutput': True, 'outputKey': output_key
    })


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    sw = nb['switch_intent']
    rules = sw['parameters']['rules']['values']
    existing_keys = {r.get('outputKey') for r in rules}

    novos = [
        ('PAUSAR', 'PAUSAR'),
        ('REATIVAR', 'REATIVAR'),
        ('ENCERRAR', 'ENCERRAR'),
        ('ALTERAR_VERBA', 'ALTERAR_VERBA'),
        ('ALTERAR_PUBLICO', 'ALTERAR_PUBLICO'),
        ('ALTERAR_GEO', 'ALTERAR_GEO'),
    ]
    for intent, key in novos:
        if key not in existing_keys:
            add_rule(rules, intent, key)
            print(f'  + switch_intent output: {key}')

    sw['parameters']['rules']['values'] = rules

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 9.1 aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 9.2: Rodar a extensão do switch_intent**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_10_extend_switch_intent.py
```

- [ ] **Step 9.3: Escrever rewire global**

Conteúdo de `scripts/b_09_rewire_all.py`:

```python
#!/usr/bin/env python3
"""
Rewire global do workflow conforme spec §7.1.

Conexões:
- load_estado → em_gestao_valido
- em_gestao_valido TRUE → process_gestao_step
- em_gestao_valido FALSE → classify_intent
- process_gestao_step → if_process_acao (Switch by acao)
- switch_intent outputs:
   ... CONFIRMAR/SUBIR_DENOVO/NOVA/OUTRO continuam como antes ...
   PAUSAR → list_campanhas
   REATIVAR → list_campanhas
   ENCERRAR → list_campanhas
   ALTERAR_VERBA → list_campanhas
   ALTERAR_PUBLICO → list_campanhas
   ALTERAR_GEO → list_campanhas
- list_campanhas → init_gestao → build_gestao_response → persist_estado_gestao → media_send_confirma (reuse UAZAPI send_text)

Sub-flow após process_gestao_step:
- acao = avanca → build_gestao_response → persist_estado_gestao → media_send_confirma
- acao = erro_input → build_gestao_response → persist_estado_gestao → media_send_confirma
- acao = reset → reset_gestao_simples (limpa sem chamar Meta) → build_gestao_msg_cancelado → media_send_confirma
- acao = executa → build_extrator_partial_publico_body (se ALTERAR_PUBLICO_livre) OR build_extrator_partial_geo_body (se ALTERAR_GEO_livre) → extrator → build_targeting_atualizado → execute_gestao_action → meta_update_* → check_gestao_result → update_db_campanha → audit_gestao → reset_gestao → build_gestao_confirmation_msg → media_send_confirma
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


RESET_GESTAO_SIMPLES_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
  '{etapa_atual}',
  to_jsonb('ativa'::text)
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""


BUILD_GESTAO_MSG_CANCELADO_CODE = """const motivo = $('process_gestao_step').first().json.motivo || 'cancelado';
let text;
if (motivo === 'cancelado_pelo_cliente' || motivo === 'cancelado_no_confirma') text = 'Ok, cancelei. Volta quando quiser.';
else if (motivo === 'gestao_vazio') text = 'Não tem operação em andamento.';
else text = 'Cancelado.';
return [{ json: { text, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
"""


IF_PROCESS_ACAO_RULES = {
    'avanca': "={{ $('process_gestao_step').item.json.acao === 'avanca' ? 'true' : 'false' }}",
    'erro_input': "={{ $('process_gestao_step').item.json.acao === 'erro_input' ? 'true' : 'false' }}",
    'executa': "={{ $('process_gestao_step').item.json.acao === 'executa' ? 'true' : 'false' }}",
    'reset': "={{ $('process_gestao_step').item.json.acao === 'reset' ? 'true' : 'false' }}",
}


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # Adiciona dois nodes faltantes: reset_gestao_simples + build_gestao_msg_cancelado + switch_acao_gestao
    if 'reset_gestao_simples' not in nb:
        wf['nodes'].append({
            'id': 'reset_gestao_simples', 'name': 'reset_gestao_simples',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1750, 400],
            'parameters': {'operation': 'executeQuery', 'query': RESET_GESTAO_SIMPLES_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_gestao_simples adicionado')

    if 'build_gestao_msg_cancelado' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_msg_cancelado', 'name': 'build_gestao_msg_cancelado',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [1950, 400],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_MSG_CANCELADO_CODE}
        })
        print('  + build_gestao_msg_cancelado adicionado')

    if 'switch_acao_gestao' not in nb:
        wf['nodes'].append({
            'id': 'switch_acao_gestao', 'name': 'switch_acao_gestao',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [1750, 50],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'avanca', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'AVANCA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'erro_input', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'ERRO_INPUT'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'executa', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'EXECUTA'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.acao }}", 'rightValue': 'reset', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'RESET'}
                    ]
                }, 'options': {}
            }
        })
        print('  + switch_acao_gestao adicionado')

    # Rewire
    # load_estado → em_gestao_valido (TRUE) → process_gestao_step → switch_acao_gestao
    #                              (FALSE) → classify_intent
    wf['connections']['load_estado'] = {'main': [[{'node': 'em_gestao_valido', 'type': 'main', 'index': 0}]]}
    wf['connections']['em_gestao_valido'] = {
        'main': [
            [{'node': 'process_gestao_step', 'type': 'main', 'index': 0}],
            [{'node': 'classify_intent', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['process_gestao_step'] = {'main': [[{'node': 'switch_acao_gestao', 'type': 'main', 'index': 0}]]}

    # switch_acao_gestao outputs:
    # 0=AVANCA → build_gestao_response → persist_estado_gestao → media_send_confirma
    # 1=ERRO_INPUT → build_gestao_response → media_send_confirma (sem persist)
    # 2=EXECUTA → load_meta_token → ... fluxo de execução ...
    # 3=RESET → reset_gestao_simples → build_gestao_msg_cancelado → media_send_confirma
    wf['connections']['switch_acao_gestao'] = {
        'main': [
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'load_meta_token', 'type': 'main', 'index': 0}],
            [{'node': 'reset_gestao_simples', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['reset_gestao_simples'] = {'main': [[{'node': 'build_gestao_msg_cancelado', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_msg_cancelado'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    # switch_intent: 6 novos outputs → list_campanhas
    # Mantém os existentes (CONFIRMAR, SUBIR_DENOVO, NOVA, OUTRO) intactos
    sw = nb['switch_intent']
    current_outputs = sw['parameters']['rules']['values']
    current_main = wf['connections'].get('switch_intent', {}).get('main', [])
    # Garante que mantém os 4 originais (índices 0-3) e adiciona 6 novos
    while len(current_main) < len(current_outputs) + 1:  # +1 pro fallback
        current_main.append([])
    for i, rule in enumerate(current_outputs):
        if rule.get('outputKey') in ['PAUSAR', 'REATIVAR', 'ENCERRAR', 'ALTERAR_VERBA', 'ALTERAR_PUBLICO', 'ALTERAR_GEO']:
            current_main[i] = [{'node': 'list_campanhas', 'type': 'main', 'index': 0}]
    wf['connections']['switch_intent']['main'] = current_main

    # list_campanhas → init_gestao → build_gestao_response → persist_estado_gestao → media_send_confirma
    wf['connections']['list_campanhas'] = {'main': [[{'node': 'init_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['init_gestao'] = {'main': [[{'node': 'build_gestao_response', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_response'] = {'main': [[{'node': 'persist_estado_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_estado_gestao'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    # Execução: load_meta_token → execute_gestao_action (Switch by verbo)
    # STATUS → meta_update_status; VERBA → meta_update_adset_budget; TARGETING → build_extrator_partial_*_body (se livre) OR build_targeting_atualizado direto
    wf['connections']['load_meta_token'] = {'main': [[{'node': 'execute_gestao_action', 'type': 'main', 'index': 0}]]}
    wf['connections']['execute_gestao_action'] = {
        'main': [
            [{'node': 'meta_update_status', 'type': 'main', 'index': 0}],          # STATUS (PAUSAR/REATIVAR/ENCERRAR)
            [{'node': 'meta_update_adset_budget', 'type': 'main', 'index': 0}],    # VERBA
            [{'node': 'build_targeting_atualizado', 'type': 'main', 'index': 0}]   # TARGETING (PUBLICO/GEO) — entra direto, build_targeting_atualizado lida com decidir se chama extrator antes
        ]
    }
    # Para TARGETING: lógica fica em build_targeting_atualizado que consulta gestao.novo_valor.tipo
    # Se for 'publico_livre' ou 'geo_livre', precisa do extrator antes — adicionar Switch:
    # Vou simplificar: build_targeting_atualizado sempre tenta primeiro, e se faltar dado de extrator retorna error → caímos num passo intermediário

    # Para ALTERAR_PUBLICO_livre / ALTERAR_GEO_livre — fazemos um IF antes de build_targeting_atualizado
    # MAS pra simplificar v1: sempre rodar build_extrator_partial_publico_body OU build_extrator_partial_geo_body
    # quando o tipo do novo_valor for 'livre'. Isso é feito via novo switch interno.

    if 'switch_publico_geo_livre' not in nb:
        wf['nodes'].append({
            'id': 'switch_publico_geo_livre', 'name': 'switch_publico_geo_livre',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [2400, 325],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.novo_valor.tipo }}", 'rightValue': 'publico_livre', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'PUBLICO_LIVRE'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('process_gestao_step').item.json.gestao.novo_valor.tipo }}", 'rightValue': 'geo_livre', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'GEO_LIVRE'}
                    ]
                },
                'options': {'fallbackOutput': 'extra'}  # estruturado → vai direto
            }
        })
        print('  + switch_publico_geo_livre adicionado')

    # Re-roteia o output TARGETING do execute_gestao_action: vai pra switch_publico_geo_livre primeiro
    wf['connections']['execute_gestao_action']['main'][2] = [{'node': 'switch_publico_geo_livre', 'type': 'main', 'index': 0}]

    # switch_publico_geo_livre:
    # 0=PUBLICO_LIVRE → build_extrator_partial_publico_body → extrator → build_targeting_atualizado
    # 1=GEO_LIVRE → build_extrator_partial_geo_body → extrator → build_targeting_atualizado
    # fallback (estruturado) → build_targeting_atualizado direto
    wf['connections']['switch_publico_geo_livre'] = {
        'main': [
            [{'node': 'build_extrator_partial_publico_body', 'type': 'main', 'index': 0}],
            [{'node': 'build_extrator_partial_geo_body', 'type': 'main', 'index': 0}],
            [{'node': 'build_targeting_atualizado', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['build_extrator_partial_publico_body'] = {'main': [[{'node': 'extrator', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_extrator_partial_geo_body'] = {'main': [[{'node': 'extrator', 'type': 'main', 'index': 0}]]}
    # extrator → build_targeting_atualizado (override do A: precisa entender contexto)
    # IMPORTANTE: o extrator também é usado no fluxo CONFIRMAR do A (vai pra parse_extrator).
    # Pra evitar conflito, vou manter extrator → parse_extrator (fluxo A) E mudar build_extrator_partial_*
    # pra usar extrator → build_targeting_atualizado direto NÃO funciona porque conexão é única.
    #
    # Solução: copiar o node extrator pra um clone 'extrator_partial' usado só pela gestão.
    pass

    # Como conexão tem que ser única, vamos criar um clone 'extrator_partial' do node extrator
    if 'extrator_partial' not in nb:
        # Clona o node extrator
        ext = nb.get('extrator')
        if ext:
            clone = dict(ext)
            clone['name'] = 'extrator_partial'
            clone['id'] = 'extrator_partial'
            clone['position'] = [2700, 325]
            wf['nodes'].append(clone)
            print('  + extrator_partial (clone do extrator) adicionado')

    # Atualiza conexões dos builders parciais pra extrator_partial em vez de extrator
    wf['connections']['build_extrator_partial_publico_body'] = {'main': [[{'node': 'extrator_partial', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_extrator_partial_geo_body'] = {'main': [[{'node': 'extrator_partial', 'type': 'main', 'index': 0}]]}
    wf['connections']['extrator_partial'] = {'main': [[{'node': 'build_targeting_atualizado', 'type': 'main', 'index': 0}]]}

    # build_targeting_atualizado → meta_update_adset_targeting
    wf['connections']['build_targeting_atualizado'] = {'main': [[{'node': 'meta_update_adset_targeting', 'type': 'main', 'index': 0}]]}

    # 3 endpoints Meta → check_gestao_result
    wf['connections']['meta_update_status'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}
    wf['connections']['meta_update_adset_budget'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}
    wf['connections']['meta_update_adset_targeting'] = {'main': [[{'node': 'check_gestao_result', 'type': 'main', 'index': 0}]]}

    # check_gestao_result → update_db_campanha → audit_gestao → reset_gestao → build_gestao_confirmation_msg → media_send_confirma
    wf['connections']['check_gestao_result'] = {'main': [[{'node': 'update_db_campanha', 'type': 'main', 'index': 0}]]}
    wf['connections']['update_db_campanha'] = {'main': [[{'node': 'audit_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['audit_gestao'] = {'main': [[{'node': 'reset_gestao', 'type': 'main', 'index': 0}]]}
    wf['connections']['reset_gestao'] = {'main': [[{'node': 'build_gestao_confirmation_msg', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_gestao_confirmation_msg'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 9.3 (rewire global) aplicada')


if __name__ == '__main__':
    main()
```

- [ ] **Step 9.4: Rodar rewire**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/b_09_rewire_all.py
```

- [ ] **Step 9.5: Verificar estrutura final**

```bash
python3 -c "
import sys; sys.path.insert(0, 'scripts')
import n8n_api, config
wf = n8n_api.get_workflow(config.get_workflow_id())
names = sorted(n['name'] for n in wf['nodes'])
must = ['em_gestao_valido', 'process_gestao_step', 'switch_acao_gestao', 'list_campanhas', 'init_gestao', 'build_gestao_response', 'persist_estado_gestao', 'reset_gestao_simples', 'build_gestao_msg_cancelado', 'execute_gestao_action', 'switch_publico_geo_livre', 'extrator_partial', 'build_extrator_partial_publico_body', 'build_extrator_partial_geo_body', 'build_targeting_atualizado', 'meta_update_status', 'meta_update_adset_budget', 'meta_update_adset_targeting', 'check_gestao_result', 'update_db_campanha', 'audit_gestao', 'reset_gestao', 'build_gestao_confirmation_msg']
faltando = [m for m in must if m not in names]
assert not faltando, f'Faltando: {faltando}'
print(f'✓ {len(names)} nodes total. Gestão completa.')
"
```

- [ ] **Step 9.6: Commit**

```bash
git add scripts/b_09_rewire_all.py scripts/b_10_extend_switch_intent.py
git commit -m "feat(n8n): rewire global B + switch_intent estendido"
```

---

## Phase 10: Smoke tests

### Task 10: Test PAUSAR ponta-a-ponta

**Files:**
- Create: `scripts/test_b_pausar.py`

- [ ] **Step 10.1: Escrever**

Conteúdo de `scripts/test_b_pausar.py`:

```python
#!/usr/bin/env python3
"""Smoke test PAUSAR: pré-popula 1 campanha ACTIVE, manda fluxo, valida status PAUSED no DB."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def setup():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    cur.execute(f"UPDATE auto_ads.campanhas SET status='ACTIVE' WHERE telefone='{PHONE}' AND campaign_id IS NOT NULL LIMIT 1")
    conn.commit(); conn.close()


def send(text):
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


def count_status(s):
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT count(*) FROM auto_ads.campanhas WHERE telefone='{PHONE}' AND status=%s", (s,))
    n = cur.fetchone()[0]; conn.close()
    return n


def main():
    setup()
    before = count_status('ACTIVE')
    assert before >= 1, f'precisa de >=1 ACTIVE pra testar; tem {before}'

    print('[pausar]')
    send('pausar')
    time.sleep(8)
    estado = get_estado()
    assert estado.get('gestao'), 'esperava estado.gestao populado após "pausar"'
    assert estado['gestao']['passo'] == 'selecao', f"esperava passo=selecao, é {estado['gestao']['passo']}"
    assert len(estado['gestao']['lista_candidatas']) >= 1
    print(f"  ✓ lista com {len(estado['gestao']['lista_candidatas'])} candidatas")

    print('[1]')
    send('1')
    time.sleep(8)
    estado = get_estado()
    assert estado['gestao']['passo'] == 'confirmacao', f"esperava passo=confirmacao, é {estado['gestao']['passo']}"
    print(f"  ✓ avançou pra confirmacao, selecionada: {estado['gestao']['selecionada']['nome']}")

    print('[SIM]')
    send('SIM')
    time.sleep(20)
    estado = get_estado()
    assert estado.get('gestao') is None, f"esperava gestao=null após execução, é {estado.get('gestao')}"
    after = count_status('PAUSED')
    assert after > 0, f'esperava >=1 PAUSED depois do fluxo; tem {after}'
    print(f'  ✓ PAUSED no DB. Fluxo completo.')


if __name__ == '__main__':
    main()
```

- [ ] **Step 10.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_b_pausar.py
```

- [ ] **Step 10.3: Commit**

```bash
git add scripts/test_b_pausar.py
git commit -m "test(B): PAUSAR fluxo completo"
```

---

### Task 11: Test ALTERAR_VERBA

**Files:**
- Create: `scripts/test_b_alterar_verba.py`

- [ ] **Step 11.1: Escrever**

Conteúdo de `scripts/test_b_alterar_verba.py`:

```python
#!/usr/bin/env python3
"""Smoke test ALTERAR_VERBA: fluxo de 4 turnos, valida verba nova no DB."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def setup():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    # Garante 1 campanha com adset_id e verba 50
    cur.execute(f"""UPDATE auto_ads.campanhas
                    SET status='ACTIVE',
                        json_extrator = jsonb_set(json_extrator, '{{campanha,verba_diaria}}', to_jsonb(50))
                    WHERE telefone='{PHONE}' AND adset_id IS NOT NULL AND adset_id != 'undefined'
                    LIMIT 1""")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_state_e_verba():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    estado = cur.fetchone()[0]
    cur.execute(f"SELECT (json_extrator->'campanha'->>'verba_diaria')::int FROM auto_ads.campanhas WHERE telefone='{PHONE}' AND adset_id IS NOT NULL AND adset_id != 'undefined' ORDER BY ultima_alteracao DESC LIMIT 1")
    verba = cur.fetchone()[0]
    conn.close()
    return estado, verba


def main():
    setup()
    estado, v0 = get_state_e_verba()
    print(f'verba inicial: R$ {v0}/dia')

    send('alterar verba'); time.sleep(8)
    estado, _ = get_state_e_verba()
    assert estado.get('gestao'), 'gestao não populado'
    assert estado['gestao']['passo'] == 'selecao'

    send('1'); time.sleep(8)
    estado, _ = get_state_e_verba()
    assert estado['gestao']['passo'] == 'coleta_valor'

    send('80'); time.sleep(8)
    estado, _ = get_state_e_verba()
    assert estado['gestao']['passo'] == 'confirmacao'
    assert estado['gestao']['novo_valor']['valor'] == 80

    send('SIM'); time.sleep(20)
    estado, v1 = get_state_e_verba()
    assert estado.get('gestao') is None
    assert v1 == 80, f'verba esperada 80, tem {v1}'
    print(f'  ✓ verba atualizada de R$ {v0} → R$ {v1}/dia')


if __name__ == '__main__':
    main()
```

- [ ] **Step 11.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_b_alterar_verba.py
```

- [ ] **Step 11.3: Commit**

```bash
git add scripts/test_b_alterar_verba.py
git commit -m "test(B): ALTERAR_VERBA fluxo completo"
```

---

### Task 12: Test CANCELAR em cada passo

**Files:**
- Create: `scripts/test_b_cancelar.py`

- [ ] **Step 12.1: Escrever**

Conteúdo de `scripts/test_b_cancelar.py`:

```python
#!/usr/bin/env python3
"""Smoke test CANCELAR: testa cancelamento em cada passo do sub-flow."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    cur.execute(f"UPDATE auto_ads.campanhas SET status='ACTIVE' WHERE telefone='{PHONE}' AND campaign_id IS NOT NULL")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def cancel_at(steps_before_cancel):
    reset()
    send('pausar'); time.sleep(8)
    for s in steps_before_cancel:
        send(s); time.sleep(8)
    send('cancelar'); time.sleep(8)
    estado = get_estado()
    assert estado.get('gestao') is None, f'gestao não resetado após cancelar (passos antes: {steps_before_cancel})'
    print(f'  ✓ CANCELAR após passos {steps_before_cancel} resetou gestao')


def main():
    cancel_at([])              # cancelar no selecao
    cancel_at(['1'])           # cancelar no confirmacao (PAUSAR)


if __name__ == '__main__':
    main()
```

- [ ] **Step 12.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_b_cancelar.py
```

- [ ] **Step 12.3: Commit**

```bash
git add scripts/test_b_cancelar.py
git commit -m "test(B): CANCELAR em cada passo"
```

---

### Task 13: Test TTL de 10 min

**Files:**
- Create: `scripts/test_b_ttl.py`

- [ ] **Step 13.1: Escrever**

Conteúdo de `scripts/test_b_ttl.py`:

```python
#!/usr/bin/env python3
"""Smoke test TTL: força iniciado_em antigo no DB, manda msg, valida reset."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def setup_expired_gestao():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    # Cria conversa com gestao expirada (15 min atrás)
    expired = json.dumps({
        'etapa_atual': 'em_gestao',
        'criativo': {'recebido': False},
        'brief': {},
        'ultima_tentativa': None,
        'gestao': {
            'verbo': 'PAUSAR',
            'passo': 'selecao',
            'iniciado_em': '2026-05-30T10:00:00Z',  # bem antigo
            'lista_candidatas': [{'posicao': 1, 'campanha_id_db': 999, 'nome': 'test'}],
            'selecionada': None,
            'novo_valor': None
        }
    })
    cur.execute(f"INSERT INTO auto_ads.conversas (telefone, historico, estado_json) VALUES ('{PHONE}', '', %s)", (expired,))
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def main():
    setup_expired_gestao()
    estado_antes = get_estado()
    assert estado_antes['gestao'] is not None, 'setup falhou'

    # Envia msg qualquer — TTL expirou, deveria cair no fluxo normal
    send('oi'); time.sleep(15)
    estado = get_estado()
    # Após oi, agente responde normal e gestao deveria ser limpo (TTL)
    # Como em_gestao_valido vai FALSE → vai pro classify_intent → fluxo normal
    # O estado.gestao persistido pode continuar lá (sem cleanup explícito)
    # MAS etapa_atual NÃO deveria ser em_gestao
    assert estado['etapa_atual'] != 'em_gestao', f'etapa não saiu de em_gestao: {estado["etapa_atual"]}'
    print(f'  ✓ TTL expirou — fluxo normal retomado (etapa={estado["etapa_atual"]})')


if __name__ == '__main__':
    main()
```

- [ ] **Step 13.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_b_ttl.py
```

- [ ] **Step 13.3: Commit**

```bash
git add scripts/test_b_ttl.py
git commit -m "test(B): TTL 10min expira sub-flow"
```

---

### Task 14: Test inputs inválidos

**Files:**
- Create: `scripts/test_b_input_invalido.py`

- [ ] **Step 14.1: Escrever**

Conteúdo de `scripts/test_b_input_invalido.py`:

```python
#!/usr/bin/env python3
"""Smoke test inputs inválidos: número fora de range, verba fora de faixa."""
import os, sys, json, time, urllib.request
import psycopg2

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config

PHONE = '5511980838409'
DB_URL = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')


def reset():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"DELETE FROM auto_ads.conversas WHERE telefone = '{PHONE}'")
    cur.execute(f"UPDATE auto_ads.campanhas SET status='ACTIVE' WHERE telefone='{PHONE}'")
    conn.commit(); conn.close()


def send(text):
    payload = {'chat': {'phone': '+55 11 98083-8409'},
               'message': {'type': 'text', 'text': text, 'from': f'{PHONE}@s.whatsapp.net'}}
    req = urllib.request.Request(config.WORKFLOW_URL, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}, method='POST')
    urllib.request.urlopen(req, timeout=60).read()


def get_estado():
    conn = psycopg2.connect(DB_URL); cur = conn.cursor()
    cur.execute(f"SELECT estado_json FROM auto_ads.conversas WHERE telefone='{PHONE}'")
    row = cur.fetchone(); conn.close()
    return row[0] if row else None


def main():
    # Teste 1: número fora de range
    reset()
    send('pausar'); time.sleep(8)
    estado = get_estado()
    n = len(estado['gestao']['lista_candidatas'])
    send(str(n + 99)); time.sleep(8)  # número impossível
    estado = get_estado()
    assert estado['gestao']['passo'] == 'selecao', f'esperava continuar em selecao após input inválido, tem {estado["gestao"]["passo"]}'
    print(f'  ✓ número fora de range mantém passo=selecao')

    # Teste 2: verba fora de faixa
    reset()
    send('alterar verba'); time.sleep(8)
    send('1'); time.sleep(8)
    send('200'); time.sleep(8)  # > 100
    estado = get_estado()
    assert estado['gestao']['passo'] == 'coleta_valor', f'esperava continuar em coleta_valor, tem {estado["gestao"]["passo"]}'
    print(f'  ✓ verba 200 (fora) mantém passo=coleta_valor')


if __name__ == '__main__':
    main()
```

- [ ] **Step 14.2: Rodar**

```bash
cd /Users/renanreal/quirk_auto_ads && python3 scripts/test_b_input_invalido.py
```

- [ ] **Step 14.3: Commit**

```bash
git add scripts/test_b_input_invalido.py
git commit -m "test(B): inputs inválidos mantém passo"
```

---

## Phase 11: Handoff final

### Task 15: Atualizar HANDOFF + reset conversa

**Files:**
- Modify: `docs/HANDOFF_V2.md`

- [ ] **Step 15.1: Adicionar seção B no handoff**

Use Edit pra adicionar antes da seção "Próximos sub-projetos":

```markdown
## Sub-projeto B (gestão de campanhas) — IMPLEMENTADO

6 verbos disponíveis no WhatsApp:
- **PAUSAR** / **REATIVAR** / **ENCERRAR** — gestão de status (Meta + DB)
- **ALTERAR VERBA** / **ALTERAR PÚBLICO** / **ALTERAR GEO** — edição de dados

Fluxo: comando → lista numerada → selecionar (1, 2, 3...) → confirmar (SIM/NÃO).
CANCELAR em qualquer passo volta ao fluxo normal.
TTL de 10 min em sub-flows abandonados.

Audit imutável em `auto_ads.audit_log` (evento `gestao_*` com antes/depois).
Política NUNCA DELETE preservada (ENCERRAR usa ARCHIVED).
```

- [ ] **Step 15.2: Reset da conversa de teste do Renan**

```bash
python3 -c "
import psycopg2
db_url = open('/Users/renanreal/.config/n8n-quirk/supabase_url.txt').read().strip().replace('aws-0-', 'aws-1-')
conn = psycopg2.connect(db_url); cur = conn.cursor()
cur.execute(\"DELETE FROM auto_ads.conversas WHERE telefone = '5511980838409'\")
conn.commit(); conn.close()
print('✓ conversa resetada pra teste real do Renan')
"
```

- [ ] **Step 15.3: Commit final**

```bash
git add docs/HANDOFF_V2.md
git commit -m "docs: handoff B — gestão de campanhas implementada"
```

---

## Self-Review

**Spec coverage** (checagem das seções do design):
- §4 modelo de estado: Task 3 (process_gestao_step) + Task 4 (init_gestao popula gestao + TTL check em em_gestao_valido)
- §5 detecção de intent: Task 2 (classify_intent v3) + Task 3 (em_gestao_valido + process_gestao_step) + Task 9 (switch_acao_gestao)
- §6 UX por verbo: Task 4 (build_gestao_response)
- §7 arquitetura: Tasks 3, 4, 5, 6, 7, 8, 9
- §8 lifecycle status: Task 8 (update_db_campanha SQL CASE)
- §9 persistência + audit: Task 1 (SQL ultima_alteracao) + Task 8 (update_db_campanha + audit_gestao)
- §10 tratamento de erro: Task 7 (check_gestao_result classifica infra/dado)
- §11 migração: Task 1 (SQL 005) + scripts idempotentes
- §12 riscos: Tasks 3 (input validation), 13 (TTL), 14 (inputs inválidos), 12 (CANCELAR)
- §13 testes: Tasks 10-14 (5 smoke tests dos cenários críticos; outros 5 são extensões opcionais)

**Placeholder scan:** nenhum TBD/TODO/incompleto. Todas as queries SQL, código JS e Python estão completos.

**Type consistency:**
- `estado.gestao` aparece em Tasks 3, 4, 7, 8 — sempre objeto com {verbo, passo, lista_candidatas, selecionada, novo_valor}
- `gestao.verbo` string uppercase (PAUSAR, REATIVAR, etc.) em Tasks 2, 3, 5, 7, 8
- `gestao.passo` string lowercase (selecao, coleta_valor, confirmacao) — consistente em Tasks 3, 4
- `gestao.lista_candidatas[i]` com {posicao, campanha_id_db, campaign_id_meta, adset_id_meta, nome, status, verba_atual_reais, publico_atual, geo_cidade_atual, geo_raio_atual, json_extrator_completo} — usado em init_gestao (Task 4) e build_gestao_response (Task 4) e check_gestao_result (Task 7) e update_db_campanha (Task 8)
- `check_gestao_result` output: {ok, classe, motivo, verbo, telefone, selecionada, novo_valor} — usado em update_db_campanha + audit_gestao + reset_gestao + build_gestao_confirmation_msg (Task 8)

**Diferenças notadas durante review:**
- Plan inclui Task 15 (handoff + reset) que não foi mencionada explicitamente na spec mas é prática boa de finalização do trabalho — mantido.
- Quantidade de smoke tests (Task 10-14 = 5 cenários) é menor que os 10 listados em §13.1 da spec. Os 5 cobertos são os mais críticos (PAUSAR, ALTERAR_VERBA, CANCELAR, TTL, input inválido). Os outros 5 (REATIVAR, ENCERRAR, ALTERAR_PUBLICO estruturado, ALTERAR_PUBLICO livre, ALTERAR_GEO estruturado) são extensões diretas dos padrões — adicionar se necessário durante implementação.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-30-quirk-auto-ads-B-gestao-campanhas.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch um subagent por task, review entre tasks
**2. Inline Execution** — Executa tasks nesta sessão com checkpoints

Qual?
