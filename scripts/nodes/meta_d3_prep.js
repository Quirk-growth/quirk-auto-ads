// Prepara o binário do criativo pro nó NATIVO fazer o multipart.
// (Code node do n8n NÃO consegue multipart binário — só o HTTP Request nativo.
//  Aqui a gente baixa os bytes com Bearer e entrega como binary do n8n.)
const v = $('validate').first().json;
const adAccountId = v.cliente.ad_account_id;
const pageId = v.cliente.page_id;
const campNome = v.json_extrator.campanha.nome;
const copy = v.json_extrator.anuncio.copy;
const token = $('load_meta_token').first().json.valor;
const apiBase = 'https://graph.facebook.com/v25.0';

let media_id = '', mimetype = '';
try {
  media_id = v.estado?.criativo?.media_id || '';
  mimetype = v.estado?.criativo?.mimetype || v.estado?.criativo?.mime_type || '';
} catch (e) {}

if (!media_id) {
  return [{ json: { error: 'criativo_sem_media_id', adAccountId, pageId, campNome, copy, token, isVideo: false } }];
}

// media_id -> URL fresca -> download dos bytes (download funciona no code node)
const meta = await this.helpers.httpRequest({ method: 'GET', url: `${apiBase}/${media_id}?access_token=${encodeURIComponent(token)}`, returnFullResponse: false });
const m = (typeof meta === 'string') ? JSON.parse(meta) : meta;
const mime = m.mime_type || mimetype || 'application/octet-stream';
const bin = await this.helpers.httpRequest({ method: 'GET', url: m.url, headers: { Authorization: `Bearer ${token}` }, encoding: 'arraybuffer', returnFullResponse: false });
const buffer = Buffer.from(bin);
const isVideo = /^video\//i.test(mime);
const bd = await this.helpers.prepareBinaryData(buffer, isVideo ? 'criativo.mp4' : 'criativo.jpg', mime);

return [{ json: { adAccountId, pageId, campNome, copy, token, mime, isVideo, media_id }, binary: { data: bd } }];
