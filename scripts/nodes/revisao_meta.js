// Revisão v2: valida acesso Meta + ativa cliente. 2 dados (Página + Conta de Anúncios), SEM link WhatsApp.
const cliente = $('classify_status').first().json.cliente;
let historico = [];
try {
  const novo = $('parse_onboarding_resp').first().json.novo_historico;
  historico = JSON.parse(novo || cliente.historico_onboarding || '[]');
} catch(e) {
  try { historico = JSON.parse(cliente.historico_onboarding || '[]'); } catch(e2) { historico = []; }
}
const telefone = cliente.telefone;

// TODA a conversa do usuário (não só as últimas 5 — senão dados picotados se perdem)
const userText = historico
  .filter(h => h.role === 'user')
  .map(h => typeof h.content === 'string'
    ? h.content
    : (Array.isArray(h.content) ? h.content.map(c => c.text || '').join(' ') : ''))
  .join('\n');

// Conta de Anúncios: número longo (14-17 dígitos). Pega o ÚLTIMO informado.
const adMatches = [...userText.matchAll(/\b(\d{14,17})\b/g)].map(m => m[1]);
const ad_account_id = adMatches.length ? adMatches[adMatches.length - 1] : null;

if (!ad_account_id) {
  return [{ json: {
    ok: false, motivo: 'dados_incompletos', telefone,
    mensagem: 'Pra finalizar preciso do *ID da Conta de Anúncios* (os números que aparecem no Gerenciador). Me manda ele junto com o *nome da tua Página*. 🙂',
  }}];
}

let token = '';
try { token = $('load_meta_token_revisao').first().json.valor; } catch(e) {}
if (!token) {
  return [{ json: { ok: false, motivo: 'sem_token_meta', telefone, mensagem: 'Deu um errinho interno aqui — já te chamo de volta.' } }];
}

const BM_QUIRK = '1612905538806887';
const apiBase = 'https://graph.facebook.com/v25.0';
async function getJson(url) {
  const r = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
  return (typeof r === 'string') ? JSON.parse(r) : r;
}
async function postForm(path, params) {
  const body = Object.entries(params).map(([k, v]) => `${k}=${encodeURIComponent(v)}`).join('&');
  const r = await this.helpers.httpRequest({
    method: 'POST', url: `${apiBase}/${path}`, body,
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    returnFullResponse: false,
  });
  return (typeof r === 'string') ? JSON.parse(r) : r;
}
const SYS_USER = '122093025345347834'; // System User "Quirkautoads"
const norm = s => String(s || '').trim().toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');

// 1. Conta de Anúncios compartilhada com a Quirk?
let adAccounts = [];
try {
  const r = await getJson.call(this, `${apiBase}/${BM_QUIRK}/client_ad_accounts?fields=id,account_id,name&limit=500&access_token=${encodeURIComponent(token)}`);
  adAccounts = r.data || [];
} catch(e) {
  return [{ json: { ok: false, motivo: 'erro_meta_api', telefone, mensagem: 'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.' } }];
}
const adAccountEncontrada = adAccounts.find(a =>
  String(a.account_id) === String(ad_account_id) ||
  String(a.id).replace('act_', '') === String(ad_account_id)
);
if (!adAccountEncontrada) {
  return [{ json: {
    ok: false, motivo: 'ad_account_nao_compartilhada', telefone,
    mensagem: `Não achei a Conta de Anúncios ${ad_account_id} compartilhada com a Quirk.\n\nConfere:\n1. Você compartilhou a *Conta de Anúncios* (não o Business inteiro) com a Quirk?\n2. A permissão é "Gerenciar campanhas"?\n3. ID da Quirk: ${BM_QUIRK}\n\nDepois de ajustar, é só me chamar.`,
  }}];
}

