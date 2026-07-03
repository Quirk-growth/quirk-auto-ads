// FINISH do criativo: recebe o upload feito pelo nó nativo meta_d3_upload
// (video_id ou image_hash) e cria o adcreative. Vídeo: espera processar + pega thumbnail.
const prep = $('meta_d3_prep').first().json;
if (prep.error) return [{ json: { error: prep.error } }];

const token = prep.token, adAccountId = prep.adAccountId, pageId = prep.pageId;
const campNome = prep.campNome, copy = prep.copy;
const apiBase = 'https://graph.facebook.com/v25.0';
const up = $('meta_d3_upload').first().json;

async function getJson(url) {
  const r = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
  return (typeof r === 'string') ? JSON.parse(r) : r;
}
async function postJson(url, body) {
  try {
    return await this.helpers.httpRequest({ method: 'POST', url, headers: { 'Content-Type': 'application/json' }, body, json: true, returnFullResponse: false });
  } catch (e) {
    const d = e?.response?.data || e?.response?.body || e?.message || String(e);
    throw new Error('Meta API error: ' + (typeof d === 'string' ? d : JSON.stringify(d)));
  }
}

if (prep.isVideo) {
  const videoId = up && up.id;
  if (!videoId) return [{ json: { error: 'video_upload_falhou', resp: up } }];

  // espera o vídeo processar
  let st = null;
  for (let i = 0; i < 8; i++) {
    await new Promise(r => setTimeout(r, 4000));
    const s = await getJson.call(this, `${apiBase}/${videoId}?fields=status&access_token=${encodeURIComponent(token)}`);
    st = s?.status?.video_status || s?.status;
    if (st === 'ready') break;
    if (st === 'error') return [{ json: { error: 'video_processing_error', video_id: videoId, status: s } }];
  }
  if (st !== 'ready') return [{ json: { error: 'video_processing_timeout', video_id: videoId } }];

  // thumbnail (obrigatória no video_data)
  let thumb = null;
  try {
    const th = await getJson.call(this, `${apiBase}/${videoId}/thumbnails?access_token=${encodeURIComponent(token)}`);
    const list = th.data || [];
    const pref = list.find(t => t.is_preferred) || list[0];
    if (pref && pref.uri) thumb = pref.uri;
  } catch (e) {}
  if (!thumb) return [{ json: { error: 'video_sem_thumbnail', video_id: videoId } }];

  const videoData = {
    video_id: videoId, title: campNome, message: copy, image_url: thumb,
    call_to_action: { type: 'WHATSAPP_MESSAGE', value: { app_destination: 'WHATSAPP' } },
  };
  const cr = await postJson.call(this, `${apiBase}/act_${adAccountId}/adcreatives`, {
    name: campNome, object_story_spec: { page_id: pageId, video_data: videoData }, access_token: token,
  });
  if (!cr.id) return [{ json: { error: 'video_creative_falhou', resp: cr } }];
  return [{ json: { id: cr.id, tipo_criativo: 'video', video_id: videoId } }];

} else {
  const hash = (up && up.images) ? Object.values(up.images)[0]?.hash : null;
  if (!hash) return [{ json: { error: 'image_upload_falhou', resp: up } }];
  const linkData = {
    message: copy, image_hash: hash,
    call_to_action: { type: 'WHATSAPP_MESSAGE', value: { app_destination: 'WHATSAPP' } },
  };
  const cr = await postJson.call(this, `${apiBase}/act_${adAccountId}/adcreatives`, {
    name: campNome, object_story_spec: { page_id: pageId, link_data: linkData }, access_token: token,
  });
  if (!cr.id) return [{ json: { error: 'image_creative_falhou', resp: cr } }];
  return [{ json: { id: cr.id, tipo_criativo: 'image', image_hash: hash } }];
}
