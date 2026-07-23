# Onboarding — auto-detecção de conta/página (fim do "digite o ID") — design

**Data:** 2026-07-22
**Status:** Aprovado (design)

## Problema

No onboarding, pra virar `ativo` o cliente precisa **reportar o ID da conta de anúncios** (14-17 dígitos) na conversa. Isso é técnico e propenso a erro — o cliente conecta tudo na BM mas não consegue reportar o ID certo, e **fica preso no onboarding** sem o bot ter como aceitar "já está pronto". (Aconteceu com a 1ª cliente real, Jimenne — resolvido na marra via ativação manual no banco.)

## Objetivo

Remover o passo de digitar o ID: a **conta de anúncios** passa a ser detectada **por nome** (como a página já é hoje), a partir dos ativos que o cliente compartilhou com a BM Quirk. Com travas anti-troca, confirmação sempre, e escape pra humano quando não resolver — pra o cliente **nunca ficar preso**.

## Estado atual (o que já existe — construir em cima)

- Gatilho: `onboarding_agent` emite `<REVISAO_REQUEST/>` quando o cliente sinaliza que terminou → `parse_onboarding_resp` seta `solicita_revisao=true` → dispara `revisao_meta`.
- `revisao_meta` (workflow principal `fBUin1UPt5xJEp6g`):
  - **Página:** JÁ casa por nome (lista `client_pages`+`owned_pages` da BM, match fuzzy com o que o cliente citou).
  - **Conta de anúncios:** extrai um ID `\d{14,17}` da conversa; se não achar → falha ("me manda o ID"). **É o que trava.**
  - Sucesso → `update_cliente_ativo` (status `ativo` + grava ad_account_id/page_id).
- BM Quirk (Auto Ads): `1612905538806887`. Token: `meta_access_token` no config.

## Arquitetura (mudanças, todas no workflow principal)

### 1. Detecção da conta de anúncios por nome (`revisao_meta`)
Trocar "extrai ID da conversa" por match por nome, igual a página:
- Lista `GET /{BM}/client_ad_accounts?fields=account_id,name`.
- **Filtra "sem dono":** remove os `account_id` que já estão em `auto_ads.clientes.ad_account_id` (qualquer cliente). **Trava anti-troca** — só considera ativos ainda não atribuídos.
- Match por nome contra: **(a)** `nome_cliente` (do cadastro) e **(b)** termos que o cliente citou na conversa. Match fuzzy (lowercase, sem acento, "contém"), como o da página.
- **Aplicar o MESMO filtro "sem dono" à página** (hoje ela casa entre todas; passa a casar só entre as sem dono).

### 2. Confirmação sempre (novo estado `aguardando_confirmacao`)
- Achou **exatamente 1 conta + 1 página** (sem dono, nome batendo) → `revisao_meta` **NÃO ativa**. Retorna os candidatos; o bot manda: *"Achei a conta *'{nome_conta}'* e a página *'{nome_pagina}'*. Confirma que são essas? (responde SIM)"* e o estado do cliente vai pra `aguardando_confirmacao` (guardando os IDs candidatos no `estado_json`).
- Cliente responde **SIM/confirmo/isso** → ativa (`update_cliente_ativo` com os IDs guardados) → mensagem de boas-vindas "pode subir campanhas".
- Cliente responde que **não são essas** → volta pro fluxo de onboarding (pede pra conferir / mostra a lista).

### 3. Na dúvida / não achou (nunca adivinha)
- **0 candidatos sem dono** (disse que terminou, mas nada compartilhado bate) → bot explica o que provavelmente falta (compartilhar a Conta de Anúncios com a Quirk, permissão "Gerenciar campanhas") — texto curto e claro.
- **2+ candidatos** → o bot mostra a **lista curta de nomes** e pede pro cliente dizer qual é a dele → depois confirma.

### 4. Escape pra humano (rede de segurança)
- Contador de tentativas de revisão que falharam por "não achou" no `estado_json` (ex: `revisao_falhas`).
- Ao atingir **3 falhas**, o sistema:
  - Manda um alerta no WhatsApp do Renan (número interno) via Cloud API: *"⚠️ Cliente {nome} ({telefone}) preso no onboarding — não consegui detectar os ativos após 3 tentativas. Dá uma olhada."*
  - Marca o cliente (ex: `estado_json.travado_onboarding=true`) pra destacar no painel admin depois.
- O cliente recebe uma mensagem tranquilizadora ("Vou pedir pro time dar uma olhada e já te retorno") em vez de loop.

## Segurança (anti-troca, mesmo com onboarding simultâneo)

- **Só considera ativos "sem dono"** (não atribuídos a nenhum cliente) → dois clientes simultâneos não veem o ativo já atribuído do outro.
- **Atribuição por nome do próprio cliente** (cadastro + o que ele diz), nunca por tempo/"mais recente".
- **Confirmação sempre** mostra o nome completo → o cliente rejeita se não for dele.
- **Na dúvida (0 ou 2+), pergunta** — não decide sozinho.
- Match parcial é seguro porque o universo é minúsculo (só ativos sem dono no momento).

## Não-objetivos (YAGNI)

- Não mexer no compartilhamento em si (o cliente continua compartilhando os ativos com a BM — é a fronteira de segurança, e fica).
- Sem integração Embedded Signup da Meta (Opção C — futuro).
- O botão **"Ativar + avisar" no painel admin** é **follow-on separado** (spec própria): ativa + manda boas-vindas + limpa contexto de onboarding num clique, pra intervenção manual.

## Casos de borda

- Conta compartilhada mas página não (ou vice-versa) → detecta a que achou, pede a outra de forma específica.
- Cliente com nome de cadastro diferente do nome do ativo (batizou a conta com nome de imobiliária) → o match por (b) "o que ele citou" cobre; se não, cai em "mostra a lista".
- Ativo compartilhado mas com permissão errada ("Gerenciar campanhas") → a checagem de acesso existente no `revisao_meta` continua valendo; se não conseguir usar, explica.
- Reativação de cliente já `ativo` que re-dispara revisão → idempotente (já tem IDs; não reatribui).

## Testes

1. **Fluxo feliz:** cliente `em_onboarding` com conta+página compartilhadas (sem dono) e nome batendo → sinaliza que terminou → bot pergunta "confirma '{conta}' e '{página}'?" → responde SIM → vira `ativo` com os IDs certos + mensagem de boas-vindas. (Testar com um cliente de teste real da BM.)
2. **Anti-troca:** com 2 contas sem dono, uma do cliente e uma de outro → o match pega só a do nome dele; se ambíguo, mostra a lista (não ativa sozinho).
3. **Não achou:** cliente sem nada compartilhado sinaliza terminado → bot explica o que falta, não ativa.
4. **Escape:** 3 falhas → alerta chega no WhatsApp do Renan + cliente recebe mensagem de "vou pedir pro time".
5. **Confirmação negada:** bot sugere candidato errado, cliente diz "não é essa" → volta pro onboarding sem ativar.

## Deploy

- Alterações via API do n8n no workflow `fBUin1UPt5xJEp6g` (com **backup** antes; padrão dos scripts `g_*`), + edição do prompt embutido no `onboarding_agent`/`build_onboarding_body`.
- Testar na instância com um cliente de teste antes de considerar pronto.
