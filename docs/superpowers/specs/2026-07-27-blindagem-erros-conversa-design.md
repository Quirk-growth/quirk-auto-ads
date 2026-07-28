# Blindagem de erros e fluidez da conversa — Auto Ads — design

**Data:** 2026-07-27
**Status:** Aprovado (design)
**Workflow:** principal `fBUin1UPt5xJEp6g`

## Problema

Testes com os comandos novos de gestão expuseram 4 bugs, todos confirmados em execução real:

1. **"SUBIR DENOVO" cria campanha por engano (crítico, gasta dinheiro).**
   A mensagem de erro de uma ação de gestão (geo/verba/pausar) instrui *"Manda SUBIR DENOVO pra tentar novamente"*. Mas o intent `SUBIR_DENOVO` está ligado ao fluxo de **criar campanha do zero**. No exec 22942 o estado tinha `etapa_atual: 'ativa'` + um `brief` antigo → o "SUBIR DENOVO" reconstruiu e subiu uma campanha **já ativa**, duplicando.

2. **Erro transitório do Meta vira erro fatal (exec 22937).**
   A alteração de geo falhou com `(#613) Calls to this api have exceeded the rate limit` — rate limit, transitório. O classificador (`check_gestao_result.classify`) só marca como `infra` mensagens com `status code 5xx`/`timeout`/`ECONN`. Esse veio como HTTP `400`, foi classificado como `dado` e a mensagem empurrou pro "SUBIR DENOVO" fatal.

3. **Estado travado (exec 22877).**
   Esperando o número da campanha (`passo: 'selecao'`), qualquer mensagem que não seja um número válido vira *"Número inválido"* — inclusive um comando novo ("Pausar"). O `em_gestao_valido` já expira o estado em 10 min, mas **dentro** da janela não há como trocar de comando.

4. **Status cru no relatório (`format_status_response`).**
   Mostra `Status no Meta: CREATED_ACTIVE` em vez de dizer se está no ar ou pausada.

## Objetivo

Blindar o produto pra que nenhum erro do Meta ou mensagem fora de ordem leve a ação errada (nunca criar/duplicar campanha por engano), e pra que a conversa siga fluida quando o cliente muda de ideia no meio de um fluxo. Toda falha vira mensagem clara + saída segura.

## Decisões (definidas com o cliente)

- **Estado travado:** *sempre perguntar antes de trocar* de contexto.
- **Retry de gestão:** repetir a **mesma** ação (geo/verba/pausar), nunca a criação de campanha.
- **Teste:** replay das execuções reais + harness por nó, **sem gasto novo**; smoke test manual pelo cliente no fim.

## Parte 1 — SUBIR_DENOVO nunca mais cria campanha por engano

**1a. Gate no intent SUBIR_DENOVO.** Antes de entrar no fluxo de criação (`build_extrator_body`), um nó decide pelo `estado.etapa_atual`:
- `pronta_pra_subir` → segue (é exatamente o caso de retry legítimo: brief completo + criativo, upload falhou).
- `ativa` → **bloqueia** com: *"Sua última campanha já está no ar 🟢. Pra criar outra, manda NOVA CAMPANHA."*
- qualquer outro (`coletando_info`, `aguardando_criativo`) → *"Não tem nenhuma campanha pronta pra subir ainda. Me manda os dados do imóvel que a gente monta."*

**1b. Mensagem de erro de gestão deixa de dizer "SUBIR DENOVO".**
Em `build_gestao_confirmation_msg`, o texto do ramo de erro passa a oferecer o retry seguro da própria gestão (Parte 2), com a palavra **TENTAR DE NOVO** — que só existe no contexto de gestão. "SUBIR DENOVO" fica restrito à criação de campanha.

## Parte 2 — Retry seguro da ação de gestão

**2a. Classificação correta de erro transitório.** `check_gestao_result.classify` passa a marcar como `infra` (além dos casos atuais):
- HTTP 400/500 cujo corpo contenha `(#613)` ou `rate limit` ou `code":613` (rate limit);
- `is_transient":true`;
- subcódigos transitórios conhecidos do Meta (`code":1`, `code":2`, `code":4`, `code":17`, `code":341`, `code":80004`).

**2b. Retry que repete a mesma gestão — reusando o caminho que já existe.**
Hoje `reset_gestao` (um nó Postgres na cadeia linear) roda no sucesso **e** no erro, e sempre faz `gestao = null` + `etapa_atual = 'ativa'` (essa segunda parte é, aliás, o que envenenou o estado no bug 1). A mudança: `prep_update_db` calcula `manter_gestao = (!ok && classe === 'infra')`, e `reset_gestao` fica condicional:
- `manter_gestao` verdadeiro → **não toca** no `estado_json` (mantém `gestao` com `passo:'confirmacao'`, `selecionada`, `novo_valor`).
- senão → limpa como hoje.

