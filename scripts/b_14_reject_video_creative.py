#!/usr/bin/env python3
"""
Bloqueia vídeo no branch de mídia (MVP: só aceita foto JPG/PNG).

Meta API: meta_d3_creative usa object_story_spec.link_data.picture, que só aceita
imagem estática. Vídeo exige pipeline separado (upload /advideos + wait processed +
creative com video_data + thumbnail). Fora de escopo no MVP.

Fix:
1. decide_acao_media detecta mimetype não-imagem e seta video_rejeitado=true
2. build_media_response v4: se video_rejeitado, manda msg pedindo foto e NÃO grava
   o criativo no estado (mantém o anterior, se houver)
3. media_upsert_criativo: condiciona o INSERT pra só rodar se for imagem
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


DECIDE_ACAO_MEDIA_V3 = """// Decide o que fazer depois de receber mídia
const conversaAnterior = $('media_select_conversa').first().json;
let estadoAntes = conversaAnterior.estado_json;
if (typeof estadoAntes === 'string') { try { estadoAntes = JSON.parse(estadoAntes); } catch(e) { estadoAntes = {etapa_atual: 'coletando_info'}; } }

const etapaAntes = estadoAntes?.etapa_atual || 'coletando_info';
const ultMotivo = estadoAntes?.ultima_tentativa?.motivo || '';
const criativoEraMotivo = /criativo|imagem|image|video|tipo de imagem/i.test(ultMotivo);

// NOVO: bloqueia vídeo (Meta API d3_creative só aceita imagem estática)
const mimetype = $('media_download').first().json.mimetype || '';
const eh_imagem = /^image\\//i.test(mimetype);
const eh_video = /^video\\//i.test(mimetype);
const video_rejeitado = eh_video || (!eh_imagem && mimetype.length > 0);

// Detecta duplicado recente (< 2 min)
const criativoAnt = estadoAntes?.criativo;
let duplicado_recente = false;
if (criativoAnt?.recebido && criativoAnt?.recebido_em) {
  const dtMs = Date.now() - new Date(criativoAnt.recebido_em).getTime();
  duplicado_recente = dtMs < 120000;
}

const triggerRetry = (etapaAntes === 'falhou_dado') && criativoEraMotivo && eh_imagem;

return [{
  json: {
    triggerRetry,
    duplicado_recente,
    video_rejeitado,
    eh_imagem,
    mimetype,
    etapaAntes,
    estadoAntes,
    telefone: $('media_normalize_phone').first().json.telefone_normalizado,
    criativo_url: $('media_download').first().json.fileURL || ''
  }
}];
"""


BUILD_MEDIA_RESPONSE_V4 = """const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};
const brief = estadoAntes.brief || {};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);

let text;

// NOVO: vídeo rejeitado tem prioridade máxima
if (d.video_rejeitado) {
  text = '⚠️ Por enquanto só aceito FOTO no criativo (JPG ou PNG). Vídeo ainda não tá suportado. Manda uma imagem do imóvel.';
} else if (d.duplicado_recente) {
  text = '✓ Recebi seu criativo (atualizado).';
} else if (d.triggerRetry) {
  text = 'Recebi o novo criativo ✓ — manda SUBIR DENOVO pra tentar com ele.';
} else if (estadoAntes.etapa_atual === 'ativa') {
  text = 'Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer NOVA CAMPANHA?';
} else if (estadoAntes.etapa_atual === 'falhou_dado') {
  const motivo = estadoAntes.ultima_tentativa?.motivo || 'algum problema';
  text = 'Recebi seu criativo ✓ — mas a última tentativa falhou por: ' + motivo + '. Corrige isso e manda SUBIR DENOVO.';
} else if (briefCompleto) {
  text = 'Recebi seu criativo ✓ — tudo pronto. Manda CONFIRMAR quando quiser subir.';
} else {
  const faltantes = obrig.filter(k => !brief[k]).join(', ');
  text = 'Recebi seu criativo ✓ — ainda preciso de: ' + faltantes + '. Me manda esses dados pra fechar.';
}

return [{
  json: {
    text,
    telefone: d.telefone
  }
}];
"""


# media_upsert_criativo condicional: só grava se for imagem
# Solução: adicionar guard SQL — só UPDATE se mimetype começa com image/
MEDIA_UPSERT_GUARDED = """INSERT INTO auto_ads.conversas (telefone, criativo_url, historico, estado_json)
SELECT
  '{{ $('media_normalize_phone').item.json.telefone_normalizado }}',
  '{{ ($('media_download').item.json.fileURL || '').replace(/'/g, "''") }}',
  '|||TURN|||[SISTEMA: criativo recebido em ' || NOW()::TEXT || ']',
  jsonb_set(
    COALESCE((SELECT estado_json FROM auto_ads.conversas WHERE telefone = '{{ $('media_normalize_phone').item.json.telefone_normalizado }}'), '{"etapa_atual":"coletando_info","brief":{},"ultima_tentativa":null}'::jsonb),
    '{criativo}',
    jsonb_build_object(
      'recebido', true,
      'url', '{{ ($('media_download').item.json.fileURL || '').replace(/'/g, "''") }}',
      'mimetype', '{{ ($('media_download').item.json.mimetype || '').replace(/'/g, "''") }}',
      'recebido_em', NOW()::TEXT
    )
  )
WHERE '{{ ($('media_download').item.json.mimetype || '').replace(/'/g, "''") }}' LIKE 'image/%'
ON CONFLICT (telefone) DO UPDATE
  SET criativo_url = EXCLUDED.criativo_url,
      historico = COALESCE(auto_ads.conversas.historico, '') || EXCLUDED.historico,
      estado_json = jsonb_set(
        auto_ads.conversas.estado_json,
        '{criativo}',
        EXCLUDED.estado_json -> 'criativo'
      ),
      ultima_atualizacao = NOW()"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['decide_acao_media']['parameters']['jsCode'] = DECIDE_ACAO_MEDIA_V3
    print('  ↻ decide_acao_media v3 (detecta video_rejeitado)')

    nb['build_media_response']['parameters']['jsCode'] = BUILD_MEDIA_RESPONSE_V4
    print('  ↻ build_media_response v4 (msg pra vídeo)')

    nb['media_upsert_criativo']['parameters']['query'] = MEDIA_UPSERT_GUARDED
    print('  ↻ media_upsert_criativo: só grava se mimetype LIKE image/%')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Vídeo bloqueado no branch de mídia (MVP só foto)')


if __name__ == '__main__':
    main()
