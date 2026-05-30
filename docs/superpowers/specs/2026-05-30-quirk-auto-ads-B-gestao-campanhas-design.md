# Quirk Auto Ads — Sub-projeto B (gestão de campanhas) — Design

**Data:** 2026-05-30
**Autor:** Renan Real + Claude
**Status:** Aprovado (pré-implementação)
**Spec pai:** [v2 state-aware](./2026-05-29-quirk-auto-ads-v2-state-aware-design.md)
**Sub-projetos relacionados:** A (core state-aware, **DONE**) · C (relatórios, backlog)

---

## 1. Contexto

Sub-projeto A (v2 state-aware) está implementado e validado. Cria campanhas Meta CTWA via WhatsApp ponta-a-ponta. Próxima necessidade: cliente precisa **gerenciar campanhas existentes** sem voltar pro Ads Manager — pausar quando o lead vai bem demais, reativar depois, alterar verba/público/região conforme aprende, encerrar quando o imóvel vendeu.

Hoje não há nenhum verbo de gestão. Cliente que pede "pausa minha campanha" cai no `agente_principal` que responde sobre brief novo — desencontro de UX.

## 2. Objetivos

- **6 verbos de gestão** funcionando no WhatsApp: PAUSAR, REATIVAR, ENCERRAR, ALTERAR_VERBA, ALTERAR_PUBLICO, ALTERAR_GEO
- **Identificação por lista numerada** quando o cliente tem múltiplas campanhas — determinístico, fácil
- **Confirmação obrigatória antes de executar** qualquer ação — política Quirk
- **Histórico imutável** — toda ação grava em `auto_ads.audit_log`, nenhum DELETE
- **Política NUNCA DELETE preservada** — mesmo ENCERRAR usa `status=ARCHIVED` no Meta
- **Cancelar a qualquer momento** durante um sub-flow de gestão volta ao fluxo normal
- **Coleta de novos valores híbrida**: estruturada (verba), lista pré-definida + livre (público/geo)

## 3. Não-objetivos

- Relatórios e análise de performance — sub-projeto C
- Edição de copy do anúncio — fora de escopo (cliente recria criativo)
- Duplicar campanha — fora de escopo
- Bulk actions (pausar todas) — fora de escopo
- Auto-pausa por orçamento ou performance — fora de escopo (futuro D)

## 4. Modelo de estado

### 4.1 Extensão do `estado_json`

Sem migration SQL nova. `estado_json` (JSONB) já existe. Acrescenta sub-objeto `gestao`:

```json
{
  "etapa_atual": "ativa | em_gestao | falhou_dado | ...",
  "criativo": { ... },
  "brief": { ... },
  "ultima_tentativa": { ... },
  "gestao": {
    "verbo": "PAUSAR | REATIVAR | ENCERRAR | ALTERAR_VERBA | ALTERAR_PUBLICO | ALTERAR_GEO",
    "passo": "selecao | coleta_valor | confirmacao",
    "iniciado_em": "2026-05-30T15:00:00Z",
    "lista_candidatas": [
      {"posicao": 1, "campanha_id_db": 10, "campaign_id_meta": "120...", "adset_id_meta": "120...", "nome": "...", "verba_atual": 5000, "publico_atual": "Pub Quirk 4", "geo_atual": "Goiânia 17km"}
    ],
    "selecionada": null,
    "novo_valor": null
  }
}
```

### 4.2 Nova etapa `em_gestao`

Quando `estado.gestao` não é null e `passo` ainda não chegou em confirmação executada, `etapa_atual` vira `em_gestao`. Agente principal **não conduz coleta de brief novo** nessa etapa. Quando a ação completa (sucesso ou falha) OU `CANCELAR` é detectado, `gestao` volta a null e `etapa_atual` volta pro estado anterior (`ativa` se tinha campanha ativa, ou `coletando_info` se foi reset).

### 4.3 TTL do sub-flow

