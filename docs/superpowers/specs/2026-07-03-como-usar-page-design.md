# Página "Como usar o Auto Ads" — design

**Data:** 2026-07-03
**Status:** Aprovado (design)

## Objetivo

Uma página web curta e direta que ensina o cliente **já ativo** a usar o Auto Ads pelo WhatsApp: como criar um anúncio (o briefing), o que acontece depois, e os comandos do dia a dia. Reduz atrito e suporte. Entregue como link no WhatsApp quando o cliente vira `ativo`.

## Princípio de conteúdo (regra do Renan)

**Simples e direto. Nada de textão.** Cada seção é escaneável em segundos: frases curtas, listas, 1 exemplo pronto pra copiar. Cobrir TODOS os detalhes de uso — mas de forma enxuta.

## Não-objetivos (YAGNI)

- Não é o onboarding de conexão da conta Meta (isso já existe no `onboarding.html`).
- Sem vídeo nesta v1 (só texto + exemplo; pode entrar depois).
- Sem FAQ extenso — só "dicas rápidas".
- Sem login/proteção (é conteúdo público de ajuda; sem dado sensível).

## Formato e local

- Página estática única `como-usar.html`, **mesmo estilo dark premium** do `onboarding.html` (variáveis de marca: `--bg:#001D41`, azul `#1D80FF`, ciano `#00E5FF`, verde `#39b54a`, fontes Sora + Poppins).
- Fica em `/Users/renanreal/Desktop/Quirk Auto Ads - Páginas/como-usar.html` → sobe no cPanel → `https://autoads.quirkgrowth.com.br/como-usar.html`.

## Estrutura e conteúdo (copy concreta — curta)

**1. Hero**
> Tudo conectado! 🎉
> Agora é só me chamar no WhatsApp pra criar seus anúncios. Veja como — leva 2 minutos.

**2. Como criar um anúncio** (o coração)
> Me manda **numa mensagem** os dados do imóvel:
> - **Tipo** (apê, casa, sobrado, lote…)
> - **Valor**
> - **Bairro + cidade**
> - **Objetivo**: morar, investir ou veraneio
>
> 👉 Exemplo: *"Apartamento de R$ 650 mil no Batel, Curitiba, pra investidor."*
>
> Faltou algo? Eu te pergunto. Pode mandar **fotos ou o book** junto.

**3. O que acontece depois** (3 passos)
> 1. Eu confirmo o **público** e a **verba diária** (começa em R$30/dia).
> 2. Você responde **"confirma"**.
> 3. O anúncio **sobe** — te aviso quando estiver no ar.

**4. Comandos do dia a dia** (cola — comando → o que faz)
> - **status** → ver como estão seus anúncios
> - **pausar** (diz qual imóvel) → pausa um anúncio
> - **ativar** (diz qual) → religa um anúncio pausado
> - **muda a verba pra R$X/dia** → altera o investimento diário
> - **listar** → ver todos os seus anúncios
> - **cancelar** (diz qual) → encerra um anúncio

**5. Dicas rápidas**
> - A verba começa no **piso seguro (R$30/dia)** — você aumenta quando quiser.
> - Mande **foto/book** do imóvel pra usar no anúncio.
> - A Meta leva de **minutos a algumas horas** pra aprovar. Te aviso quando no ar.

**6. Rodapé**
> Qualquer dúvida, é só me chamar aqui no WhatsApp. 💬

> **Nota de fidelidade:** os campos do briefing (tipo, valor, bairro/cidade, objetivo) e os comandos (status, pausar, ativar, alterar verba, listar, cancelar) refletem o que o bot realmente aceita (`prompts/agente_principal.md` linha ~120 + intents do classificador). Na implementação, conferir o fraseado dos comandos contra `prompts/classifier.md` e ajustar se algum termo divergir.

## Integração (entrega do link)

Quando o cliente vira `ativo`, o bot deve mandar (ou incluir na mensagem de liberação) o link `https://autoads.quirkgrowth.com.br/como-usar.html`. É um ajuste pequeno na mensagem de ativação do workflow principal do n8n. Escopo mínimo: adicionar a linha do link na mensagem que já é disparada na transição para `ativo` (não criar fluxo novo).

## Testes

1. Página abre em produção, renderiza as 6 seções, responsiva no celular (corretor abre no zap).
2. Sem erro de console; `noindex` opcional (é ajuda pública, mas pode marcar).
3. Link no WhatsApp: ao virar `ativo`, a mensagem de liberação contém o link e ele abre a página.
4. Fidelidade: comandos e campos batem com `agente_principal.md`/`classifier.md`.

## Deploy

- Salvar `como-usar.html` na pasta das páginas + subir no cPanel (mesma pasta do subdomínio).
- Versionar no repo (`frontend_admin/` ou nova pasta `paginas/`) + este spec.
- Ajuste da mensagem de ativação no n8n via API (com backup antes).
