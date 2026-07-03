const resp = $input.first().json;
const txt = resp?.content?.[0]?.text || '';
const solicita_revisao = /<REVISAO_REQUEST\s*\/?>/i.test(txt);

// remove a tag de controle
let limpo = txt.replace(/<REVISAO_REQUEST\s*\/?>/gi, '').trim();

// Formatação WhatsApp:
//  - ** (negrito markdown) -> * (negrito WhatsApp)
//  - nunca deixa asterisco colado num link (senão o ** entra na URL e quebra o link)
limpo = limpo
  .replace(/\*\*+/g, '*')                          // ** ou *** -> *
  .replace(/\*+(?=https?:\/\/)/g, '')              // remove * ANTES do link
  .replace(/(https?:\/\/[^\s*]+)\*+/g, '$1');      // remove * DEPOIS do link

const cliente = $('classify_status').first().json.cliente;
const telefone = cliente.telefone;
const userMsg = $('build_onboarding_body').first().json._msg_atual_user || '';

let historico = [];
try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e) {}
historico.push({ role: 'user', content: userMsg });
if (limpo) historico.push({ role: 'assistant', content: limpo });
if (historico.length > 60) historico = historico.slice(-60);

return [{ json: {
  solicita_revisao,
  text: limpo,
  telefone,
  novo_historico: JSON.stringify(historico),
}}];
