# Quirk Auto Ads — v2 (state-aware) — Design

**Data:** 2026-05-29
**Autor:** Renan Real + Claude
**Status:** Aprovado (pré-implementação)
**Sub-projetos relacionados (backlog):** B (gestão de campanhas) · C (relatórios e análise)

---

## 1. Contexto

V1 do workflow Quirk Auto Ads ([spec](../../2026-05-28-quirk-auto-ads-n8n-migration-design.md), [plan](../../2026-05-28-quirk-auto-ads-n8n-implementation-plan.md)) está operacional em n8n self-hosted (`https://n8n.quirkgrowth.online`), com integração Anthropic + Postgres (Supabase `auto_ads` schema) + UAZAPI + Meta Marketing API v25.

Testes reais expuseram 3 bugs entrelaçados que comprometem a UX e a integridade do fluxo:

1. **Agente mente sobre execução.** Diz "Campanha confirmada e subindo! 🚀" antes do backend rodar validação. Quando o validate barra (faltou criativo, raio inválido, etc.), o cliente já recebeu confirmação falsa.
2. **Mensagens contraditórias.** O `send_falha_validacao` (adicionado como UX patch) compete com a resposta otimista do agente. Cliente recebe 2 msgs conflitantes.
3. **Branch de mídia desconectado.** Foto chega num branch paralelo, escreve em `auto_ads.conversas.criativo_url`, mas o agente principal não tem awareness disso. Não há sinal de "criativo recebido" pro próximo turno, nem máquina de estado.

Causa-raiz: o sistema confunde **intenção do agente** com **estado do backend**. O agente fala como autônomo, mas quem executa é o n8n.

## 2. Objetivos

- **Coerência:** cliente recebe **uma única mensagem** por evento, sempre alinhada com o que o backend realmente fez.
- **State-awareness:** o agente principal lê o estado real da campanha (etapa, criativo, última tentativa) antes de responder.
- **Fluidez da mídia:** branch de mídia integrado ao state machine — confirma recepção contextualmente (sabe se brief está pronto, se acabou de falhar, etc.) e dispara retry automático em casos apropriados.
- **Retry inteligente:** auto-retry em erros de infra (rate limit, 5xx, timeout); cliente comanda retry em erros de dado (criativo inválido, raio errado, pagamento).
- **Arquitetura extensível:** preparado pros sub-projetos B (gestão) e C (relatórios) sem refatoração estrutural.

## 2.1 Políticas invioláveis

- **NUNCA DELETE de campanhas no Meta.** Apenas `status=PAUSED` ou `status=ARCHIVED`. Histórico em `auto_ads.campanhas` é imutável (somente INSERT + UPDATE de status). Razão: auditoria, recuperação, evita perda de dados de performance históricos.
- **NUNCA Multi-Advertiser Ads.** Todo creative e todo ad criado pela automação inclui `degrees_of_freedom_spec.creative_features_spec.multi_advertiser_ads.enroll_status = "OPT_OUT"`. Razão: Quirk não autoriza seus criativos a serem mesclados com outros anunciantes.
- **NUNCA Standard Enhancements automáticos.** Inclui `standard_enhancements.enroll_status = "OPT_OUT"`. Razão: Quirk controla manualmente a qualidade do criativo.
- **NUNCA Advantage+ Audiences.** `targeting_meta.targeting_automation.advantage_audience` é forçado a `0` em `merge_brief`, independente do que o extrator gere. Razão: Quirk usa segmentação manual cirúrgica.

## 3. Não-objetivos

- Gestão de campanhas existentes (pausar, reativar, alterar) — escopo do sub-projeto B.
- Relatórios e análise de performance — escopo do sub-projeto C.
- Multi-cliente em produção (mai/2026) — fora deste sprint.
- Refatoração de `auto_ads.clientes` (telefone, ad_account_id, page_id) — já está OK.

## 4. Modelo de estado

### 4.1 Nova coluna `estado_json` em `auto_ads.conversas`

```sql
ALTER TABLE auto_ads.conversas
ADD COLUMN estado_json JSONB DEFAULT '{
  "etapa_atual": "coletando_info",
  "criativo": {"recebido": false, "url": null, "mimetype": null, "recebido_em": null},
  "brief": {},
  "ultima_tentativa": null
}'::jsonb;
```

### 4.2 Estrutura do `estado_json`

