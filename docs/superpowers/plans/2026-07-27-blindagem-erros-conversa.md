# Blindagem de erros e fluidez — Implementation Plan

> **For agentic workers:** executar via superpowers:executing-plans. Steps com checkbox.

**Goal:** Blindar o Auto Ads pra que nenhum erro do Meta ou mensagem fora de ordem cause ação errada (nunca criar/duplicar campanha por engano) e pra que a conversa siga fluida quando o cliente muda de ideia.

**Architecture:** Edições de `jsCode`/SQL em nós do workflow principal `fBUin1UPt5xJEp6g`, via API do n8n, cada uma com backup + `node --check`, no padrão dos scripts `g_*`. Cada task tem um script `scripts/g_NN_*.py` (dry-run + deploy) e um teste (`scripts/_test_*.py` ou replay de execução real).

**Tech Stack:** n8n REST (`scripts/n8n_api.py`), Node (harness/`--check`), Postgres (psycopg2), Python 3.

## Global Constraints

- Toda alteração de nó: **backup antes** em `n8n_workflow/backup_*.json`, `node --check` no jsCode, `settings={"executionOrder": ...}` no PUT.
- Âncoras de `str.replace` devem casar **exatamente 1×** (abortar se ≠1).
- **Sem gasto novo:** testes por replay de execução real + harness isolado. Nada de subir campanha.
- Nomes de nós reais (verificados): `format_status_response`, `switch_intent`, `build_extrator_body`, `check_gestao_result`, `build_gestao_confirmation_msg`, `prep_update_db`, `reset_gestao`, `process_gestao_step`, `check_meta_results`.

---

### Task 1: Status claro no relatório (Parte 4)

**Files:** Modify nó `format_status_response` (workflow principal). Script: `scripts/g_15_status_legivel.py`.

- [ ] **Step 1:** Ler o jsCode atual e confirmar a âncora `'Status no Meta: ' + d.status_atual`.
- [ ] **Step 2:** Substituir por um mapa:
```js
const MAPA_STATUS = { CREATED_ACTIVE:'🟢 No ar', ACTIVE:'🟢 No ar', CREATED_PAUSED:'⏸️ Pausada', PAUSED:'⏸️ Pausada', ARCHIVED:'📁 Encerrada', PARTIAL_FAIL:'⚠️ Subiu com pendência — me chama' };
const status_legivel = MAPA_STATUS[d.status_atual] || d.status_atual;
```
e trocar a linha por `'Status: ' + status_legivel`.
- [ ] **Step 3:** `node --check` (dry-run). Deploy. Commit.
- [ ] **Step 4 (teste):** replay de uma execução real de STATUS (ex. 22851) contra o código novo, ou harness com cada valor do mapa → confirmar "🟢 No ar"/"⏸️ Pausada".

### Task 2: Gate do SUBIR_DENOVO por etapa_atual (Parte 1a)

**Files:** Novo nó Code `gate_subir_denovo` entre `switch_intent`(saída SUBIR_DENOVO) e `build_extrator_body`; IF `if_pode_subir_denovo`; msg `send_bloqueio_denovo`. Script: `scripts/g_16_gate_subir_denovo.py`.

- [ ] **Step 1:** Mapear a conexão atual `switch_intent[SUBIR_DENOVO] -> build_extrator_body`.
- [ ] **Step 2:** Inserir nó Code `gate_subir_denovo`:
```js
const etapa = $('load_estado').first().json.estado?.etapa_atual;
const pode = etapa === 'pronta_pra_subir';
let motivo = '';
if (etapa === 'ativa') motivo = 'Sua última campanha já está no ar 🟢. Pra criar outra, manda *NOVA CAMPANHA*.';
else if (!pode) motivo = 'Não tem nenhuma campanha pronta pra subir ainda. Me manda os dados do imóvel que a gente monta. 👍';
return [{ json: { pode, motivo, telefone: $('normalize_phone').first().json.telefone_normalizado } }];
```
- [ ] **Step 3:** IF `pode === true` → `build_extrator_body`; senão → nó httpRequest `send_bloqueio_denovo` (envia `motivo`) → `respond_immediate`.
- [ ] **Step 4:** `node --check`, backup, deploy, commit.
- [ ] **Step 5 (teste):** replay do exec 22942 (estado `etapa_atual:'ativa'`) → deve **bloquear** (pode=false, mensagem NOVA CAMPANHA), sem chamar `build_extrator_body`/`meta_d1_campaign`.

### Task 3: Erro de gestão seguro + retry por SIM (Partes 1b, 2a, 2b)

**Files:** Modify `check_gestao_result` (classificação infra), `prep_update_db` (flag `manter_gestao`), `reset_gestao` (SQL condicional), `build_gestao_confirmation_msg` (mensagens). Script: `scripts/g_17_retry_gestao_seguro.py`.