`gestao.iniciado_em` registra timestamp. Se nova msg chega **>10 minutos** após `iniciado_em`, o sub-flow é descartado silenciosamente (estado reseta) e a msg é tratada como nova. Evita cliente preso num fluxo abandonado.

## 5. Detecção de intent

### 5.1 Regras de roteamento

```
load_estado
  ↓
estado.gestao está populado E < 10min de TTL?
  ├─ SIM → process_gestao_step (roteia por passo)
  └─ NÃO → classify_intent (regex tradicional)
```

### 5.2 Novos verbos no `classify_intent`

| Regex | Intent |
|---|---|
| `/^pausar/i`, `/^pausa/i`, `/parar minha campanha/i` | `PAUSAR` |
| `/^reativar/i`, `/^reativa/i`, `/voltar minha campanha/i`, `/^ativar/i` | `REATIVAR` |
| `/^encerrar/i`, `/^arquivar/i`, `/^finalizar campanha/i` | `ENCERRAR` |
| `/alterar verba/i`, `/mudar verba/i`, `/^trocar verba/i` | `ALTERAR_VERBA` |
| `/alterar p[uú]blico/i`, `/mudar p[uú]blico/i` | `ALTERAR_PUBLICO` |
| `/alterar geo/i`, `/mudar (regi[aã]o\|cidade)/i` | `ALTERAR_GEO` |
| `/^cancelar/i`, `/^deixa pra l[áa]/i` | `CANCELAR` (válido só em sub-flow) |

Intents existentes do A (CONFIRMAR, SUBIR_DENOVO, NOVA_CAMPANHA, OUTRO) continuam funcionando.

### 5.3 `process_gestao_step` — roteamento por passo

| Passo atual | Input cliente | Próxima ação |
|---|---|---|
| `selecao` | número (1, 2, ...) | valida range; popula `gestao.selecionada`; verbo destrutivo → `confirmacao`; verbo de alteração → `coleta_valor` |
| `selecao` | "CANCELAR" | reset gestao; volta ao fluxo |
| `coleta_valor` | depende do verbo (ver §6.2) | valida valor; popula `gestao.novo_valor`; vai pra `confirmacao` |
| `coleta_valor` | "CANCELAR" | reset gestao |
| `confirmacao` | "SIM" | executa via Meta API |
| `confirmacao` | "NÃO" / "CANCELAR" | reset gestao |
| qualquer | input inválido | re-envia prompt do passo + lembra opções |

## 6. UX por verbo

### 6.1 Verbos sem coleta (PAUSAR, REATIVAR, ENCERRAR)

```
Cliente: pausar minha campanha
Bot:     Você tem 2 ativas. Qual?
         1️⃣ Cobertura Ibirapuera (R$ 50/dia)
         2️⃣ Apto Setor Bueno (R$ 30/dia)
         Responde com o número ou CANCELAR.
Cliente: 1
Bot:     Confirma pausar Cobertura Ibirapuera? SIM ou NÃO.
Cliente: SIM
Bot:     ✓ Cobertura Ibirapuera pausada.
```

- REATIVAR: lista filtra `status=PAUSED`.
- ENCERRAR: confirmação é mais explícita — "ENCERRAR é permanente — campanha vai pro histórico arquivado, não roda mais. Confirma? SIM ou NÃO."
- Lista inclui só campanhas relevantes ao verbo:
  - PAUSAR → `status IN ('CREATED_PAUSED', 'ACTIVE')` (no Meta seria `ACTIVE`; no DB temos `CREATED_PAUSED` pra paused-since-creation)
  - REATIVAR → `status IN ('PAUSED', 'CREATED_PAUSED')`
  - ENCERRAR → `status NOT IN ('ARCHIVED', 'DELETED')`

### 6.2 Verbos com coleta (ALTERAR_*)