```json
{
  "etapa_atual": "coletando_info | aguardando_criativo | pronta_pra_subir | subindo | ativa | falhou_dado | falhou_infra",
  "criativo": {
    "recebido": false,
    "url": null,
    "mimetype": null,
    "recebido_em": null
  },
  "brief": {
    "objetivo": null,
    "faixa_valor": null,
    "trilho_escolhido": null,
    "publico_escolhido": null,
    "campanha": {"nome": null, "objetivo_meta": null, "verba_diaria": null, "periodo": null},
    "conjunto": {"idade_min": null, "idade_max": null, "geo": null, "geo_cidade": null, "geo_raio_km": null, "limitar": null},
    "anuncio": {"tipo_imovel": null, "valor_imovel": null, "copy": null},
    "targeting_meta": null
  },
  "ultima_tentativa": {
    "timestamp": "2026-05-29T15:00:00Z",
    "resultado": "ok | erro_dado | erro_infra",
    "motivo": "criativo_url vazio | raio < 17km | pagamento ausente | rate limit | etc",
    "campaign_id": "120246...",
    "adset_id": null,
    "creative_id": null,
    "ad_id": null,
    "tentativas_count": 0
  }
}
```

### 4.3 Transições válidas

| De | Para | Trigger |
|---|---|---|
| `coletando_info` | `aguardando_criativo` | `update_estado_etapa` detecta brief mínimo coletado. Campos obrigatórios pra essa transição: `nome`, `objetivo`, `faixa_valor`, `geo`, `verba_diaria`. Detecção feita por código (Code node), não pelo agente. |
| `aguardando_criativo` | `pronta_pra_subir` | Branch de mídia recebe criativo |
| `coletando_info` | `pronta_pra_subir` | Cliente envia mídia antes do brief completar (loop volta a `coletando_info` se brief ainda incompleto) |
| `pronta_pra_subir` | `subindo` | Cliente envia `CONFIRMAR` (detectado por `classify_intent`) |
| `subindo` | `ativa` | `check_meta_results.ok == true` (4 nodes Meta OK) |
| `subindo` | `falhou_dado` | Erro de dado (criativo, targeting, pagamento) |
| `subindo` | `falhou_infra` | Erro de infra (rate limit, 5xx, timeout) → auto-retry até 2x → vira `subindo` de novo ou `falhou_dado` |
| `falhou_dado` | `pronta_pra_subir` | Cliente envia `RETRY` (após corrigir o problema) |
| `falhou_dado` | `pronta_pra_subir` | Cliente envia novo criativo via branch de mídia (sobrescreve auto-retry quando motivo era criativo) |
| `ativa` | `coletando_info` | Cliente envia `NOVA_CAMPANHA` |

## 5. Arquitetura

### 5.1 Fluxo principal (texto)

```
webhook
  └─ switch_type ──text──→ normalize_phone → select_cliente → if_cadastrado
                                                                  ├─ não → send_nao_cadastrado
                                                                  └─ sim → select_conversa
                                                                              ↓
                                                                       load_estado (Code: lê estado_json)
                                                                              ↓
                                                                       classify_intent (Code: regex)
                                                                              ↓
                                          ┌───────────────────────────┬───────┴───────────┬────────────────────┐
                                       CONFIRMAR                    RETRY              NOVA              OUTRO (default)
                                          ↓                            ↓                ↓                    ↓
                                     (segue extrator)              reset_etapa     reset_estado_completo  build_agente_body_v2
                                          ↓                            ↓                ↓                    ↓
                                          └─────────┬───────────────────┘                ↓             agente_principal_v2 (chat)
                                                    ↓                                    ↓                    ↓
                                         build_extrator_body                   send_resposta              merge_brief (Code)
                                                    ↓                          ("começamos do zero")          ↓
                                                extrator                                ↓             update_estado_etapa
                                                    ↓                                  ─┘             (Code: atualiza brief + etapa)
                                             parse_extrator                                                    ↓
                                                    ↓                                                   send_resposta
                                          merge_brief (atualiza
                                          estado_json.brief
                                          + targeting_meta normalizado)
                                                    ↓
                                              validate_v2
                                                    ↓
                                          ┌──── ok? ────┐
                                       sim              não
                                          ↓               ↓
                                 update_estado('subindo')  classify_erro_dado
                                          ↓               ↓
                                 load_meta_token       update_estado('falhou_dado')
                                          ↓               ↓
                                 meta_d1_campaign      build_agente_body_v2 (com erro de dado no contexto)
                                          ↓               ↓
                                 meta_d2_adset         agente_principal_v2
                                          ↓               ↓
                                 meta_d3_creative      send_resposta
                                          ↓
                                 meta_d4_ad
                                          ↓
                                 check_meta_results
                                          ↓
                                 ┌──── ok? ────┐
                              sim              não (infra OR dado)
                                 ↓               ↓
                        update_estado('ativa')  classify_erro_infra_ou_dado
                                 ↓               ↓
                        insert_campanha    ┌─ infra & tentativas<2 ─┐
                                 ↓         ↓                        ↓
                        audit_campanha     wait_30s             update_estado('falhou_dado')
                                 ↓         ↓                        ↓
                        build_agente_body_v2 retry_meta_calls    build_agente_body_v2 (com erro)
                        (com sucesso)      (loop back to d1-d4)     ↓
                                 ↓                              agente_principal_v2
                        agente_principal_v2                         ↓
                                 ↓                              send_resposta
                        send_resposta
```

