#!/usr/bin/env python3
"""Rewire global do workflow v2 + remove classifier e send_falha_validacao."""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def load_prompt_with_state_placeholder():
    with open('/Users/renanreal/quirk_auto_ads/prompts/agente_principal.md') as f:
        return f.read()


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # ─── 1. build_agente_body v2 ───
    sys_template = load_prompt_with_state_placeholder()
    sys_template_quoted = json.dumps(sys_template)

    new_agente_body = f"""const systemTemplate = {sys_template_quoted};
const estado = $('load_estado').first().json.estado;
const intent = $('classify_intent').first().json.intent || 'OUTRO';
const historico = String($('load_estado').first().json.historico || '').trim();
const novaMsg = String($('normalize_phone').first().json.mensagem_texto || '').trim();

const brief = estado.brief || {{}};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const preenchidos = obrig.filter(k => !!brief[k]);
const faltantes = obrig.filter(k => !brief[k]);
const ult = estado.ultima_tentativa;

let estadoBlock = `Etapa atual: ${{estado.etapa_atual}}
Criativo recebido: ${{estado.criativo?.recebido ? 'sim (' + estado.criativo.url + ')' : 'não'}}
Brief preenchido: ${{preenchidos.join(', ') || '(nada)'}}
Brief faltante: ${{faltantes.join(', ') || '(nada)'}}
Última tentativa: ${{ult ? (ult.resultado + (ult.motivo ? ': ' + ult.motivo : '')) : 'nenhuma'}}
Tentativas count: ${{ult?.tentativas_count || 0}}
Intent detectado (msg atual): ${{intent}}`;

if (estado.etapa_atual === 'ativa' && ult?.campaign_id) {{
  estadoBlock += `\\nCampanha ATIVA: campaign_id=${{ult.campaign_id}}`;
}}

const system = systemTemplate.replace('{{{{ESTADO_BLOCK}}}}', estadoBlock);

let userContent;
if (historico) {{
  userContent = `Histórico da conversa até agora:\\n${{historico}}\\n\\nNova mensagem do cliente: ${{novaMsg}}`;
}} else {{
  userContent = novaMsg;
}}

return [{{
  json: {{
    model: "claude-sonnet-4-5",
    max_tokens: 1500,
    temperature: 0.3,
    system,
    messages: [{{ role: "user", content: userContent }}]
  }}
}}];
"""
    nb['build_agente_body']['parameters']['jsCode'] = new_agente_body
    print('  ↻ build_agente_body v2 (injeta [ESTADO])')

    # ─── 2. switch_intent ───
    if 'switch_intent' not in nb:
        wf['nodes'].append({
            'id': 'switch_intent', 'name': 'switch_intent',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [1500, 100],
            'parameters': {
                'rules': {
                    'values': [
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('classify_intent').item.json.intent }}", 'rightValue': 'CONFIRMAR', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'CONFIRMAR'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('classify_intent').item.json.intent }}", 'rightValue': 'RETRY', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'RETRY'},
                        {'conditions': {'options': {'caseSensitive': True, 'typeValidation': 'loose'}, 'combinator': 'and',
                          'conditions': [{'leftValue': "={{ $('classify_intent').item.json.intent }}", 'rightValue': 'NOVA_CAMPANHA', 'operator': {'type': 'string', 'operation': 'equals'}}]},
                         'renameOutput': True, 'outputKey': 'NOVA'}
                    ]
                },
                'options': {'fallbackOutput': 'extra'}
            }
        })
        print('  + switch_intent adicionado')

    # ─── 3. Persistência após cada step ───
    persist_query_after_meta = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  jsonb_set(
    estado_json,
    '{etapa_atual}',
    to_jsonb('{{ $('check_meta_results').item.json.ok ? "ativa" : ($('check_meta_results').item.json.classe === "infra" ? "falhou_infra" : "falhou_dado") }}'::text)
  ),
  '{ultima_tentativa}',
  jsonb_build_object(
    'timestamp', NOW()::TEXT,
    'resultado', '{{ $('check_meta_results').item.json.ok ? "ok" : ("erro_" + $('check_meta_results').item.json.classe) }}',
    'motivo', '{{ ($('check_meta_results').item.json.motivo || '').replace(/'/g, "''") }}',
    'campaign_id', {{ $('check_meta_results').item.json.campaign_id ? "'" + $('check_meta_results').item.json.campaign_id + "'" : 'NULL' }},
    'adset_id', {{ $('check_meta_results').item.json.adset_id ? "'" + $('check_meta_results').item.json.adset_id + "'" : 'NULL' }},
    'creative_id', {{ $('check_meta_results').item.json.creative_id ? "'" + $('check_meta_results').item.json.creative_id + "'" : 'NULL' }},
    'ad_id', {{ $('check_meta_results').item.json.ad_id ? "'" + $('check_meta_results').item.json.ad_id + "'" : 'NULL' }},
    'tentativas_count', {{ $('check_meta_results').item.json.tentativas_count }}
  )
)
WHERE telefone = '{{ $('check_meta_results').item.json.telefone }}'"""

    if 'persist_estado_apos_meta' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_apos_meta', 'name': 'persist_estado_apos_meta',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [5080, 100],
            'parameters': {'operation': 'executeQuery', 'query': persist_query_after_meta, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_apos_meta adicionado')

    persist_query_etapa = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{etapa_atual}',
  to_jsonb('{{ $('update_estado_etapa').item.json.estado.etapa_atual }}'::text)
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'persist_estado_etapa' not in nb:
        wf['nodes'].append({
            'id': 'persist_estado_etapa', 'name': 'persist_estado_etapa',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1800, 250],
            'parameters': {'operation': 'executeQuery', 'query': persist_query_etapa, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_estado_etapa adicionado')

    persist_brief_query = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(
  estado_json,
  '{brief}',
  '{{ JSON.stringify($('merge_brief').item.json.estado.brief).replace(/'/g, "''") }}'::jsonb
)
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'persist_brief' not in nb:
        wf['nodes'].append({
            'id': 'persist_brief', 'name': 'persist_brief',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3300, 50],
            'parameters': {'operation': 'executeQuery', 'query': persist_brief_query, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + persist_brief adicionado')

    reset_estado_query = """UPDATE auto_ads.conversas