**ALTERAR_VERBA — estruturado (só o número):**
```
Cliente: alterar verba
Bot:     Você tem 2 ativas. Qual?
         1️⃣ Cobertura Ibirapuera (R$ 50/dia)
         2️⃣ Apto Setor Bueno (R$ 30/dia)
Cliente: 1
Bot:     Verba atual de Cobertura Ibirapuera: R$ 50/dia. Manda só o número novo (entre 10 e 100).
Cliente: 80
Bot:     Confirma mudar de R$ 50 → R$ 80/dia? SIM ou NÃO.
Cliente: SIM
Bot:     ✓ Verba atualizada pra R$ 80/dia.
```
Validação no Code node: número inteiro entre 10 e 100; senão, "Verba inválida. Manda número entre 10 e 100, ou CANCELAR."

**ALTERAR_PUBLICO — lista pré-definida + livre:**
```
Cliente: alterar público
Bot:     Lista campanhas → seleção
Bot:     Público atual: Pub Quirk 4. Escolhe um pré-definido ou descreve:
         1️⃣ Pub Quirk 0  (broad)
         2️⃣ Pub Quirk 1  (Brasil 25-60)
         ... até Pub Corretores #3
         Ou descreve em linguagem natural ("investidor 35-50 alto valor").
Cliente: "investidor casado alto valor" (ou "5")
Bot:     Se número entre 1-N → usa template direto da tabela.
         Se texto → roda extrator parcial (only-publico) que devolve nome do Pub Quirk mais próximo.
         "Vai trocar de Pub Quirk 4 → Pub Quirk Invest + Alto valor. Confirma? SIM ou NÃO."
Cliente: SIM
Bot:     ✓ Público atualizado pra Pub Quirk Invest + Alto valor.
```
Edge case: extrator não consegue mapear → "Não consegui identificar o público. Escolhe um número da lista, ou descreve melhor."

**ALTERAR_GEO — estruturado + fallback livre:**
```
Cliente: mudar região
Bot:     Lista → seleção
Bot:     Geo atual: Goiânia, raio 17km. Manda "CIDADE raio_km" (ex: "São Paulo 20") ou descreve.
Cliente: São Paulo 25 (ou "muda pra São Paulo raio 25")
Bot:     Se match no regex `/^(.+)\s+(\d+)$/` → extrai cidade + raio direto.
         Senão, extrator parcial (only-geo) que devolve `{geo_cidade, geo_raio_km}` baseado na tabela de cidades.
         Aplica clamp de raio (17-80) automaticamente, igual no extrator de criação.
         "Confirma trocar de Goiânia 17km → São Paulo 25km? SIM ou NÃO."
Cliente: SIM
Bot:     ✓ Geo atualizado.
```

## 7. Arquitetura

### 7.1 Diagrama do fluxo

