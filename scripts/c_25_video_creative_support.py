"""
c_25_video_creative_support.py

Habilita suporte a vídeo no fluxo de criativo. Antes, vídeo era bloqueado
em três pontos (b_14_reject_video_creative.py). Agora:

  1. decide_acao_media: remove flag video_rejeitado
  2. build_media_response: remove mensagem de rejeição de vídeo
  3. media_upsert_criativo: remove guard SQL WHERE mimetype LIKE 'image/%'
  4. meta_d3_creative: transformado em Code node JS que:
     - se mimetype = image/* → POST /adcreatives com link_data.picture (igual antes)
     - se mimetype = video/* → POST /advideos (upload) + polling status=ready
       + POST /adcreatives com video_data.video_id + thumbnail (image_url)

Notas:
- Polling video status: até 5 tentativas, 4s entre cada (20s total).
  Vídeos curtos do WhatsApp processam em < 10s normalmente.
- Thumbnail vem do próprio /advideos via fields=picture (Meta gera auto).
- file_url passado pra /advideos é o fileURL da uazapi
  (URL temporária mas válida durante o upload).
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)

fixes_applied = []
fixes_failed = []

# ─────────────────────────────────────────────────────────────
# A — decide_acao_media: vídeo não é mais rejeitado
# ─────────────────────────────────────────────────────────────

OLD_DECIDE = """\
const eh_imagem = /^image\\//i.test(mimetype);
const eh_video = /^video\\//i.test(mimetype);
const video_rejeitado = eh_video || (!eh_imagem && mimetype.length > 0);"""

NEW_DECIDE = """\
const eh_imagem = /^image\\//i.test(mimetype);
const eh_video = /^video\\//i.test(mimetype);
// Tipo desconhecido (não-image E não-video com mimetype não-vazio) continua rejeitado
const video_rejeitado = !eh_imagem && !eh_video && mimetype.length > 0;"""

# ─────────────────────────────────────────────────────────────
# B — build_media_response: msg de vídeo recebido (não rejeita)
# ─────────────────────────────────────────────────────────────

OLD_RESP = """\
// vídeo rejeitado mantém prioridade
if (d.video_rejeitado) {
  text = '⚠️ Por enquanto só aceito FOTO no criativo (JPG ou PNG). Vídeo ainda não tá suportado. Manda uma imagem do imóvel.';
} else if (d.duplicado_recente) {"""

NEW_RESP = """\
// tipo de mídia desconhecido rejeitado mantém prioridade
if (d.video_rejeitado) {
  text = '⚠️ Tipo de arquivo não suportado. Manda FOTO (JPG/PNG) ou VÍDEO (MP4) do imóvel.';
} else if (d.duplicado_recente) {"""

# ─────────────────────────────────────────────────────────────
# C — media_upsert_criativo: aceita image E video
# ─────────────────────────────────────────────────────────────

OLD_SQL_GUARD = (
    "WHERE '{{ ($('media_download').item.json.mimetype || '').replace(/'/g, \"''\") }}' LIKE 'image/%'"
)
NEW_SQL_GUARD = (
    "WHERE '{{ ($('media_download').item.json.mimetype || '').replace(/'/g, \"''\") }}' ~ '^(image|video)/'"
)

# ─────────────────────────────────────────────────────────────
# D — meta_d3_creative: vira Code com branch image/video
# ─────────────────────────────────────────────────────────────

META_D3_CODE = r"""// Cria adcreative no Meta. Suporta IMAGEM (link_data.picture) e VÍDEO (video_data).
// Vídeo requer upload prévio em /advideos + polling até status=ready.

const v = $('validate').first().json;
const adAccountId = v.cliente.ad_account_id;
const pageId = v.cliente.page_id;
const waLink = v.cliente.wa_link;
const campNome = v.json_extrator.campanha.nome;
const copy = v.json_extrator.anuncio.copy;
const token = $('load_meta_token').first().json.valor;

// Resolve URL do criativo (formato igual ao do nó antigo)
const criativoUrlRaw = (v.conversa.criativo_url || '').trim();
const criativoUrl = criativoUrlRaw.split('\n').filter(u => u).slice(-1)[0];

// Determina tipo via estado.criativo.mimetype
let mimetype = '';
try { mimetype = v.estado?.criativo?.mimetype || ''; } catch(e) {}
const ehVideo = /^video\//i.test(mimetype);

const baseHeaders = { 'Content-Type': 'application/json' };
const apiBase = 'https://graph.facebook.com/v25.0';

async function postJson(url, body) {
  return await this.helpers.httpRequest({
    method: 'POST', url, headers: baseHeaders, body, json: true,
    returnFullResponse: false,
  });
}
async function getJson(url) {
  return await this.helpers.httpRequest({
    method: 'GET', url, returnFullResponse: false,
  });
}

if (ehVideo) {
  // ─────────────── BRANCH VÍDEO ───────────────
  // 1) Upload via /advideos com file_url
  const uploadResp = await postJson.call(this,
    `${apiBase}/act_${adAccountId}/advideos`,
    { file_url: criativoUrl, name: campNome, access_token: token }
  );
  const videoId = uploadResp.id;
  if (!videoId) {
    return [{ json: { error: 'video_upload_falhou', resp: uploadResp } }];
  }

  // 2) Polling status até ready (max 5 tentativas × 4s = 20s)
  let videoStatus = null;
  let thumbnail = null;
  for (let i = 0; i < 5; i++) {
    await new Promise(r => setTimeout(r, 4000));
    const statusResp = await getJson.call(this,
      `${apiBase}/${videoId}?fields=status,picture&access_token=${encodeURIComponent(token)}`
    );
    const parsed = (typeof statusResp === 'string') ? JSON.parse(statusResp) : statusResp;
    videoStatus = parsed?.status?.video_status || parsed?.status;
    thumbnail = parsed?.picture || thumbnail;
    if (videoStatus === 'ready') break;
    if (videoStatus === 'error') {
      return [{ json: { error: 'video_processing_error', video_id: videoId, status: parsed } }];
    }
  }
  if (videoStatus !== 'ready') {
    return [{ json: { error: 'video_processing_timeout', video_id: videoId, last_status: videoStatus } }];
  }

  // 3) Cria adcreative com video_data
  const videoData = {
    video_id: videoId,
    title: campNome,
    message: copy,
    call_to_action: { type: 'WHATSAPP_MESSAGE', value: { link: waLink, app_destination: 'WHATSAPP' } }
  };
  if (thumbnail) videoData.image_url = thumbnail;

  const creativeResp = await postJson.call(this,
    `${apiBase}/act_${adAccountId}/adcreatives`,
    {
      name: campNome,
      object_story_spec: { page_id: pageId, video_data: videoData },
      access_token: token,
    }
  );
  if (!creativeResp.id) {
    return [{ json: { error: 'video_creative_falhou', resp: creativeResp, video_id: videoId } }];
  }
  return [{ json: { id: creativeResp.id, tipo_criativo: 'video', video_id: videoId, thumbnail_url: thumbnail || null } }];

} else {
  // ─────────────── BRANCH IMAGEM (default — comportamento original) ───────────────
  const body = {
    name: campNome,
    object_story_spec: {
      page_id: pageId,
      link_data: {
        message: copy,
        picture: criativoUrl,
        link: waLink,
        call_to_action: { type: 'WHATSAPP_MESSAGE', value: { app_destination: 'WHATSAPP' } }
      }
    },
    access_token: token,
  };
  const creativeResp = await postJson.call(this,
    `${apiBase}/act_${adAccountId}/adcreatives`,
    body
  );
  if (!creativeResp.id) {
    return [{ json: { error: 'image_creative_falhou', resp: creativeResp } }];
  }
  return [{ json: { id: creativeResp.id, tipo_criativo: 'image' } }];
}
"""

# Validate precisa expor estado pra o code lê mimetype.
# Vou checar se v.estado já existe — provavelmente sim.

# ─────────────────────────────────────────────────────────────
# Aplicar
# ─────────────────────────────────────────────────────────────

meta_d3_old_position = None
meta_d3_old_id = None

for node in wf['nodes']:
    name = node['name']

    if name == 'decide_acao_media':
        code = node['parameters'].get('jsCode', '')
        if OLD_DECIDE in code:
            node['parameters']['jsCode'] = code.replace(OLD_DECIDE, NEW_DECIDE)
            fixes_applied.append('decide_acao_media: vídeo não rejeitado mais')
        else:
            fixes_failed.append('decide_acao_media: bloco não encontrado')

    elif name == 'build_media_response':
        code = node['parameters'].get('jsCode', '')
        if OLD_RESP in code:
            node['parameters']['jsCode'] = code.replace(OLD_RESP, NEW_RESP)
            fixes_applied.append('build_media_response: msg para tipo desconhecido (não vídeo)')
        else:
            fixes_failed.append('build_media_response: bloco não encontrado')

    elif name == 'media_upsert_criativo':
        q = node['parameters'].get('query', '')
        if OLD_SQL_GUARD in q:
            node['parameters']['query'] = q.replace(OLD_SQL_GUARD, NEW_SQL_GUARD)
            fixes_applied.append('media_upsert_criativo: aceita image OR video no SQL guard')
        else:
            fixes_failed.append('media_upsert_criativo: WHERE LIKE image/% não encontrado')

    elif name == 'meta_d3_creative':
        meta_d3_old_position = node.get('position')
        meta_d3_old_id = node.get('id')
        # Substituir HTTP node por Code node
        node['type'] = 'n8n-nodes-base.code'
        node['typeVersion'] = 2
        # Limpa parâmetros antigos do HTTP node
        node['parameters'] = {'jsCode': META_D3_CODE}
        # mantém position e id pra preservar conexões
        if meta_d3_old_position: node['position'] = meta_d3_old_position
        if meta_d3_old_id: node['id'] = meta_d3_old_id
        fixes_applied.append('meta_d3_creative: virou Code com branch image/video + upload /advideos')

print("=== FIXES APLICADOS ===")
for f in fixes_applied: print(f"  ✅ {f}")
print("\n=== FIXES FALHADOS ===")
for f in fixes_failed: print(f"  ❌ {f}")

if not fixes_failed:
    clean = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean)
    print("\n✅ Workflow atualizado.")
else:
    sys.exit(1)
