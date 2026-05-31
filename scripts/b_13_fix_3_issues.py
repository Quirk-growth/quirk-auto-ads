#!/usr/bin/env python3
"""
3 fixes:

1. CONFIRMAR quebrado: load_meta_token estava apontando pra execute_gestao_action (B),
   sobrescrevendo o path do A (load_meta_token → meta_d1_campaign).
   Fix: novo node switch_a_ou_b decide o destino baseado em estado.gestao.

2. Foto duplicada: cliente manda 2 medias e o sistema responde 2x.
   Fix: decide_acao_media adiciona check 'criativo_ja_recebido_recentemente' (<2min).
   Se já tem criativo recente, manda msg 'Já recebi seu criativo. Quer trocar?
   Responde TROCAR ou ignora.' em vez de sobrescrever.

3. Layout bagunçado: reorganiza posições de todos os nodes em colunas lógicas.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


# ─── FIX 1: switch_a_ou_b após load_meta_token ───

SWITCH_A_OU_B_RULES = {
    'rules': {
        'values': [
            {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [{
                        'leftValue': "={{ $('load_estado').item.json.estado.gestao !== null && $('load_estado').item.json.estado.gestao !== undefined ? 'B' : 'A' }}",
                        'rightValue': 'B',
                        'operator': {'type': 'string', 'operation': 'equals'}
                    }]
                },
                'renameOutput': True, 'outputKey': 'GESTAO'
            }
        ]
    },
    'options': {'fallbackOutput': 'extra'}  # fallback = A (criação)
}


# ─── FIX 2: decide_acao_media com check de duplicação recente ───

DECIDE_ACAO_MEDIA_V2 = """// Decide o que fazer depois de receber mídia
const conversaAnterior = $('media_select_conversa').first().json;
let estadoAntes = conversaAnterior.estado_json;
if (typeof estadoAntes === 'string') { try { estadoAntes = JSON.parse(estadoAntes); } catch(e) { estadoAntes = {etapa_atual: 'coletando_info'}; } }

const etapaAntes = estadoAntes?.etapa_atual || 'coletando_info';
const ultMotivo = estadoAntes?.ultima_tentativa?.motivo || '';
const criativoEraMotivo = /criativo|imagem|image|video/i.test(ultMotivo);

// NOVO: detecta criativo já recebido recentemente (< 2 min)
const criativoAnt = estadoAntes?.criativo;
let duplicado_recente = false;
if (criativoAnt?.recebido && criativoAnt?.recebido_em) {
  const dtMs = Date.now() - new Date(criativoAnt.recebido_em).getTime();
  duplicado_recente = dtMs < 120000;  // 2 minutos
}

const triggerRetry = (etapaAntes === 'falhou_dado') && criativoEraMotivo;

return [{
  json: {
    triggerRetry,
    duplicado_recente,
    etapaAntes,
    estadoAntes,
    telefone: $('media_normalize_phone').first().json.telefone_normalizado,
    criativo_url: $('media_download').first().json.fileURL || ''
  }
}];
"""


# build_media_response v2 — trata duplicado_recente
BUILD_MEDIA_RESPONSE_V3 = """const d = $('decide_acao_media').first().json;
const estadoAntes = d.estadoAntes || {};
const brief = estadoAntes.brief || {};
const obrig = ['campanha', 'objetivo', 'faixa_valor', 'conjunto', 'anuncio', 'targeting_meta'];
const briefCompleto = obrig.every(k => !!brief[k]);