### 5.2 Branch de mídia (state-aware)

```
webhook(media)
  └─ media_normalize_phone → media_select_cliente → media_select_conversa
                                                            ↓
                                                  load_estado_media (Code)
                                                            ↓
                                                  media_download (UAZAPI)
                                                            ↓
                                                  media_update_estado (Code + UPSERT)
                                                  ├─ estado_json.criativo = {recebido:true, url, mimetype, recebido_em}
                                                  ├─ historico += "|||TURN|||[SISTEMA: criativo recebido em <ts>: <url>]"
                                                  └─ transição de etapa conforme tabela 4.3
                                                            ↓
                                                  decide_acao_media (Code)
                                                  ├─ se etapa anterior era falhou_dado(criativo) → disparar RETRY automático
                                                  └─ caso padrão → mandar msg condicional (build_media_response)
                                                            ↓
                                                  build_media_response (Code: msg condicional)
                                                            ↓
                                                  media_send_resposta (UAZAPI send_text)
```

**Mensagens condicionais do `build_media_response`:**

| Estado antes | Brief completo? | Mensagem enviada |
|---|---|---|
| `coletando_info` | não | "Recebi seu criativo ✓ — ainda preciso de: <faltantes>. Me manda esses dados pra fechar." |
| `coletando_info` | sim → vira `pronta_pra_subir` | "Recebi seu criativo ✓ — tudo pronto. Manda **CONFIRMAR** quando quiser subir." |
| `aguardando_criativo` | (sempre sim) | "Recebi seu criativo ✓ — tudo pronto. Manda **CONFIRMAR** quando quiser subir." |
| `falhou_dado` (motivo: criativo) | sim | "Recebi o novo criativo ✓ — rodando RETRY automático agora..." (dispara retry async) |
| `falhou_dado` (motivo: outro) | sim | "Recebi seu criativo ✓ — mas a última tentativa falhou por **<motivo>**. Corrige isso e manda **RETRY**." |
| `ativa` | — | "Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer **NOVA** campanha?" |

### 5.3 Agente principal v2

System prompt do `agente_principal` ganha bloco de contexto explícito:

```
[ESTADO DA CONVERSA — leia ANTES de responder]
Etapa atual: {{estado.etapa_atual}}
Criativo recebido: {{estado.criativo.recebido ? "sim (" + estado.criativo.url + ")" : "não"}}
Brief coletado: {{lista_campos_preenchidos}}
Brief faltante: {{lista_campos_obrigatorios_faltantes}}
Última tentativa: {{estado.ultima_tentativa ? "<resultado>: <motivo>" : "nenhuma"}}
Tentativas count: {{estado.ultima_tentativa.tentativas_count || 0}}

[CONTEXTO DA TENTATIVA ATUAL — se houver]
{{se etapa = ativa: "Campanha subiu: campaign_id=<id> (PAUSED no Meta)"}}
{{se etapa = falhou_dado: "Última subida falhou por: <motivo>. Cliente precisa: <ação>."}}
{{se etapa = subindo: "Campanha sendo processada agora — NÃO confirme sucesso ainda."}}

[REGRA CRÍTICA DE INTEGRIDADE]
NUNCA prometa "subindo agora", "campanha criada", "tá no ar" — quem decide isso é o backend.
Responda APENAS com base no estado acima.

- etapa = coletando_info → conduza coleta (faltam: <campos>)
- etapa = aguardando_criativo → peça o criativo (foto/vídeo)
- etapa = pronta_pra_subir → peça confirmação ("Tudo pronto. Manda CONFIRMAR pra subir.")
- etapa = subindo → "Validando e subindo, te aviso assim que estiver no ar."
- etapa = ativa → confirme com campaign_id real
- etapa = falhou_dado → explique motivo + peça correção + cite RETRY como comando
- etapa = falhou_infra → "Tive falha técnica, tentando de novo automaticamente."

[FIM ESTADO]
```

### 5.4 Detecção de intent (substitui o classifier LLM)