- [ ] **Step 1 (classify infra):** em `check_gestao_result.classify`, ampliar o teste de `infra` pra cobrir rate limit e transitórios:
```js
if (/status code 5\d\d/i.test(msg) || /timeout/i.test(msg) || /is_transient["\s:]+true/i.test(msg) || /ECONN/i.test(msg) || /\(#613\)/.test(msg) || /rate limit/i.test(msg) || /"code":\s*(1|2|4|17|341|613|80004)\b/.test(msg)) {
  return { ok:false, classe:'infra', motivo: msg.slice(0,200) };
}
```
- [ ] **Step 2 (flag):** em `prep_update_db`, após obter `r` de check_gestao_result, adicionar ao json de saída: `manter_gestao: (r.ok === false && r.classe === 'infra')`.
- [ ] **Step 3 (reset condicional):** trocar o SQL de `reset_gestao` por:
```sql
UPDATE auto_ads.conversas
SET estado_json = CASE
  WHEN {{ $('prep_update_db').item.json.manter_gestao ? 'true' : 'false' }} THEN estado_json
  ELSE jsonb_set(jsonb_set(estado_json, '{gestao}', 'null'::jsonb), '{etapa_atual}', '"ativa"'::jsonb)
END
WHERE telefone = '{{ $('prep_update_db').item.json.telefone }}'
```
- [ ] **Step 4 (mensagens):** em `build_gestao_confirmation_msg`, ramo de erro:
```js
if (classe === 'infra') {
  text = `⚙️ Deu um engasgo no Meta (nada de errado com seu pedido). Manda *SIM* de novo daqui a 1 min que eu repito, ou *CANCELAR*.`;
} else {
  text = `⚠️ Não consegui: ${motivo}\n\nMe manda o dado certo, ou *CANCELAR*.`;
}
```
(remove qualquer menção a "SUBIR DENOVO").
- [ ] **Step 5:** `node --check` nos Code, backup do workflow, deploy, commit.
- [ ] **Step 6 (teste):** replay do exec 22937 (rate limit #613) → classe=`infra`, mensagem com "SIM"/"engasgo", `manter_gestao=true`. Harness: rodar `classify` com o corpo real do #613 e confirmar `infra`.

### Task 4: Perguntar antes de trocar de contexto (Parte 3)

**Files:** Modify `process_gestao_step`. Script: `scripts/g_18_pergunta_troca.py`.

- [ ] **Step 1:** Adicionar helper no topo de `process_gestao_step`:
```js
function pareceComando(m) {
  const s = m.trim().toLowerCase();
  return /^(pausar|parar|reativar|ativar|encerrar|arquivar|status|relat[óo]rio|nova campanha|subir|tutorial|ajuda)\b/.test(s)
      || /^(alterar|mudar|trocar)\s+(verba|p[úu]blico|geo|regi[ãa]o|cidade|bairro|localiza)/.test(s);
}
```
- [ ] **Step 2 (decisão de troca pendente):** logo após o check de `cancelar`, tratar `gestao.aguardando_troca`:
```js
if (gestao.aguardando_troca) {
  if (/^(continuar|anterior|1|seguir)\b/i.test(msg)) { delete gestao.aguardando_troca; return [{ json: { acao:'reprompt', gestao, estado } }]; }
  if (/^(trocar|nova|desconsiderar|desconsidera|deixa|2)\b/i.test(msg)) return [{ json: { acao:'reset', motivo:'troca_confirmada' } }];
  return [{ json: { acao:'pergunta_troca', gestao, estado, reask:true } }];
}
```
- [ ] **Step 3 (detectar comando no meio):** nos ramos de erro de `selecao` e `confirmacao`, e **antes** do texto-livre em `coleta_valor`, se `pareceComando(msg)` → marcar `gestao.aguardando_troca = true` e `return [{ json: { acao:'pergunta_troca', gestao, estado } }]`.
- [ ] **Step 4 (wiring da resposta):** `switch_acao_gestao` precisa de saídas pra `pergunta_troca` (envia a pergunta CONTINUAR/TROCAR) e `reprompt` (repete o pedido do passo). Mapear no switch e ligar aos nós de mensagem. Verificar as saídas atuais do `switch_acao_gestao` antes de editar.
- [ ] **Step 5:** `node --check`, backup, deploy, commit.
- [ ] **Step 6 (teste):** replay do exec 22877 ("Pausar" em passo selecao) → `acao:'pergunta_troca'`, não "número inválido". Harness de `pareceComando` (aceita comandos, rejeita "Moema SP 6", "25", "sim").

### Task 5: Rede de segurança global + verificação final (Parte 5)

**Files:** Auditar `check_gestao_result` e `check_meta_results` pra garantir `else` seguro. Script/relatório: `scripts/_audit_erros_conversa.py`.

- [ ] **Step 1:** Conferir que todo caminho de erro de gestão/criação termina em mensagem amigável + saída segura (CANCELAR/SIM), nunca criação. Corrigir se faltar `else`.
- [ ] **Step 2:** Guarda de invariante (exit 0/1): (a) nenhuma mensagem de gestão contém "SUBIR DENOVO"; (b) gate do SUBIR_DENOVO existe; (c) classify cobre #613; (d) mapa de status no format_status_response; (e) `pareceComando` no process_gestao_step.
- [ ] **Step 3:** Rodar o guarda → verde. Commit.
- [ ] **Step 4:** Entregar roteiro de smoke test manual pro cliente (número de teste): pausar→trocar no meio; geo com rate limit→SIM de novo; status legível.