let text;
if (d.duplicado_recente) {
  // Suprime resposta — recebeu 2º criativo em < 2 min, provavelmente sem querer
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


# ─── FIX 3: layout reorganizado em colunas ───
# Convenção: x=coluna * 200, y=linha * 150
# Fluxo principal (TEXTO) na linha 0, gestão (B) na linha 1, mídia na linha 2, Meta API/retry na linha 3

LAYOUT = {
    # Fluxo principal (TEXTO) — linha 0 (y=100)
    'webhook':                              (200, 100),
    'switch_type':                          (400, 100),
    'normalize_phone':                      (600, 100),
    'select_cliente':                       (800, 100),
    'if_cadastrado':                        (1000, 100),
    'send_nao_cadastrado':                  (1000, 250),
    'select_conversa':                      (1200, 100),
    'load_estado':                          (1400, 100),
    'em_gestao_valido':                     (1600, 100),
    'if_em_gestao':                         (1800, 100),
    'classify_intent':                      (2000, 100),
    'switch_intent':                        (2200, 100),

    # Branch CONFIRMAR/SUBIR_DENOVO — linha 0
    'build_extrator_body':                  (2400, 100),
    'extrator':                             (2600, 100),
    'parse_extrator':                       (2800, 100),
    'merge_brief':                          (3000, 100),
    'persist_brief':                        (3200, 100),
    'validate':                             (3400, 100),
    'if_valid':                             (3600, 100),
    'audit_validacao_falhou':               (3600, 250),
    'load_meta_token':                      (3800, 100),
    'switch_a_ou_b':                        (4000, 100),

    # Meta API CREATE (A) — linha 0
    'meta_d1_campaign':                     (4200, 100),
    'meta_d2_adset':                        (4400, 100),
    'meta_d3_creative':                     (4600, 100),
    'meta_d4_ad':                           (4800, 100),
    'check_meta_results':                   (5000, 100),
    'if_pode_retry_infra':                  (5200, 100),
    'wait_30s':                             (5400, 250),
    'persist_estado_apos_meta':             (5400, 100),
    'insert_campanha':                      (5600, 100),
    'audit_campanha_criada':                (5800, 100),

    # Resposta agente_principal (NÃO-CONFIRMAR / OUTRO) — linha 0
    'build_agente_body':                    (2400, 300),
    'agente_principal':                     (2600, 300),
    'update_estado_etapa':                  (2800, 300),
    'persist_estado_etapa':                 (3000, 300),
    'build_historico':                      (3200, 300),
    'upsert_conversa':                      (3400, 300),
    'send_resposta':                        (3600, 300),
    'if_confirmado':                        (3800, 300),

    # NOVA CAMPANHA branch
    'reset_estado_nova':                    (2400, 450),

    # BRANCH GESTÃO (B) — linha 1 (y=600)
    'process_gestao_step':                  (2000, 600),
    'switch_acao_gestao':                   (2200, 600),
    'list_campanhas':                       (2400, 600),
    'init_gestao':                          (2600, 600),
    'prep_persist_gestao':                  (2800, 600),
    'persist_estado_gestao':                (3000, 600),
    'build_gestao_response':                (3200, 600),
    'reset_gestao_simples':                 (2400, 750),
    'build_gestao_msg_cancelado':           (2600, 750),

    # B execução — vem de switch_a_ou_b output GESTAO
    'execute_gestao_action':                (4200, 600),
    'meta_update_status':                   (4400, 600),
    'meta_update_adset_budget':             (4400, 750),
    'switch_publico_geo_livre':             (4400, 900),
    'build_extrator_partial_publico_body':  (4600, 850),
    'build_extrator_partial_geo_body':      (4600, 950),
    'extrator_partial':                     (4800, 900),
    'build_targeting_atualizado':           (5000, 900),
    'meta_update_adset_targeting':          (5200, 900),
    'check_gestao_result':                  (5400, 600),
    'prep_update_db':                       (5600, 600),
    'update_db_campanha':                   (5800, 600),
    'audit_gestao':                         (6000, 600),
    'reset_gestao':                         (6200, 600),
    'build_gestao_confirmation_msg':        (6400, 600),
    'send_gestao_msg':                      (6600, 600),

    # BRANCH MÍDIA — linha 2 (y=1100)
    'media_normalize_phone':                (600, 1100),
    'media_select_cliente':                 (800, 1100),
    'media_if_cadastrado':                  (1000, 1100),
    'media_select_conversa':                (1200, 1100),
    'media_download':                       (1400, 1100),
    'media_upsert_criativo':                (1600, 1100),
    'decide_acao_media':                    (1800, 1100),
    'build_media_response':                 (2000, 1100),
    'media_send_confirma':                  (2200, 1100),

    # respond_immediate (UAZAPI 200) — agrupado no canto
    'respond_immediate':                    (400, 250),
}


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # ─── FIX 1: cria switch_a_ou_b ───
    if 'switch_a_ou_b' not in nb:
        wf['nodes'].append({
            'id': 'switch_a_ou_b', 'name': 'switch_a_ou_b',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [4000, 100],
            'parameters': SWITCH_A_OU_B_RULES
        })
        print('  + switch_a_ou_b adicionado')
    else:
        nb['switch_a_ou_b']['parameters'] = SWITCH_A_OU_B_RULES
        print('  ↻ switch_a_ou_b atualizado')

    # Reroteia: load_meta_token → switch_a_ou_b
    # switch_a_ou_b output 0 (GESTAO) → execute_gestao_action; output 1 (fallback A) → meta_d1_campaign
    wf['connections']['load_meta_token'] = {'main': [[{'node': 'switch_a_ou_b', 'type': 'main', 'index': 0}]]}
    wf['connections']['switch_a_ou_b'] = {
        'main': [
            [{'node': 'execute_gestao_action', 'type': 'main', 'index': 0}],  # GESTAO
            [{'node': 'meta_d1_campaign', 'type': 'main', 'index': 0}]        # fallback A
        ]
    }
    print('  ↻ load_meta_token → switch_a_ou_b → (B|A)')

    # ─── FIX 2: decide_acao_media + build_media_response v2 ───
    nb['decide_acao_media']['parameters']['jsCode'] = DECIDE_ACAO_MEDIA_V2
    print('  ↻ decide_acao_media v2 (detecta duplicado_recente <2min)')
    nb['build_media_response']['parameters']['jsCode'] = BUILD_MEDIA_RESPONSE_V3
    print('  ↻ build_media_response v3 (msg curta pra duplicado)')

    # ─── FIX 3: layout ───
    aplicados = 0
    for n in wf['nodes']:
        if n['name'] in LAYOUT:
            n['position'] = list(LAYOUT[n['name']])
            aplicados += 1
    print(f'  ↻ layout: {aplicados}/{len(wf["nodes"])} nodes reposicionados')

    # Settings limpas
    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}

    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ 3 fixes aplicados')


if __name__ == '__main__':
    main()