```
webhook → switch_type (text) → normalize_phone → select_cliente → if_cadastrado
                                                                        ↓
                                                                  select_conversa
                                                                        ↓
                                                                  load_estado
                                                                        ↓
                                                                  em_gestao_valido? (estado.gestao && TTL<10min)
                                                                  ┌─────┴─────┐
                                                                 sim         não
                                                                  ↓           ↓
                                                          process_gestao_step  classify_intent
                                                                  ↓           ↓
                                                       (passo + input)    switch_intent
                                                                  ↓     ┌────┴────┬────┬────┬───────┬───────┬───────┐
                                                                  ↓  CONFIRMAR SUBIR NOVA OUTRO  PAUSAR REATIVAR ALTERAR_*
                                                                  ↓     ↓       _DENOVO ↓ ...     ↓     ↓        ↓
                                                                  ↓   ...  (fluxo A já implementado)  list_campanhas
                                                                  ↓                                          ↓
                                                                  ↓                                     init_gestao
                                                                  ↓                                          ↓
                                                                  └─────────────────→ build_gestao_response (mensagem do passo)
                                                                                            ↓
                                                                                      persist_estado_gestao (UPDATE estado_json.gestao)
                                                                                            ↓
                                                                                      send_resposta
                                                              [Caso process_gestao_step decida executar:]
                                                                  ↓
                                                            execute_gestao_action (Switch por verbo)
                                                            ├─ PAUSAR/REATIVAR/ENCERRAR → meta_update_status (HTTP POST)
                                                            ├─ ALTERAR_VERBA → meta_update_adset_budget (HTTP POST)
                                                            ├─ ALTERAR_PUBLICO → meta_update_adset_targeting (HTTP POST)
                                                            └─ ALTERAR_GEO → meta_update_adset_targeting (HTTP POST)
                                                                              ↓
                                                                       check_gestao_result (Code: ok / erro_infra / erro_dado)
                                                                              ↓
                                                                       ┌─── ok? ───┐
                                                                      sim         não
                                                                       ↓           ↓
                                                                  update_db_campanha   wait_30s + retry (mesmo padrão A)
                                                                       ↓
                                                                  audit_gestao (INSERT em auto_ads.audit_log)
                                                                       ↓
                                                                  reset_gestao (limpa estado.gestao, etapa volta)
                                                                       ↓
                                                                  build_gestao_confirmation_msg
                                                                       ↓
                                                                  send_resposta
```

### 7.2 Novos componentes

| Componente | Tipo | Descrição |
|---|---|---|
| `em_gestao_valido` | IF | `estado.gestao != null && (now - iniciado_em) < 10min` |
| `process_gestao_step` | Code | Roteador por `passo` — valida input e decide próximo passo |
| `list_campanhas` | Postgres | `SELECT * FROM auto_ads.campanhas WHERE telefone=$1 AND status IN (...) ORDER BY criada_em DESC LIMIT 10` |
| `init_gestao` | Code | Popula `estado.gestao` com lista + verbo + passo='selecao' + timestamp |
| `build_gestao_response` | Code | Mensagem do passo atual (lista numerada, prompt de coleta, prompt de confirmação) |
| `persist_estado_gestao` | Postgres | UPDATE `estado_json` setando `gestao` |
| `execute_gestao_action` | Switch | Roteia por `gestao.verbo` |
| `meta_update_status` | HTTP POST | `POST graph.facebook.com/v25.0/{campaign_id}` com `{status:...}` |
| `meta_update_adset_budget` | HTTP POST | `POST .../v25.0/{adset_id}` com `{daily_budget: <centavos>}` |
| `meta_update_adset_targeting` | HTTP POST | `POST .../v25.0/{adset_id}` com `{targeting: {...}}` (merge feito em Code antes) |
| `check_gestao_result` | Code | Classifica resultado: ok / erro_infra / erro_dado (mesmo padrão check_meta_results) |
| `update_db_campanha` | Postgres | UPDATE `auto_ads.campanhas` (status + json_extrator novo se alteração) |
| `audit_gestao` | Postgres | INSERT `audit_log` com `{verbo, campanha_id, antes, depois, ts}` |
| `reset_gestao` | Postgres | UPDATE `estado_json` setando `gestao = null`, `etapa_atual` apropriada |
| `build_gestao_confirmation_msg` | Code | Mensagem final de sucesso ou falha |

**Nota — extrator parcial:** ALTERAR_PUBLICO e ALTERAR_GEO em modo "livre" reusam o node `extrator` (sub-projeto A) mas com 2 novos Code nodes `build_extrator_partial_publico_body` e `build_extrator_partial_geo_body` que mandam um system prompt enxuto pedindo só o campo alvo. Não cria node Anthropic novo — só novos builders de body.

**Total: 14 nodes novos + 2 builders de body para extrator parcial = 16.**

### 7.3 Endpoints Meta API