Com a gestão preservada, o cliente ainda está "em gestão" (passo confirmação). A mensagem de erro `infra` vira: *"⚙️ Deu um engasgo no Meta (nada de errado com seu pedido). Manda **SIM** de novo daqui a 1 min que eu repito, ou **CANCELAR**."* O "SIM" reentra pelo `process_gestao_step` (passo `confirmacao` → `acao:'executa'`) e re-executa `execute_gestao_action` com o `novo_valor` guardado — repete geo/verba/pausar, **sem criar nada** e **sem intent novo**. "CANCELAR" já é tratado pelo `process_gestao_step`.

Erro de `dado` (ex.: cidade inexistente) limpa a gestão e pede o dado corrigido, com o `motivo_usuario` legível já implementado no commit `e327359`.

## Parte 3 — Conversa fluida: perguntar antes de trocar

Toda a lógica fica em `process_gestao_step` (já é o dono do estado de gestão). Um detector `pareceComando(msg)` reconhece comandos de topo (pausar, reativar/ativar, encerrar, alterar/mudar verba/público/geo, status/relatório, nova campanha, subir, tutorial), com padrões ancorados (espelhando `classify_intent`) pra não capturar valores legítimos.

**Fluxo:**
- Em `selecao`/`confirmacao`: se o input não encaixa **e** `pareceComando(msg)` → `acao: 'pergunta_troca'`.
- Em `coleta_valor` (onde texto livre vira geo/público): checa `pareceComando(msg)` **antes** de aceitar como valor → evita "Pausar" virar cidade.
- `pergunta_troca` envia: *"Você tem uma **[ação legível]** em andamento na campanha *[nome]*. Quer **CONTINUAR** ela, ou **TROCAR** pra atender seu novo pedido?"* e grava `gestao.aguardando_troca = true`.
- Próxima mensagem, com `aguardando_troca`:
  - `continuar`/`anterior` → limpa a flag, repete o pedido do passo atual.
  - `trocar`/`nova`/`desconsiderar`/`deixa` → `reset` da gestão + *"Beleza, deixei a alteração anterior de lado 👍. Me manda de novo o que você quer fazer agora."* (o cliente reenvia; entra limpo pelo `classify_intent`).
  - outra coisa → repete a pergunta CONTINUAR/TROCAR.

**Trade-off aceito:** no "TROCAR", o cliente reenvia o comando (uma mensagem a mais) em vez de o sistema reprocessar o texto guardado. É deliberado: reprocessar exigiria uma aresta de volta ao `classify_intent` (frágil no n8n); reenviar é à prova de erro e a fricção é mínima. Se incomodar, vira follow-up.

Lixo de verdade (não-comando) mantém o reprompt atual ("não entendi, manda o número 1–N ou CANCELAR").

## Parte 4 — Status claro no relatório

Em `format_status_response`, trocar `'Status no Meta: ' + d.status_atual` por um mapa:

| status no banco | mostrado ao cliente |
|---|---|
| `CREATED_ACTIVE`, `ACTIVE` | 🟢 No ar |
| `CREATED_PAUSED`, `PAUSED` | ⏸️ Pausada |
| `ARCHIVED` | 📁 Encerrada |
| `PARTIAL_FAIL` | ⚠️ Subiu com pendência — me chama |
| (desconhecido) | o próprio valor, como fallback |

## Parte 5 — Rede de segurança global

Garantir que os dois pontos de entrada de erro do Meta no fluxo de gestão (`check_gestao_result`) e de criação (`check_meta_results`) tenham um `else` final: qualquer erro não classificado → mensagem amigável + saída segura (CANCELAR / TENTAR DE NOVO conforme o contexto), **nunca** um caminho que dispare criação de campanha.

## Não-objetivos (YAGNI)

- Não mexer no padrão "nó vazio estanca a cadeia" (`select_conversa`, `load_estado_*`) — frente separada já registrada.
- Não reprocessar automaticamente o comando no "TROCAR" (ver trade-off).
- Não buscar `effective_status` ao vivo no Meta pro relatório — o status do banco é a fonte que temos; tradução resolve o pedido.

## Testes (sem gasto novo)

1. **Replay** das execuções reais contra o código corrigido: 22942 (denovo→bloqueia), 22937 (rate limit→infra→TENTAR DE NOVO), 22877 (comando no meio→pergunta_troca), status (→"no ar/pausada").
2. **Harness por nó:** `classify` (rate limit vira infra), `pareceComando`, gate do SUBIR_DENOVO por `etapa_atual`, mapa de status.
3. **Smoke test manual** do cliente no número de teste: pausar→trocar no meio; geo com rate limit→tentar de novo; status.

## Deploy

Alterações de `jsCode` via API do n8n, uma por vez, com **backup antes** e `node --check`, padrão dos scripts `g_*`. Settings sempre `{executionOrder}`.