Novo node `classify_intent` (Code) substitui o `classifier` (Anthropic). Roda regex no texto da msg do cliente:

| Regex | Intent |
|---|---|
| `/^confirmar?$/i` ou `/^confirmado$/i` ou `/^sim,?\s*subir$/i` | `CONFIRMAR` |
| `/^retry$/i` ou `/tente?.*denovo/i` ou `/subir.*novamente/i` ou `/tenta.*de\s*novo/i` | `RETRY` |
| `/^nova\s*campanha$/i` ou `/^começar.*nova$/i` ou `/quero.*outra.*campanha/i` | `NOVA_CAMPANHA` |
| (default) | `OUTRO` |

**Por que regex e não LLM:** instantâneo (0ms), determinístico, sem custo de token, fácil de auditar. A v1 usava LLM porque a regra dependia de inspecionar a resposta do agente — na v2 a intenção vem do cliente diretamente.

**Edge case:** se o cliente escreve "CONFIRMADO" mas o `estado.etapa_atual` é `coletando_info` (ou seja, confirmou prematuramente), o fluxo vai pra branch `CONFIRMAR` → `validate_v2` vai barrar → agente_principal_v2 explica o que falta. Confirmação prematura não destrói o estado.

### 5.5 Classificação de erro Meta

`check_meta_results` (refatorado) detecta tipo do erro:

| Sinal | Classe | Ação backend |
|---|---|---|
| HTTP 5xx, timeout, `is_transient: true` | `infra` | Auto-retry: wait 30s, count++, máx 2x. Se persistir → `falhou_dado` (degradado) |
| `error_subcode: 1487110` (raio inválido) | `dado` | `falhou_dado`, motivo: "raio geográfico inválido" |
| `error_subcode: 3858258` (imagem inválida) | `dado` | `falhou_dado`, motivo: "imagem rejeitada pela Meta" |
| `error_user_msg` contém "pagamento" / "billing" | `dado` | `falhou_dado`, motivo: "conta sem método de pagamento ativo" |
| Outros 4xx | `dado` | `falhou_dado`, motivo: extrai `error_user_msg` cru |

### 5.6 Retry mechanism

**Auto-retry (infra):**
- Implementado dentro do branch `subindo`. Após `check_meta_results.erro_classe = "infra"` e `tentativas_count < 2`:
  - `wait_30s` (n8n Wait node, 30 segundos)
  - Loop reinicia **do passo que falhou** (d2, d3 ou d4), preservando IDs criados nos passos anteriores. `check_meta_results` já distingue cada step e expõe `failed_step`.
  - `tentativas_count++` em cada loop, persistido em `estado_json.ultima_tentativa.tentativas_count`
- Se atingir 2 tentativas e ainda infra → desce pra `falhou_dado` (degradação, evita loop infinito; cliente decide se faz retry manual)

**Retry manual (dado):**
- Cliente manda `RETRY` (ou variação reconhecida pelo regex em 5.4)
- `classify_intent` roteia pra branch RETRY
- Branch RETRY: lê `estado_json.brief` (que já tem o último JSON extraído), pula `extrator`, vai direto pra `validate_v2` → meta_dN
- Se cliente mandou novo criativo via branch de mídia depois de uma falha por criativo → `decide_acao_media` dispara RETRY automaticamente (sem o cliente precisar digitar)

## 6. Componentes novos / alterados

| Componente | Tipo | Status | Descrição |
|---|---|---|---|
| `auto_ads.conversas.estado_json` | Coluna SQL | Novo | JSONB com state machine |
| `load_estado` | Code node | Novo | Lê estado_json no início do fluxo |
| `classify_intent` | Code node | Novo | Regex em msg.text → CONFIRMAR/RETRY/NOVA/OUTRO |
| `merge_brief` | Code node | Novo | Mescla json_extrator no estado_json.brief |
| `update_estado_etapa` | Code node | Novo | Atualiza etapa baseado no resultado de cada step |
| `validate_v2` | Code node | Refator | Mesma lógica do validate v1 mas lê de estado_json.brief |
| `check_meta_results` (v2) | Code node | Refator | Classifica erro como infra vs dado |
| `wait_30s` | n8n Wait | Novo | 30s sleep antes de retry |
| `decide_acao_media` | Code node | Novo | No branch de mídia: decide entre msg simples vs auto-retry |
| `build_media_response` | Code node | Refator | Msg condicional baseada em estado |
| `agente_principal_v2` (prompt) | Anthropic prompt | Refator | Inclui bloco [ESTADO] + regra anti-mentira |
| `classifier` (LLM) | Anthropic | **Aposentado** | Substituído por `classify_intent` (regex) |
| `send_falha_validacao` | UAZAPI HTTP | **Aposentado** | Mensagem agora vem do agente_principal_v2 |
| `audit_validacao_falhou` | Postgres | Mantido | Continua registrando em audit_log |