| Verbo | Método/URL | Body |
|---|---|---|
| PAUSAR | `POST /v25.0/{campaign_id}` | `{"status":"PAUSED"}` |
| REATIVAR | `POST /v25.0/{campaign_id}` | `{"status":"ACTIVE"}` |
| ENCERRAR | `POST /v25.0/{campaign_id}` | `{"status":"ARCHIVED"}` |
| ALTERAR_VERBA | `POST /v25.0/{adset_id}` | `{"daily_budget": <novo_em_centavos>}` |
| ALTERAR_PUBLICO | `POST /v25.0/{adset_id}` | `{"targeting": <targeting completo com novo público>}` |
| ALTERAR_GEO | `POST /v25.0/{adset_id}` | `{"targeting": <targeting completo com novo geo>}` |

**Atenção:** `targeting` no Meta é substituído por inteiro. Backend precisa ler o `targeting_meta` salvo em `auto_ads.campanhas.json_extrator`, modificar só o campo certo (`flexible_spec` pra público, `geo_locations` pra geo), re-enviar o objeto completo.

## 8. Lifecycle de status

```
                            ┌─────────────────┐
                            │                 ▼
       CREATED_PAUSED ──→ PAUSED ←─→ ACTIVE
              │             │           │
              └─→ ARCHIVED ←─┴───────────┘
                       │
                       ▼
              (irreversível)
```

`CREATED_PAUSED` é o status default de criação (sub-projeto A). Em qualquer ponto do ciclo, cliente pode REATIVAR (vira ACTIVE) ou PAUSAR (vira PAUSED) ou ENCERRAR (vira ARCHIVED). ARCHIVED é terminal — não tem REATIVAR.

`auto_ads.campanhas.status` reflete o status atual. Para auditoria, `audit_log` guarda histórico de transições.

## 9. Persistência e audit

### 9.1 `auto_ads.campanhas` — UPDATE controlado

Após `execute_gestao_action`, `update_db_campanha` faz UPDATE controlado:

```sql
UPDATE auto_ads.campanhas
SET status = $1,                          -- novo status (se PAUSAR/REATIVAR/ENCERRAR)
    json_extrator = $2,                   -- novo json_extrator (se ALTERAR_*)
    ultima_alteracao = NOW()              -- nova coluna timestamp
WHERE id = $3
```

Nova coluna `ultima_alteracao TIMESTAMPTZ` em `auto_ads.campanhas` (migration 005, default = `criada_em`).

### 9.2 `auto_ads.audit_log` — histórico imutável

Toda ação grava:

```json
{
  "evento": "gestao_pausar | gestao_reativar | gestao_encerrar | gestao_alterar_verba | gestao_alterar_publico | gestao_alterar_geo",
  "telefone": "5511...",
  "detalhes": {
    "campanha_id_db": 10,
    "campaign_id_meta": "120...",
    "antes": { "status": "ACTIVE", "verba_diaria": 50 },
    "depois": { "status": "PAUSED" },
    "meta_response_id": "...",
    "tentativas_count": 1
  },
  "ts": "2026-05-30T..."
}
```

## 10. Tratamento de erro

Mesmo padrão de sub-projeto A:

| Erro Meta | Classe | Ação |
|---|---|---|
| 5xx / timeout / transient | `infra` | auto-retry: wait 30s, count++, máx 2x |
| 4xx com `error_user_msg` | `dado` | manda msg pro cliente com motivo + opção de tentar de novo |
| Campanha não encontrada / status inválido | `dado` | "Essa campanha não existe ou já foi alterada." |

Em `falhou_dado` durante gestão, `estado.gestao` NÃO é resetado automaticamente — cliente pode mandar `SUBIR DENOVO` pra re-tentar a mesma ação OU `CANCELAR` pra sair.

## 11. Migração e backward compat

