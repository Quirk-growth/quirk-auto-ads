# Quirk Auto Ads v2 — Handoff

**Data:** 2026-05-29
**Status:** Implementado, smoke-tested, **campanha real subida no Meta** ✓

## O que mudou

1. **Estado persistido**: `auto_ads.conversas.estado_json` (JSONB) com etapa, criativo, brief, ultima_tentativa
2. **Agente principal v2**: lê estado e responde com base nele. Não inventa mais "subindo agora"
3. **classify_intent (regex)** substitui o classifier LLM — instantâneo, sem custo de token
4. **validate roda ANTES do agente** em CONFIRMAR/RETRY — cliente recebe 1 msg coerente
5. **Branch de mídia state-aware**: msg condicional baseada em etapa + brief + última tentativa
6. **Auto-retry de infra** (Meta 5xx/timeout): até 2 tentativas com 30s de espera
7. **Comandos do cliente**: CONFIRMAR · RETRY · NOVA CAMPANHA (detectados por regex)

## Validação

| Teste | Resultado |
|---|---|
| Happy path (oi → brief → criativo → CONFIRMAR) | ✓ Campanha `120250407346530210` subiu PAUSED no Meta |
| Falha de dado + RETRY manual | ✓ `tentativas_count: 1 → 2`, fluxo reiniciou |
| Branch de mídia state-aware (4 transições) | ✓ Mensagem correta em cada estado |

## Configuração atual

- `auto_ads.clientes` telefone=5511980838409:
  - `ad_account_id = 2081590208992514` (cartão de crédito — funciona)
  - `page_id = 687786881077238`
- `auto_ads.config.meta_access_token`: token válido pra conta atual
- `auto_ads.campanhas` tem várias entradas dos testes — paused, sem ad real

## Como testar no WhatsApp

Conversa resetada. Manda mensagem pelo 5511980838409:

1. "Oi" → agente coleta brief
2. Manda dados (tipo, valor, região, perfil, verba, período)
3. Manda **foto/vídeo** do imóvel
4. Manda **CONFIRMAR** → backend valida + sobe na Meta + responde com campaign_id real
5. Se falhar por dado → agente explica + pede correção + cita **RETRY**

## Comandos do cliente reconhecidos

- **CONFIRMAR** ("Confirmado", "Confirma", "Sim subir", "Pode subir") → tenta subir
- **RETRY** ("tente de novo", "subir novamente", "tenta de novo") → re-tenta
- **NOVA CAMPANHA** ("começar uma nova", "quero outra campanha") → reseta brief

## Pendências mapeadas (não bloqueiam)

- **Extrator + Advantage+ age**: Meta exige age_max=65 quando usa Advantage+ audience. Hoje gera erro se cliente pediu age_max menor + público com advantage_audience=1. Fix: ajustar prompt do extrator ou normalizar em merge_brief.
- **Auto-retry por mídia**: `decide_acao_media` detecta cenário mas não dispara retry assíncrono ainda — cliente ainda precisa mandar RETRY explícito. (Backlog: Wait async + sub-workflow.)
- **Campanhas órfãs nas contas antigas** (1212196032994372, 3771507593117364) — paused, sem ad. Deletar manualmente no Ads Manager.

## Sub-projeto B (gestão de campanhas) — IMPLEMENTADO

**Data:** 2026-05-30 · **Status:** smoke-tested 4/5 cenários OK

6 verbos disponíveis no WhatsApp:
- **PAUSAR** / **REATIVAR** / **ENCERRAR** — gestão de status (Meta + DB)
- **ALTERAR VERBA** / **ALTERAR PÚBLICO** / **ALTERAR GEO** — edição de dados

**UX**: comando → lista numerada → selecionar (1, 2, 3...) → confirmar SIM/NÃO.
**CANCELAR** em qualquer passo volta ao fluxo normal.
**TTL de 10 min** em sub-flows abandonados (entra em fluxo, esquece, próximo turno trata como nova msg).

**Coleta de novos valores (híbrida)**:
- VERBA: estruturada (só número 10-100)
- PÚBLICO: lista numerada (1-20) OU descrição livre que o extrator parcial mapeia pro Pub Quirk mais próximo
- GEO: estruturada "CIDADE raio_km" OU descrição livre

**Validação smoke**:
| Teste | Resultado |
|---|---|
| PAUSAR (campanha 17: ACTIVE → PAUSED) | ✓ DB + Meta sincronizados |
| ALTERAR_VERBA (R$ 50 → R$ 80/dia) | ✓ json_extrator atualizado |
| CANCELAR (selecao + confirmacao) | ✓ gestao resetado |
| Inputs inválidos (número fora, verba > 100) | ✓ mantém passo, não corrompe estado |

**Audit imutável**: `auto_ads.audit_log` com evento `gestao_*` + antes/depois.
**Política NUNCA DELETE preservada**: ENCERRAR usa `status=ARCHIVED`.

## Próximos sub-projetos

- **C (relatórios)**: status, performance, análise (Meta Insights API) — backlog

Brainstorming separado quando quiser.

## Arquivos-chave

- Spec: `docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md`
- Plan: `docs/superpowers/plans/2026-05-29-quirk-auto-ads-v2-state-aware.md`
- Migration: `sql/004_estado_json.sql`
- Prompt: `prompts/agente_principal.md` (v2)
- Scripts refator: `scripts/v2_*.py`
- Testes smoke: `scripts/test_v2_*.py`
