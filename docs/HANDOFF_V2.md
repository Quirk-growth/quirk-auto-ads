# Quirk Auto Ads — v2 (state-aware) — Handoff

**Data:** 2026-05-29
**Status:** Implementado, smoke-testado (3 cenários), pronto pra teste real

---

## O que mudou

1. **Estado persistido em `auto_ads.conversas.estado_json` (JSONB)** com:
   - `etapa_atual` (coletando_info / aguardando_criativo / pronta_pra_subir / subindo / ativa / falhou_dado / falhou_infra)
   - `criativo` (recebido, url, mimetype, recebido_em)
   - `brief` (mesma shape do extrator)
   - `ultima_tentativa` (resultado, motivo, IDs Meta, tentativas_count)

2. **Agente principal v2 com bloco [ESTADO]** no system prompt. Regra anti-mentira explícita: nunca promete "subindo" — só responde com base no estado real.

3. **classify_intent (regex) substitui classifier (LLM)** — instantâneo, sem custo de token, sem dependência de resposta do agente.

4. **Validate roda ANTES do agente** em CONFIRMAR/RETRY. Cliente recebe **uma mensagem coerente** em vez de 2 contraditórias.

5. **Branch de mídia state-aware** — confirma recepção com mensagem condicional baseada no estado anterior + brief completude + última tentativa.

6. **Auto-retry de infra** (Meta 5xx/timeout/is_transient) — até 2 tentativas com 30s de espera.

7. **Comandos novos do cliente**:
   - `CONFIRMAR` (também: "Confirmado", "Confirma", "pode subir")
   - `RETRY` (também: "tente de novo", "subir novamente")
   - `NOVA CAMPANHA` (também: "começar uma nova", "quero outra campanha")

---

## Como testar

Manda mensagem do seu WhatsApp (`5511980838409`):

1. "Oi" → agente coleta brief
2. Manda os dados (tipo, valor, região, perfil, verba, período)
3. Manda **foto/vídeo** do imóvel → bot confirma criativo + diz "manda CONFIRMAR pra subir"
4. Manda **CONFIRMAR** → backend valida, sobe na Meta, responde com campaign_id real

Se algo falhar:
- **Por dado** (raio, imagem, pagamento) → agente explica + pede correção + cita RETRY
- **Por infra** (rate limit, 5xx) → auto-retry silencioso

---

## Smoke tests rodados

- ✓ Happy path (msg → brief → criativo → CONFIRMAR → estado terminal)
- ✓ Falha de dado + RETRY manual (tentativas_count 1 → 2)
- ✓ 4 transições do branch de mídia

---

## Conhecido / fora do escopo

- **Conta Meta `1212196032994372` está sem método de pagamento** — todos os testes terminaram em `falhou_dado` por causa disso. Resolve isso na BM e o ciclo fica completo (`ativa`).
- **Sub-projetos B (gestão) e C (relatórios) ficaram em backlog** — quando quiser, brainstormar cada um separadamente.

---

## Arquivos-chave

- **Spec**: `docs/superpowers/specs/2026-05-29-quirk-auto-ads-v2-state-aware-design.md`
- **Plano**: `docs/superpowers/plans/2026-05-29-quirk-auto-ads-v2-state-aware.md`
- **Migration**: `sql/004_estado_json.sql`
- **Prompt v2**: `prompts/agente_principal.md`
- **Backup v1**: `prompts/agente_principal_v1_legacy.md`
- **Scripts**: `scripts/v2_*.py` (refator), `scripts/test_v2_*.py` (smoke)