1. **Migration SQL 005** — adiciona `ultima_alteracao` em `auto_ads.campanhas`. Default = `criada_em` (preserva linhas existentes).
2. **`estado_json.gestao`** — campo novo opcional. Linhas existentes herdam `null` automaticamente.
3. **Refactor n8n via script Python** seguindo padrão `b_*.py` (nova prefixo pra distinguir do `v2_*.py` de A).
4. **`classify_intent` já é extensível** — só adicionar regex novos.
5. **`switch_intent` ganha outputs novos** — 1 por verbo de gestão. Comporta os existentes.
6. **Sem breaking changes externos** — webhook URL igual, UAZAPI igual, ad_account_id igual.

## 12. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| Cliente seleciona número inválido (0, 99, "abc") | Alta | Baixo | `process_gestao_step` valida range, responde "Número inválido. Manda entre 1 e N ou CANCELAR." |
| Cliente abandona o fluxo (some) | Média | Médio | TTL 10min em `gestao.iniciado_em`. Próxima msg após TTL trata como nova |
| Cliente digita "cancelar" mid-flow | Alta | Baixo | Detectado em qualquer passo, reseta `gestao` |
| Meta retorna 5xx | Baixa | Médio | Auto-retry 2x com wait 30s |
| Cliente edita campanha que já foi pausada por outro motivo (manual no Ads Manager) | Baixa | Médio | Re-fetch status atual antes da UPDATE; se mudou, aviso "essa campanha já está pausada" |
| ALTERAR_PUBLICO com texto que extrator não mapeia | Média | Baixo | Falha com msg "Não consegui identificar. Escolhe número da lista, ou descreve melhor" |
| 2 alterações simultâneas (race) | Baixa | Médio | Aceitável: última vence (Meta retorna estado consistente). Auditoria registra ambas |
| Cliente tem 50+ campanhas (lista enorme) | Baixa | Baixo | `LIMIT 10` na list_campanhas. Versão 2 adiciona paginação |

## 13. Testes / validação

### 13.1 Pré-deploy (simulações)

- `test_b_pausar.py` — cria 2 campanhas mock, manda "pausar", "1", "SIM", verifica status no DB
- `test_b_reativar.py` — cria 1 paused, manda "reativar", verifica status
- `test_b_encerrar.py` — verifica ARCHIVED + audit_log
- `test_b_alterar_verba.py` — manda "alterar verba", "1", "80", "SIM", verifica daily_budget no Meta + DB
- `test_b_alterar_publico_estruturado.py` — manda número de Pub Quirk
- `test_b_alterar_publico_livre.py` — manda texto natural, valida extrator parcial
- `test_b_alterar_geo.py` — manda "São Paulo 25" e variação livre
- `test_b_cancelar.py` — entra em fluxo, cancela em cada passo
- `test_b_ttl.py` — entra em fluxo, espera 11min mock, manda msg, verifica reset
- `test_b_input_invalido.py` — input fora de range, número fora de lista, valor fora de faixa

### 13.2 Pós-deploy (monitoramento)

- `auto_ads.audit_log` — toda gestão deve ter evento `gestao_*` correspondente
- Quando `etapa_atual=em_gestao`, garantir que TTL é respeitado
- Latência: gestão (sem retry) ≤ 30s

## 14. Pontos de extensão pro sub-projeto C

- **`auto_ads.campanhas`** com status atualizado em tempo real → fonte única de verdade pra "minhas campanhas ativas"
- **`audit_log`** com histórico de mudanças → input pra "campanha X foi pausada em Y, reativada em Z, ..."
- **`estado.gestao`** padrão genérico — C pode reusar pra fluxos similares (selecionar campanha pra ver relatório)
- **Verbo STATUS** em C pode reusar `list_campanhas` + apenas mudar action pra read-only (Meta Insights API)

## 15. Próximos passos

1. Renan aprova esta spec
2. Invocar `writing-plans` pra plano detalhado
3. Implementar (estimativa: 5-7 horas — SQL + 14 nodes + 6 testes)
4. Smoke test ponta-a-ponta
5. Renan testa no WhatsApp real
6. Backlog: brainstorming sub-projeto C (relatórios)
