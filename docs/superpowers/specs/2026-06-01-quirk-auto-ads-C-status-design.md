# Quirk Auto Ads — Sub-projeto C (STATUS MVP) — Design

**Data:** 2026-06-01
**Status:** Aprovado
**Spec pai:** v2 + B

## 1. Objetivo

Verbo único `STATUS`: cliente pede status de uma campanha → bot lista campanhas → escolhe número → bot devolve métricas (Hoje / Ontem / 7d / 30d) numa única mensagem.

Zero LLM no caminho (resposta determinística). Latência ~3-5s.

## 2. UX (2 turnos)

```
Cliente: status
Bot:     Você tem 3 campanhas. Qual?
         1️⃣ Cobertura Ibirapuera (ativa)
         2️⃣ Apto Setor Bueno (paused)
         3️⃣ Lançamento Jardins (ativa)
         Responde com o número ou CANCELAR.
Cliente: 1
Bot:     📊 Cobertura Ibirapuera
         Status no Meta: ACTIVE
         
         Hoje:   234 imp · 89 alcance · 12 msgs · R$ 60 · R$ 5.00/msg
         Ontem:  567 imp · 198 alcance · 28 msgs · R$ 126 · R$ 4.50/msg
         7d:     4.5k imp · 1.6k alcance · 178 msgs · R$ 930 · R$ 5.22/msg
         30d:    18k imp · 6.2k alcance · 720 msgs · R$ 3.6k · R$ 5.00/msg
         
         CTR 7d: 2.4% · CPM 7d: R$ 21
```

## 3. Métricas (Meta Insights API)

Endpoint: `GET /v25.0/{campaign_id}/insights?fields=impressions,reach,spend,cpm,ctr,actions&date_preset=<periodo>`

Períodos: `today`, `yesterday`, `last_7d`, `last_30d`.

| Métrica WhatsApp | Fonte Meta |
|---|---|
| imp | `impressions` |
| alcance | `reach` |
| msgs | `actions[].value` onde `action_type` ∈ `{onsite_conversion.messaging_conversation_started_7d, onsite_conversion.messaging_first_reply}` (somar) |
| gasto (R$) | `spend` |
| R$/msg | `spend / msgs` (calculado) |
| CTR | `ctr` (já vem em %) |
| CPM | `cpm` (em moeda da conta) |

Edge cases:
- Sem entregas no período → "—"
- Sem campanhas → "Você não tem campanhas pra ver status."
- Campanha ARCHIVED/DELETED → filtrada da lista

## 4. Arquitetura

Reusa estrutura de B com mínima adição.

```
classify_intent (regex STATUS)
  ↓
switch_intent (novo output STATUS) → list_campanhas (mesmo node de B, filtro NOT ARCHIVED)
  ↓
init_gestao (verbo=STATUS, passo=selecao)
  ↓
prep_persist + persist_estado_gestao → build_gestao_response → send_gestao_msg
  [cliente manda número]
  ↓
em_gestao_valido (TRUE) → process_gestao_step (passo=selecao → acao=executa)
  ↓
switch_acao_gestao (output 2: EXECUTA)
  ↓
NOVO switch_b_ou_c
  ├─ verbo=STATUS → build_insights_token (Code) → 4 HTTPs Insights paralelas → format_status_response → reset_gestao → send_gestao_msg
  └─ verbo ∈ B → fluxo atual (load_meta_token → execute_gestao_action → ...)
```

### Novos nodes (8)

1. `switch_b_ou_c` (Switch): roteia STATUS pra novo branch
2. `load_meta_token_status` (Postgres): mesma query que load_meta_token, mas dedicado pra branch C
3. `meta_insights_today` (HTTP GET)
4. `meta_insights_yesterday` (HTTP GET)
5. `meta_insights_7d` (HTTP GET)
6. `meta_insights_30d` (HTTP GET)
7. `merge_insights` (Merge node): combina os 4 resultados num único item
8. `format_status_response` (Code): monta mensagem determinística

## 5. Persistência / audit

- `auto_ads.audit_log` ganha evento `status_consultado` (telefone, campanha_id_db, periodos_ok, periodos_falha)
- Sub-flow termina rápido: não persiste estado intermediário longo (TTL gestão de 10min cobre)

## 6. Tratamento de erro

| Cenário | Tratamento |
|---|---|
| Meta retorna 5xx em 1+ chamadas | mostra os períodos OK; nos demais "(erro Meta)" |
| Token expirado | mensagem "Falha de autenticação Meta. Avisa o suporte." |
| Campanha sem entregas no período | mostra "—" no período |
| Sem campanhas | "Você não tem campanhas pra ver status." |

## 7. Testes

- `test_c_status_lista.py` — manda "status", verifica lista numerada
- `test_c_status_completo.py` — cria campanha mock, manda "status" + número, verifica formato resposta

## 8. Pontos de extensão futuros (não MVP)

- RELATORIO: análise narrativa LLM
- COMPARAR: lado-a-lado de 2+ campanhas
- Cache de insights (evita rate limit Meta) — só se ficar problema
- Período custom (data início/fim)
