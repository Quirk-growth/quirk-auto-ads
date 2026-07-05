# Admin — filtros, busca e onboarding visível — design

**Data:** 2026-07-04
**Status:** Aprovado (design)

## Objetivo

Melhorar o painel admin pra dar visibilidade operacional: ver quem está **preso no onboarding** (pagou, não ativou), e filtrar/buscar clientes. Frontend-only — o backend `admin-clientes` já retorna todos os clientes + status.

## Decisões

- **Sem `inadimplente`.** Mantém-se o modelo atual de status (`ativo`, `inativo`, `pago_aguardando_meta`, `em_onboarding`, `em_revisao`). Nada muda no gateway.
- Filtro e busca acontecem **no frontend**, sobre a lista já carregada (base pequena).

## Mudanças (só `admin.html`)

1. **Carregar todos os clientes** por padrão: o dashboard passa a buscar com `somente_ativos: false` (em vez do toggle "só ativos"). Remove-se o toggle antigo.
2. **Filtro por status (chips/segmented):**
   - **Todos** (default)
   - **Ativo** → `status === 'ativo'`
   - **Onboarding** → `status ∈ {pago_aguardando_meta, em_onboarding, em_revisao}` (pagou, ainda não ativou — quem precisa de ajuda)
   - **Inativo** → `status === 'inativo'`
   - O chip ativo destaca visualmente; a tabela re-renderiza na hora.
3. **Busca por nome:** um campo de texto que filtra por `nome_cliente` (case-insensitive, substring). Combina com o filtro de status (AND).
4. **Badge de status:** garantir badge/cor pra `pago_aguardando_meta`, `em_onboarding`, `em_revisao` (âmbar/azul p/ "em onboarding") além de `ativo` (verde) e `inativo` (vermelho).
5. **Contador:** ao lado dos KPIs, mostrar quantos clientes o filtro atual está exibindo (ex.: "3 de 8"). KPIs `total_ativos` e `mrr_estimado` (do backend) permanecem.

## Não-objetivos

- Nada no backend/gateway.
- Sem `inadimplente`, sem paginação (base pequena), sem ordenação configurável.

## Testes

1. Carrega e mostra TODOS os clientes (inclui os `em_onboarding`) por padrão.
2. Filtro **Onboarding** mostra só os `pago_aguardando_meta`/`em_onboarding`/`em_revisao`.
3. Filtros **Ativo** e **Inativo** funcionam; **Todos** volta a lista completa.
4. Busca por nome filtra corretamente e combina com o filtro de status.
5. Badges corretos por status; contador reflete o filtro.
6. Validação em produção (após subir `admin.html` no cPanel), sem erro de CORS/console.

## Deploy

- Editar `admin.html` (Desktop `Quirk Auto Ads - Páginas/` + `frontend_admin/` no repo), subir no cPanel, versionar.