## 7. Migração e backward compat

1. **Adicionar coluna `estado_json`** com default em `auto_ads.conversas`. Linhas existentes herdam `etapa_atual = coletando_info` automaticamente.
2. **Refactor n8n via script Python** (estilo dos `fix_*.py` existentes). Workflow continua o mesmo ID, só substitui nodes e connections.
3. **Aposentar `classifier`** (LLM) — deletar node. `classify_intent` (Code) ocupa o lugar.
4. **Aposentar `send_falha_validacao`** — deletar node. Agente_principal_v2 absorve a função.
5. **Prompt `agente_principal.md`** — adicionar bloco [ESTADO], adicionar regra anti-mentira, manter o restante.
6. **Branch de mídia** — adicionar `load_estado_media`, `decide_acao_media`, refatorar `build_media_response`, refatorar `media_upsert_criativo` pra escrever em `estado_json`.

Não há breaking changes externos — webhook URL continua o mesmo, payload UAZAPI o mesmo, credentials as mesmas.

## 8. Pontos de extensão pros sub-projetos B e C

- **`classify_intent`** é o ponto único de detecção de verbos. Sub-projeto B adiciona PAUSAR, REATIVAR, ALTERAR_VERBA, ALTERAR_PUBLICO, ALTERAR_GEO, ENCERRAR. Sub-projeto C adiciona RELATORIO, STATUS, COMPARAR. Cada verbo novo = 1 linha de regex + 1 branch novo no switch.
- **`estado_json.campanha_em_foco`** (a adicionar quando B começar) — guarda o último `campaign_id` ativo do cliente pra resolver "pausa minha campanha" sem ambiguidade.
- **`auto_ads.campanhas`** schema já suporta query "ativas do cliente X" (telefone + status). Sub-projetos B e C consomem direto.
- **Agente principal v2** com bloco [ESTADO] é genérico — B e C estendem o bloco com mais campos sem refatorar o prompt-base.

## 9. Riscos e mitigações

| Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|
| `classify_intent` falha em variações naturais do cliente (ex: "manda CONFIRMADO pra mim") | Média | Médio | Regex robusta com prefixo/sufixo opcional; fallback pra agente entender |
| Loop infinito em auto-retry (Meta nunca para de retornar 5xx) | Baixa | Alto | Limite hard de 2 tentativas; após isso vira `falhou_dado` |
| Race condition: mídia e texto chegam simultâneos | Baixa | Médio | n8n executa execuções em paralelo; estado_json é updated por execução isolada. Última gravação vence (Last Writer Wins). Aceitável pro caso de uso. |
| Cliente envia "CONFIRMADO" sem ter completado brief → loop de validate barrar | Média | Baixo | Agente v2 lê estado e explica o que falta — não loop infinito porque cliente recebe feedback acionável |
| Cliente manda mídia que não é foto/vídeo (PDF, áudio) | Média | Baixo | UAZAPI já filtra `message.type=media`; `mimetype` checado antes de salvar. Outros tipos → ignorar com log. |
| Quebra do prompt do agente v2 → respostas inconsistentes | Alta | Alto | Prompt versionado em git; testes simulados antes do deploy; rollback via git revert |

## 10. Testes / validação

Pré-deploy:
- Simulação local: 6 cenários cobrindo todas as transições (happy path, brief incompleto, criativo só, RETRY após falha de dado, NOVA após ativa, auto-retry de infra)
- Smoke test em ambiente real (Renan no WhatsApp) com 1 brief, 1 criativo, 1 CONFIRMAR

Pós-deploy:
- Monitorar `auto_ads.audit_log` — 100% das execuções de CONFIRMAR devem ter evento `campanha_criada` ou `campanha_parcial` correspondente
- Quando `etapa_atual = falhou_dado`, verificar que a msg do agente cita o motivo real
- Latência: `classify_intent` ≤ 5ms; fluxo CONFIRMAR completo ≤ 60s (4 chamadas Meta + 2 LLM)

## 11. Próximos passos

1. Renan aprova esta spec
2. Invocar `writing-plans` pra produzir o plano de implementação detalhado
3. Implementar (estimativa: 4-6 horas de trabalho — refator de prompt + scripts Python pro n8n + migration SQL)
4. Smoke test com Renan no WhatsApp
5. Backlog: brainstorming dos sub-projetos B e C
