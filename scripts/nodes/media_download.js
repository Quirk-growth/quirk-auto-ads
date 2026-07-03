// Cloud API: media_get_url devolve {url, mime_type}. Emite fileURL/mimetype (compat)
// + media_id (fonte de verdade pra re-buscar o criativo na hora de criar o anúncio).
const g = $input.first().json || {};
let media_id = '';
try { media_id = $('media_normalize_phone').item.json.message_id || ''; } catch (e) {}
return [{ json: { fileURL: g.url || '', mimetype: g.mime_type || '', media_id } }];
