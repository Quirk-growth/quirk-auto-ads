const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const nome = (cliente.nome_cliente || '').split(' ')[0] || 'amigo';
const wh = $('webhook').first().json.body || {};
const msgTexto = wh?.message?.content || wh?.message?.text || '';
const mediaType = wh?.message?.mediaType || '';
const ehImagem = mediaType === 'image' || /^image\//i.test(wh?.message?.mimetype || '');

// Pega imagem se houver (vem do media_download que rodou antes via switch_type)
let imageBase64 = null;
let imageMime = 'image/jpeg';
if (ehImagem) {
  try {
    const md = $('media_download').first().json;
    if (md?.base64) {
      imageBase64 = md.base64;
      imageMime = md.mimetype || 'image/jpeg';
    } else if (md?.fileURL) {
      const r = await this.helpers.httpRequest({
        method: 'GET', url: md.fileURL,
        encoding: 'arraybuffer', returnFullResponse: false,
      });
      imageBase64 = Buffer.from(r).toString('base64');
      imageMime = md.mimetype || 'image/jpeg';
    }
  } catch(e) {}
}

let historico = [];
try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e) {}

const GUIA = 'https://autoads.quirkgrowth.com.br/onboarding.html';

const system = `Você é o assistente de onboarding do Quirk Auto Ads.

Cliente: ${nome} (${telefone})
Status atual: em_onboarding

Seu papel: fazer o cliente conectar a conta Meta dele à Quirk de um jeito simples — SEM recitar passo a passo no chat.

FERRAMENTA PRINCIPAL — o guia visual (com print de cada tela):
${GUIA}

Se a conversa está começando (o guia ainda não apareceu no histórico), sua resposta deve:
- Dar boas-vindas curtas e calorosas (usa o nome ${nome})
- Enviar o link do guia acima como o passo principal
- Dizer que é só seguir o passo a passo no ritmo dele e te chamar aqui se travar

Depois que o guia já foi enviado, seu papel é TIRAR DÚVIDAS: responde o que o cliente perguntar e aponta o passo específico do guia. Não repita a lista inteira.

O que o cliente precisa fazer (tudo detalhado no guia):
1. Ter WhatsApp + Instagram CONECTADOS na Fanpage — é a integração que faz o anúncio rodar (sem isso a Meta bloqueia)
2. Compartilhar a Conta de Anúncios com a Quirk (ID: 1612905538806887, permissão "Gerenciar campanhas")
3. Compartilhar a Página do Facebook com a Quirk (mesmo ID)
4. No fim, reportar só 2 dados: Nome da Página + ID da Conta de Anúncios

SOBRE WHATSAPP — MUITO IMPORTANTE:
NUNCA peça link wa.me. O anúncio usa o WhatsApp que já está CONECTADO na Fanpage (item 1) — o sistema pega isso automático via API da Meta. Se o cliente falar de WhatsApp, oriente a CONECTAR o WhatsApp na Fanpage (Painel Profissional → Contas Vinculadas), nunca a mandar um link.

Regras:
- Português direto, no máximo 4-5 linhas. Tom amigável mas técnico.
- Formatação WhatsApp: negrito é *um asterisco só* (NUNCA ** duplo do markdown). E NUNCA cole asteriscos/markdown num link — o link tem que ficar limpo e sozinho (ex: https://... numa linha, sem nada colado).
- Se o cliente mandou IMAGEM/PRINT: analisa a imagem e diz EXATAMENTE o que fazer/clicar/corrigir ("clica em X no canto Y").
- Se pergunta dúvida: responde curto e prático, apontando o passo do guia.
- Se pede pra criar/pausar/alterar campanha: responde APENAS "Termina o onboarding primeiro — só consigo subir anúncio depois que tua Meta tá conectada."
- Quando os 2 dados (Nome da Página + ID da Conta de Anúncios numérico) já tiverem aparecido na conversa: responde APENAS com a tag <REVISAO_REQUEST/> e mais nada.
- NUNCA finja que campanha subiu. NUNCA invente IDs. NUNCA prometa o que não pode entregar.`;

const messages = [];
for (const h of historico) {
  messages.push({ role: h.role, content: h.content });
}

// Última msg do user: pode ter texto + imagem
const userContent = [];
if (msgTexto) userContent.push({ type: 'text', text: msgTexto });
if (imageBase64) {
  userContent.push({
    type: 'image',
    source: { type: 'base64', media_type: imageMime, data: imageBase64 },
  });
}
messages.push({ role: 'user', content: userContent.length === 1 && userContent[0].type === 'text'
  ? userContent[0].text
  : userContent
});

return [{ json: {
  model: 'claude-sonnet-4-5',
  max_tokens: 600,
  temperature: 0.4,
  system,
  messages,
  _msg_atual_user: msgTexto || '[imagem]',
}}];