SET estado_json = '{"etapa_atual":"coletando_info","criativo":{"recebido":false},"brief":{},"ultima_tentativa":null}'::jsonb
WHERE telefone = '{{ $('normalize_phone').item.json.telefone_normalizado }}'"""

    if 'reset_estado_nova' not in nb:
        wf['nodes'].append({
            'id': 'reset_estado_nova', 'name': 'reset_estado_nova',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [1700, 350],
            'parameters': {'operation': 'executeQuery', 'query': reset_estado_query, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_estado_nova adicionado')

    # ─── 4. Reconnect fluxo principal ───
    wf['connections']['select_conversa'] = {'main': [[{'node': 'load_estado', 'type': 'main', 'index': 0}]]}
    wf['connections']['load_estado'] = {'main': [[{'node': 'classify_intent', 'type': 'main', 'index': 0}]]}
    wf['connections']['classify_intent'] = {'main': [[{'node': 'switch_intent', 'type': 'main', 'index': 0}]]}

    wf['connections']['switch_intent'] = {
        'main': [
            [{'node': 'build_extrator_body', 'type': 'main', 'index': 0}],   # CONFIRMAR
            [{'node': 'build_extrator_body', 'type': 'main', 'index': 0}],   # RETRY
            [{'node': 'reset_estado_nova', 'type': 'main', 'index': 0}],     # NOVA
            [{'node': 'build_agente_body', 'type': 'main', 'index': 0}]      # OUTRO
        ]
    }

    wf['connections']['extrator'] = {'main': [[{'node': 'parse_extrator', 'type': 'main', 'index': 0}]]}
    wf['connections']['parse_extrator'] = {'main': [[{'node': 'merge_brief', 'type': 'main', 'index': 0}]]}
    wf['connections']['merge_brief'] = {'main': [[{'node': 'persist_brief', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_brief'] = {'main': [[{'node': 'validate', 'type': 'main', 'index': 0}]]}

    wf['connections']['check_meta_results'] = {'main': [[{'node': 'if_pode_retry_infra', 'type': 'main', 'index': 0}]]}
    wf['connections']['if_pode_retry_infra'] = {
        'main': [
            [{'node': 'wait_30s', 'type': 'main', 'index': 0}],
            [{'node': 'persist_estado_apos_meta', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['wait_30s'] = {'main': [[{'node': 'meta_d1_campaign', 'type': 'main', 'index': 0}]]}

    wf['connections']['persist_estado_apos_meta'] = {'main': [[{'node': 'insert_campanha', 'type': 'main', 'index': 0}]]}
    wf['connections']['insert_campanha'] = {'main': [[{'node': 'audit_campanha_criada', 'type': 'main', 'index': 0}]]}
    wf['connections']['audit_campanha_criada'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    wf['connections']['audit_validacao_falhou'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    wf['connections']['build_agente_body'] = {'main': [[{'node': 'agente_principal', 'type': 'main', 'index': 0}]]}
    wf['connections']['agente_principal'] = {'main': [[{'node': 'update_estado_etapa', 'type': 'main', 'index': 0}]]}
    wf['connections']['update_estado_etapa'] = {'main': [[{'node': 'persist_estado_etapa', 'type': 'main', 'index': 0}]]}
    wf['connections']['persist_estado_etapa'] = {'main': [[{'node': 'build_historico', 'type': 'main', 'index': 0}]]}

    wf['connections']['reset_estado_nova'] = {'main': [[{'node': 'build_agente_body', 'type': 'main', 'index': 0}]]}

    # ─── 5. Reconnect branch de mídia ───
    wf['connections']['media_if_cadastrado'] = {
        'main': [
            [{'node': 'media_select_conversa', 'type': 'main', 'index': 0}],
            [{'node': 'send_nao_cadastrado', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['media_select_conversa'] = {'main': [[{'node': 'media_download', 'type': 'main', 'index': 0}]]}
    wf['connections']['media_download'] = {'main': [[{'node': 'media_upsert_criativo', 'type': 'main', 'index': 0}]]}
    wf['connections']['media_upsert_criativo'] = {'main': [[{'node': 'decide_acao_media', 'type': 'main', 'index': 0}]]}
    wf['connections']['decide_acao_media'] = {'main': [[{'node': 'build_media_response', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_media_response'] = {'main': [[{'node': 'media_send_confirma', 'type': 'main', 'index': 0}]]}

    # ─── 6. Remoção de deprecated ───
    deprecated = ['classifier', 'build_classifier_body', 'send_falha_validacao']
    for d in deprecated:
        if d in nb:
            wf['nodes'] = [n for n in wf['nodes'] if n['name'] != d]
            wf['connections'].pop(d, None)
            for src, conn in list(wf['connections'].items()):
                if 'main' in conn:
                    for i, out in enumerate(conn['main']):
                        if isinstance(out, list):
                            conn['main'][i] = [c for c in out if c.get('node') != d]
            print(f'  − {d} removido')

    n8n_api.update_workflow(
        WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'],
        settings=wf.get('settings', {'executionOrder': 'v1'})
    )
    print('\n✓ Task 8 aplicada — fluxo v2 reconectado')


if __name__ == '__main__':
    main()