// 2. Página: junta compartilhadas (client_pages) + próprias da BM (owned_pages)
//    e acha qual delas o cliente citou na conversa (sem exigir formato "página:")
let pages = [];
try {
  const [cp, op] = await Promise.all([
    getJson.call(this, `${apiBase}/${BM_QUIRK}/client_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`),
    getJson.call(this, `${apiBase}/${BM_QUIRK}/owned_pages?fields=id,name&limit=500&access_token=${encodeURIComponent(token)}`),
  ]);
  pages = [...(cp.data || []), ...(op.data || [])];
} catch(e) {
  return [{ json: { ok: false, motivo: 'erro_meta_api', telefone, mensagem: 'Não consegui consultar a Meta agora. Tenta de novo daqui a 1 minutinho.' } }];
}
const userNorm = norm(userText);
// prioriza o nome mais longo que casa (evita match espúrio de nomes curtos)
const candidatas = pages
  .filter(p => p.name && norm(p.name).length >= 3 && userNorm.includes(norm(p.name)))
  .sort((a, b) => norm(b.name).length - norm(a.name).length);
const paginaEncontrada = candidatas[0];
if (!paginaEncontrada) {
  return [{ json: {
    ok: false, motivo: 'pagina_nao_compartilhada', telefone,
    mensagem: `Ainda não localizei a sua Página compartilhada com a Quirk.\n\nConfere rapidinho:\n1. Você compartilhou a *sua Página* com a Quirk (ID ${BM_QUIRK}), com a permissão certa?\n2. Me manda o *nome exato* da Página, igualzinho aparece no seu Facebook.\n\nAssim que ajustar, é só me chamar. 🙂`,
  }}];
}

// 2.5. AUTO-ATRIBUIÇÃO do System User (pra ganhar liberdade de subir anúncios sozinho)
let assign_ad = false, assign_page = false, assign_err = '';
try {
  const r = await postForm.call(this, `act_${ad_account_id}/assigned_users`, {
    user: SYS_USER, tasks: '["MANAGE","ADVERTISE","ANALYZE"]', access_token: token,
  });
  assign_ad = !!(r && r.success);
} catch(e) { assign_err += 'ad:' + String(e).slice(0, 120) + ' '; }
try {
  const r = await postForm.call(this, `${paginaEncontrada.id}/assigned_users`, {
    user: SYS_USER, tasks: '["ADVERTISE","ANALYZE","CREATE_CONTENT"]', access_token: token,
  });
  assign_page = !!(r && r.success);
} catch(e) { assign_err += 'page:' + String(e).slice(0, 120); }

// 3. Permissão de campanhas (Gerenciar, não só Visualizar) — confirma que a atribuição pegou
try {
  await getJson.call(this, `${apiBase}/act_${ad_account_id}/campaigns?fields=id&limit=1&access_token=${encodeURIComponent(token)}`);
} catch(e) {
  return [{ json: {
    ok: false, motivo: 'sem_permissao_campanhas', telefone,
    mensagem: 'Tô vendo a Conta de Anúncios compartilhada, mas não consigo gerenciar campanhas dela. A permissão precisa ser "Gerenciar campanhas" (não só "Visualizar"). Ajusta e me chama.',
  }}];
}

// 4. TUDO OK!
const primeiroNome = (cliente.nome_cliente || '').split(' ')[0] || '';
return [{ json: {
  ok: true, telefone,
  ad_account_id,
  page_id: paginaEncontrada.id,
  page_name: paginaEncontrada.name,
  wa_link: '',
  assign_ad, assign_page, assign_err,
  mensagem: `✅ Tudo certo, ${primeiroNome}! Tua Meta tá conectada na Quirk:\n\n📊 Conta de Anúncios: ${adAccountEncontrada.name || ad_account_id}\n📄 Página: ${paginaEncontrada.name}\n💬 WhatsApp: pego direto da Fanpage ✅\n\n*Próximo passo* — pra subir tua primeira campanha, manda uma foto ou vídeo do imóvel + uma descrição. Ex:\n\n_"Apto 2Q no [bairro/cidade], R$ XXX mil, raio X km, perfil [investidor/morador]"_\n\nQuando quiser, é só começar. 🚀`,
}}];
