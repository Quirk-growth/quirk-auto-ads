#!/usr/bin/env python3
"""update_db_campanha + audit_gestao + reset_gestao + build_gestao_confirmation_msg."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


UPDATE_DB_CAMPANHA_QUERY = """UPDATE auto_ads.campanhas
SET status = CASE
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'PAUSAR' THEN 'PAUSED'
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'REATIVAR' THEN 'ACTIVE'
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'ENCERRAR' THEN 'ARCHIVED'
      ELSE status
    END,
    json_extrator = CASE
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' = 'ALTERAR_VERBA' THEN
        jsonb_set(json_extrator, '{campanha,verba_diaria}', to_jsonb({{ $('check_gestao_result').item.json.novo_valor?.valor || 0 }}))
      WHEN '{{ $('check_gestao_result').item.json.verbo }}' IN ('ALTERAR_PUBLICO','ALTERAR_GEO') THEN
        jsonb_set(json_extrator, '{targeting_meta}', '{{ JSON.stringify($('build_targeting_atualizado').item?.json?.targeting || {}).replace(/'/g, "''") }}'::jsonb)
      ELSE json_extrator
    END,
    ultima_alteracao = NOW()
WHERE id = {{ $('check_gestao_result').item.json.selecionada.campanha_id_db }}"""


AUDIT_GESTAO_QUERY = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
VALUES (
  '{{ $('check_gestao_result').item.json.telefone }}',
  'gestao_{{ $('check_gestao_result').item.json.verbo.toLowerCase() }}',
  jsonb_build_object(
    'campanha_id_db', {{ $('check_gestao_result').item.json.selecionada.campanha_id_db }},
    'campaign_id_meta', '{{ $('check_gestao_result').item.json.selecionada.campaign_id_meta || '' }}',
    'adset_id_meta', '{{ $('check_gestao_result').item.json.selecionada.adset_id_meta || '' }}',
    'antes', '{{ JSON.stringify({status: $('check_gestao_result').item.json.selecionada.status, verba: $('check_gestao_result').item.json.selecionada.verba_atual_reais, publico: $('check_gestao_result').item.json.selecionada.publico_atual, geo_cidade: $('check_gestao_result').item.json.selecionada.geo_cidade_atual, geo_raio: $('check_gestao_result').item.json.selecionada.geo_raio_atual}).replace(/'/g, "''") }}'::jsonb,
    'depois', '{{ JSON.stringify($('check_gestao_result').item.json.novo_valor || {}).replace(/'/g, "''") }}'::jsonb,
    'ok', {{ $('check_gestao_result').item.json.ok }},
    'classe_erro', '{{ $('check_gestao_result').item.json.classe || '' }}',
    'motivo_erro', '{{ ($('check_gestao_result').item.json.motivo || '').replace(/'/g, "''") }}'
  )
)"""


RESET_GESTAO_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(estado_json, '{gestao}', 'null'::jsonb),
  '{etapa_atual}',
  to_jsonb(CASE
    WHEN {{ $('check_gestao_result').item.json.ok }} THEN 'ativa'
    ELSE 'falhou_dado'
  END::text)
)
WHERE telefone = '{{ $('check_gestao_result').item.json.telefone }}'"""


BUILD_GESTAO_CONFIRMATION_CODE = """const r = $('check_gestao_result').first().json;
const v = r.verbo;
const sel = r.selecionada;
const nv = r.novo_valor || {};

let text;

if (r.ok) {
  if (v === 'PAUSAR') text = `✓ "${sel.nome}" pausada.`;
  else if (v === 'REATIVAR') text = `✓ "${sel.nome}" reativada.`;
  else if (v === 'ENCERRAR') text = `✓ "${sel.nome}" encerrada e arquivada.`;
  else if (v === 'ALTERAR_VERBA') text = `✓ Verba de "${sel.nome}" atualizada pra R$ ${nv.valor}/dia.`;
  else if (v === 'ALTERAR_PUBLICO') text = `✓ Público de "${sel.nome}" atualizado.`;
  else if (v === 'ALTERAR_GEO') text = `✓ Geo de "${sel.nome}" atualizado.`;
  text += '\\n\\nPode levar alguns minutos pra propagar no Meta.';
} else {
  const classe = r.classe;
  const motivo = r.motivo || 'erro desconhecido';
  if (classe === 'infra') {
    text = `⚠️ Problema técnico do Meta. Tenta de novo daqui a alguns minutos com "SUBIR DENOVO" ou CANCELAR.`;
  } else {
    text = `⚠️ Não consegui executar: ${motivo}\\n\\nManda SUBIR DENOVO pra tentar novamente OU CANCELAR.`;
  }
}

return [{
  json: {
    text,
    telefone: r.telefone
  }
}];
"""


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    if 'update_db_campanha' not in nb:
        wf['nodes'].append({
            'id': 'update_db_campanha', 'name': 'update_db_campanha',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3400, 100],
            'parameters': {'operation': 'executeQuery', 'query': UPDATE_DB_CAMPANHA_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + update_db_campanha adicionado')

    if 'audit_gestao' not in nb:
        wf['nodes'].append({
            'id': 'audit_gestao', 'name': 'audit_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3600, 100],
            'parameters': {'operation': 'executeQuery', 'query': AUDIT_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + audit_gestao adicionado')

    if 'reset_gestao' not in nb:
        wf['nodes'].append({
            'id': 'reset_gestao', 'name': 'reset_gestao',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3800, 100],
            'parameters': {'operation': 'executeQuery', 'query': RESET_GESTAO_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_gestao adicionado')

    if 'build_gestao_confirmation_msg' not in nb:
        wf['nodes'].append({
            'id': 'build_gestao_confirmation_msg', 'name': 'build_gestao_confirmation_msg',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [4000, 100],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_GESTAO_CONFIRMATION_CODE}
        })
        print('  + build_gestao_confirmation_msg adicionado')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 8 aplicada')


if __name__ == '__main__':
    main()
