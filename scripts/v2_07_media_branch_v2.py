#!/usr/bin/env python3
"""Refator do branch de mídia state-aware."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


MEDIA_UPSERT_QUERY = """INSERT INTO auto_ads.conversas (telefone, criativo_url, historico, estado_json)
VALUES (
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
)
ON CONFLICT (telefone) DO UPDATE
  SET criativo_url = EXCLUDED.criativo_url,
      historico = COALESCE(auto_ads.conversas.historico, '') || EXCLUDED.historico,
      estado_json = jsonb_set(
        auto_ads.conversas.estado_json,
        '{criativo}',
        EXCLUDED.estado_json -> 'criativo'
      ),
      ultima_atualizacao = NOW()"""


MEDIA_SELECT_CONVERSA_QUERY = (
    "SELECT $1::text AS telefone, "
    "COALESCE((SELECT historico FROM auto_ads.conversas WHERE telefone = $1), '') AS historico, "
    "COALESCE((SELECT estado_json FROM auto_ads.conversas WHERE telefone = $1), "
    "'{\"etapa_atual\":\"coletando_info\",\"criativo\":{\"recebido\":false},\"brief\":{},\"ultima_tentativa\":null}'::jsonb) AS estado_json"
)


DECIDE_ACAO_MEDIA_CODE = """// Decide o que fazer depois de receber mídia
const conversaAnterior = $('media_select_conversa').first().json;
let estadoAntes = conversaAnterior.estado_json;
if (typeof estadoAntes === 'string') { try { estadoAntes = JSON.parse(estadoAntes); } catch(e) { estadoAntes = {etapa_atual: 'coletando_info'}; } }

const etapaAntes = estadoAntes?.etapa_atual || 'coletando_info';
const ultMotivo = estadoAntes?.ultima_tentativa?.motivo || '';
const criativoEraMotivo = /criativo|imagem|image|video/i.test(ultMotivo);

const triggerRetry = (etapaAntes === 'falhou_dado') && criativoEraMotivo;

return [{
  json: {
    triggerRetry,
    etapaAntes,
    estadoAntes,
    telefone: $('media_normalize_phone').first().json.telefone_normalizado,
    criativo_url: $('media_download').first().json.fileURL || ''
  }
}];
"""


BUILD_MEDIA_RESPONSE_CODE = """// Msg condicional baseada em estado anterior + brief completo
const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};
const brief = estadoAntes.brief || {};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);

let text;
if (d.triggerRetry) {
  text = 'Recebi o novo criativo ✓ — rodando RETRY automático agora...';
} else if (estadoAntes.etapa_atual === 'ativa') {
  text = 'Recebi o criativo ✓ — mas você já tem campanha ativa. Quer fazer NOVA CAMPANHA?';
} else if (estadoAntes.etapa_atual === 'falhou_dado') {
  const motivo = estadoAntes.ultima_tentativa?.motivo || 'algum problema';
  text = 'Recebi seu criativo ✓ — mas a última tentativa falhou por: ' + motivo + '. Corrige isso e manda RETRY.';
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


MEDIA_SEND_TEXT_VALUE = "={{ $('build_media_response').item.json.text }}"
MEDIA_SEND_NUMBER_VALUE = "={{ $('build_media_response').item.json.telefone }}"


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'media_select_conversa' not in nb:
        wf['nodes'].append({
            'id': 'media_select_conversa', 'name': 'media_select_conversa',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [2200, 600],
            'parameters': {
                'operation': 'executeQuery',
                'query': MEDIA_SELECT_CONVERSA_QUERY,
                'options': {'queryReplacement': "={{ $('media_normalize_phone').item.json.telefone_normalizado }}"}
            },
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + media_select_conversa adicionado')

    if 'media_upsert_criativo' in nb:
        nb['media_upsert_criativo']['parameters']['query'] = MEDIA_UPSERT_QUERY
        nb['media_upsert_criativo']['parameters']['options'] = {}
        print('  ↻ media_upsert_criativo escreve estado_json.criativo')

    if 'decide_acao_media' not in nb:
        wf['nodes'].append({
            'id': 'decide_acao_media', 'name': 'decide_acao_media',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2600, 600],
            'parameters': {'language': 'javaScript', 'jsCode': DECIDE_ACAO_MEDIA_CODE}
        })
        print('  + decide_acao_media adicionado')

    if 'build_media_response' not in nb:
        wf['nodes'].append({
            'id': 'build_media_response', 'name': 'build_media_response',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2800, 600],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_MEDIA_RESPONSE_CODE}
        })
        print('  + build_media_response adicionado')

    if 'media_send_confirma' in nb:
        for p in nb['media_send_confirma']['parameters'].get('bodyParameters', {}).get('parameters', []):
            if p.get('name') == 'text': p['value'] = MEDIA_SEND_TEXT_VALUE
            if p.get('name') == 'number': p['value'] = MEDIA_SEND_NUMBER_VALUE
        print('  ↻ media_send_confirma usa build_media_response')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 7 aplicada')


if __name__ == '__main__':
    main()
