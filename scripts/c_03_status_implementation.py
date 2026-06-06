#!/usr/bin/env python3
"""
Sub-projeto C — STATUS MVP (verbo único, resposta determinística, 4 períodos).

Adiciona:
1. classify_intent v6: detecta STATUS por regex
2. switch_intent ganha output STATUS → list_campanhas (reusa)
3. process_gestao_step: para verbo STATUS após selecao, vai direto pra executa
4. switch_b_ou_c (Switch novo): STATUS → branch insights; demais → execute_gestao_action atual
5. 4 HTTPs Meta Insights paralelas (today/yesterday/7d/30d)
6. merge_insights (Code): combina os 4 outputs
7. format_status_response (Code): mensagem determinística
8. audit + reset_gestao no fim
"""
import os, sys, json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


CLASSIFY_INTENT_V6 = """const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();
const estado = $('load_estado').first().json?.estado || {};
const etapaAtual = estado.etapa_atual;

let intent = 'OUTRO';

if (/^(confirmar|confirmado|confirma)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^(sim,?\\s*subir|pode\\s*subir|sobe\\s*ai)[!.?]*$/i.test(msg)) intent = 'CONFIRMAR';
else if (/^subir\\s+denovo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^subir\\s+de\\s+novo[!.?]*$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/sub(ir|a)\\s+novamente/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/tent(e|a)r?\\s+(de\\s*novo|novamente)/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^repetir$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^refazer$/i.test(msg)) intent = 'SUBIR_DENOVO';
else if (/^nova\\s+campanha$/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/come[çc]ar\\s+(uma\\s+)?nova/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/quero\\s+(criar\\s+)?(uma\\s+)?(outra|nova)\\s+campanha/i.test(msg)) intent = 'NOVA_CAMPANHA';
else if (/^(pausar|pausa)[!.?]*$/i.test(msg)) intent = 'PAUSAR';
else if (/pausar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/parar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'PAUSAR';
else if (/^(reativar|reativa|ativar)[!.?]*$/i.test(msg)) intent = 'REATIVAR';
else if (/voltar\\s+(minha\\s+)?campanha/i.test(msg)) intent = 'REATIVAR';
else if (/^(encerrar|arquivar)[!.?]*$/i.test(msg)) intent = 'ENCERRAR';
else if (/finalizar\\s+campanha/i.test(msg)) intent = 'ENCERRAR';
else if (/(alterar|mudar|trocar)\\s+verba/i.test(msg)) intent = 'ALTERAR_VERBA';
else if (/(alterar|mudar)\\s+p[uú]blico/i.test(msg)) intent = 'ALTERAR_PUBLICO';
else if (/(alterar|mudar)\\s+geo/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/mudar\\s+(regi[aã]o|cidade)/i.test(msg)) intent = 'ALTERAR_GEO';
else if (/^(cancelar|cancela)[!.?]*$/i.test(msg)) intent = 'CANCELAR';
else if (/^deixa\\s+pra\\s+l[áa]/i.test(msg)) intent = 'CANCELAR';
else if (/^status$/i.test(msg)) intent = 'STATUS';
else if (/^ver\\s+status$/i.test(msg)) intent = 'STATUS';
else if (/como\\s+(est[áa]|vai|t[áa])\\s+(a\\s+)?(minha\\s+)?campanha/i.test(msg)) intent = 'STATUS';
else if (/^relat[óo]rio$/i.test(msg)) intent = 'STATUS';
else if (/m[ée]tricas?\\s+(da\\s+)?(minha\\s+)?campanha/i.test(msg)) intent = 'STATUS';

if (intent === 'OUTRO' && etapaAtual === 'ativa') {
  const temImovel = /(apartamento|cobertura|casa|sobrado|terreno|lote|condom[íi]nio|ap\\s*\\d|kitnet|studio)/i.test(msg);
  const temValor = /(r\\$|reais|milh[ãa]o|mil\\b|k\\b|\\d{2,}\\s*mil)/i.test(msg);
  const temRegiao = /(bairro|regi[ãa]o|cidade|setor|jardim|vila|centro)/i.test(msg);
  const sinais = [temImovel, temValor, temRegiao].filter(Boolean).length;
  if (sinais >= 2) intent = 'NOVA_CAMPANHA';
}

return [{ json: { intent, mensagem_texto: msg } }];
"""


# process_gestao_step v2: STATUS pula coleta_valor → vai direto pra executa após selecao
PROCESS_GESTAO_STEP_V2 = """const estado = $('load_estado').first().json.estado;
const gestao = estado.gestao;
const msg = String($('normalize_phone').first().json?.mensagem_texto || '').trim();

if (!gestao || !gestao.passo) {
  return [{ json: { acao: 'reset', motivo: 'gestao_vazio' } }];
}

if (/^(cancelar|cancela|deixa\\s+pra\\s+l[áa])[!.?]*$/i.test(msg)) {
  return [{ json: { acao: 'reset', motivo: 'cancelado_pelo_cliente' } }];
}

const passo = gestao.passo;
const verbo = gestao.verbo;

if (passo === 'selecao') {
  const num = parseInt(msg);
  if (isNaN(num) || num < 1 || num > (gestao.lista_candidatas || []).length) {
    return [{ json: { acao: 'erro_input', motivo: 'numero_invalido', proximo_passo: 'selecao', gestao, estado } }];
  }
  const selecionada = gestao.lista_candidatas[num - 1];
  gestao.selecionada = selecionada;

  // STATUS + verbos destrutivos: direto pra executa | confirmacao
  if (verbo === 'STATUS') {
    return [{ json: { acao: 'executa', estado, gestao } }];
  }
  if (['PAUSAR', 'REATIVAR', 'ENCERRAR'].includes(verbo)) {
    gestao.passo = 'confirmacao';
  } else {
    gestao.passo = 'coleta_valor';
  }
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

if (passo === 'coleta_valor') {
  let novo_valor = null;
  let erro = null;

  if (verbo === 'ALTERAR_VERBA') {
    const n = parseInt(msg);
    if (isNaN(n) || n < 10 || n > 100) erro = 'verba_fora_faixa';
    else novo_valor = { tipo: 'verba_diaria', valor: n };
  } else if (verbo === 'ALTERAR_PUBLICO') {
    const num = parseInt(msg);
    if (!isNaN(num) && num >= 1 && num <= 20) novo_valor = { tipo: 'publico_estruturado', numero: num };
    else if (msg.length >= 4) novo_valor = { tipo: 'publico_livre', descricao: msg };
    else erro = 'publico_input_invalido';
  } else if (verbo === 'ALTERAR_GEO') {
    const m = msg.match(/^(.+?)\\s+(\\d+)$/);
    if (m) novo_valor = { tipo: 'geo_estruturado', cidade: m[1].trim(), raio_km: parseInt(m[2]) };
    else if (msg.length >= 4) novo_valor = { tipo: 'geo_livre', descricao: msg };
    else erro = 'geo_input_invalido';
  }

  if (erro) return [{ json: { acao: 'erro_input', motivo: erro, proximo_passo: 'coleta_valor', gestao, estado } }];
  gestao.novo_valor = novo_valor;
  gestao.passo = 'confirmacao';
  return [{ json: { acao: 'avanca', estado, gestao } }];
}

if (passo === 'confirmacao') {
  if (/^(sim|s|confirma|confirmar|confirmado)[!.?]*$/i.test(msg)) return [{ json: { acao: 'executa', estado, gestao } }];
  if (/^(n[aã]o|n)[!.?]*$/i.test(msg)) return [{ json: { acao: 'reset', motivo: 'cancelado_no_confirma' } }];
  return [{ json: { acao: 'erro_input', motivo: 'confirma_invalido', proximo_passo: 'confirmacao', gestao, estado } }];
}

return [{ json: { acao: 'reset', motivo: 'passo_desconhecido' } }];
"""


# Switch B vs C
SWITCH_B_OU_C_RULES = {
    'rules': {
        'values': [
            {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [{
                        'leftValue': "={{ $('process_gestao_step').item.json.gestao.verbo }}",
                        'rightValue': 'STATUS',
                        'operator': {'type': 'string', 'operation': 'equals'}
                    }]
                },
                'renameOutput': True, 'outputKey': 'STATUS'
            }
        ]
    },
    'options': {'fallbackOutput': 'extra'}  # demais verbos = fluxo B atual
}


# 4 HTTP nodes — Meta Insights por período
def insights_node(node_id, position, periodo):
    return {
        'id': node_id, 'name': node_id,
        'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
        'position': position,
        'parameters': {
            'method': 'GET',
            'url': "={{ 'https://graph.facebook.com/v25.0/' + $('process_gestao_step').item.json.gestao.selecionada.campaign_id_meta + '/insights?fields=impressions,reach,spend,cpm,ctr,actions&date_preset=" + periodo + "&access_token=' + $('load_meta_token').item.json.valor }}",
            'options': {},
        },
        'continueOnFail': True,
        'retryOnFail': True, 'maxTries': 2, 'waitBetweenTries': 1500
    }


# Merge results de 4 períodos
MERGE_INSIGHTS_CODE = """// Combina os 4 outputs de insights num único objeto por período
function parseInsights(node, label) {
  try {
    const r = $(node).first().json;
    if (r?.error) return { label, ok: false, motivo: r.error.message?.slice(0, 100) || 'erro' };
    const data = (r.data || [])[0];
    if (!data) return { label, ok: true, vazio: true };

    const actions = data.actions || [];
    const msgs_iniciadas = actions.reduce((acc, a) => {
      if (['onsite_conversion.messaging_conversation_started_7d', 'onsite_conversion.messaging_first_reply', 'messaging_first_reply', 'onsite_conversion.lead'].includes(a.action_type)) {
        return acc + (parseFloat(a.value) || 0);
      }
      return acc;
    }, 0);

    const spend = parseFloat(data.spend || 0);
    const reach = parseInt(data.reach || 0);
    const imp = parseInt(data.impressions || 0);
    const cpm = parseFloat(data.cpm || 0);
    const ctr = parseFloat(data.ctr || 0);
    const cpl = msgs_iniciadas > 0 ? spend / msgs_iniciadas : 0;

    return { label, ok: true, vazio: false, imp, reach, msgs: msgs_iniciadas, spend, cpm, ctr, cpl };
  } catch(e) {
    return { label, ok: false, motivo: e.message };
  }
}

const hoje = parseInsights('meta_insights_today', 'Hoje');
const ontem = parseInsights('meta_insights_yesterday', 'Ontem');
const sete_d = parseInsights('meta_insights_7d', '7d');
const trinta_d = parseInsights('meta_insights_30d', '30d');

const sel = $('process_gestao_step').first().json.gestao.selecionada;

return [{ json: {
  campanha_nome: sel.nome,
  campanha_id_meta: sel.campaign_id_meta,
  campanha_id_db: sel.campanha_id_db,
  status_atual: sel.status,
  periodos: { hoje, ontem, sete_d, trinta_d },
  telefone: $('normalize_phone').first().json.telefone_normalizado
}}];
"""


# Format final response
FORMAT_STATUS_RESPONSE_CODE = """const d = $('merge_insights').first().json;

function fmtN(n) {
  if (n == null) return '—';
  if (n >= 1000) return (n/1000).toFixed(1) + 'k';
  return String(Math.round(n));
}
function fmtR(n) {
  if (n == null || n === 0) return '—';
  if (n >= 1000) return 'R$ ' + (n/1000).toFixed(1) + 'k';
  return 'R$ ' + n.toFixed(2);
}
function fmtP(n) { return n != null ? n.toFixed(2) + '%' : '—'; }

function fmtPeriodo(p) {
  if (!p.ok) return `${p.label.padEnd(7)} (erro Meta)`;
  if (p.vazio) return `${p.label.padEnd(7)} sem entregas`;
  return `${p.label.padEnd(7)} ${fmtN(p.imp)} imp · ${fmtN(p.reach)} alcance · ${fmtN(p.msgs)} msgs · ${fmtR(p.spend)}${p.msgs > 0 ? ' · ' + fmtR(p.cpl) + '/msg' : ''}`;
}

const p = d.periodos;
const linhas = [
  '📊 ' + d.campanha_nome,
  'Status no Meta: ' + d.status_atual,
  '',
  fmtPeriodo(p.hoje),
  fmtPeriodo(p.ontem),
  fmtPeriodo(p.sete_d),
  fmtPeriodo(p.trinta_d),
  ''
];

if (p.sete_d.ok && !p.sete_d.vazio) {
  linhas.push('CTR 7d: ' + fmtP(p.sete_d.ctr) + ' · CPM 7d: ' + fmtR(p.sete_d.cpm));
}

return [{ json: { text: linhas.join('\\n'), telefone: d.telefone } }];
"""


AUDIT_STATUS_QUERY = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
SELECT
  '{{ $('merge_insights').item.json.telefone }}',
  'status_consultado',
  jsonb_build_object(
    'campanha_id_db', {{ $('merge_insights').item.json.campanha_id_db }},
    'campaign_id_meta', '{{ $('merge_insights').item.json.campanha_id_meta }}',
    'periodos_summary', '{{ JSON.stringify({hoje_ok: $('merge_insights').item.json.periodos.hoje.ok, ontem_ok: $('merge_insights').item.json.periodos.ontem.ok, sete_d_ok: $('merge_insights').item.json.periodos.sete_d.ok, trinta_d_ok: $('merge_insights').item.json.periodos.trinta_d.ok}).replace(/'/g, "''") }}'::jsonb
  )"""


RESET_GESTAO_STATUS_QUERY = """UPDATE auto_ads.conversas
SET estado_json = jsonb_set(jsonb_set(estado_json, '{gestao}', 'null'::jsonb), '{etapa_atual}', '"ativa"'::jsonb)
WHERE telefone = '{{ $('merge_insights').item.json.telefone }}'"""


def add_rule_status_to_switch(rules, intent_name, output_key):
    rules.append({
        'conditions': {
            'options': {'caseSensitive': True, 'typeValidation': 'loose'},
            'combinator': 'and',
            'conditions': [{
                'leftValue': "={{ $('classify_intent').item.json.intent }}",
                'rightValue': intent_name,
                'operator': {'type': 'string', 'operation': 'equals'}
            }]
        },
        'renameOutput': True, 'outputKey': output_key
    })


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # 1. classify_intent v6
    nb['classify_intent']['parameters']['jsCode'] = CLASSIFY_INTENT_V6
    print('  ↻ classify_intent v6 (regex STATUS)')

    # 2. process_gestao_step v2
    nb['process_gestao_step']['parameters']['jsCode'] = PROCESS_GESTAO_STEP_V2
    print('  ↻ process_gestao_step v2 (STATUS pula coleta/confirma)')

    # 3. switch_intent: adiciona output STATUS → list_campanhas
    sw = nb['switch_intent']
    rules = sw['parameters']['rules']['values']
    existing_keys = {r.get('outputKey') for r in rules}
    if 'STATUS' not in existing_keys:
        add_rule_status_to_switch(rules, 'STATUS', 'STATUS')
        # Conexão STATUS → list_campanhas (mesmo de PAUSAR/REATIVAR/etc)
        conn = wf['connections'].get('switch_intent', {}).get('main', [])
        # index = posição do STATUS no array de outputs
        status_idx = len(rules) - 1
        # Garante que conn tem espaço suficiente
        while len(conn) < status_idx + 2:  # +2 pra fallback OUTRO
            conn.append([])
        conn[status_idx] = [{'node': 'list_campanhas', 'type': 'main', 'index': 0}]
        wf['connections']['switch_intent']['main'] = conn
        print('  + switch_intent output STATUS → list_campanhas')

    # 4. switch_b_ou_c
    if 'switch_b_ou_c' not in nb:
        wf['nodes'].append({
            'id': 'switch_b_ou_c', 'name': 'switch_b_ou_c',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [2350, 600],
            'parameters': SWITCH_B_OU_C_RULES
        })
        print('  + switch_b_ou_c adicionado')

    # 5. 4 insights nodes
    positions = {
        'meta_insights_today':     [2600, 500],
        'meta_insights_yesterday': [2600, 600],
        'meta_insights_7d':        [2600, 700],
        'meta_insights_30d':       [2600, 800],
    }
    period_map = {
        'meta_insights_today': 'today',
        'meta_insights_yesterday': 'yesterday',
        'meta_insights_7d': 'last_7d',
        'meta_insights_30d': 'last_30d',
    }
    for name, periodo in period_map.items():
        if name not in nb:
            wf['nodes'].append(insights_node(name, positions[name], periodo))
            print(f'  + {name} (date_preset={periodo})')

    # 6. merge_insights — usa Code (não Merge node nativo, mais simples)
    if 'merge_insights' not in nb:
        wf['nodes'].append({
            'id': 'merge_insights', 'name': 'merge_insights',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [2900, 650],
            'parameters': {'language': 'javaScript', 'jsCode': MERGE_INSIGHTS_CODE}
        })
        print('  + merge_insights')

    # 7. format_status_response
    if 'format_status_response' not in nb:
        wf['nodes'].append({
            'id': 'format_status_response', 'name': 'format_status_response',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [3100, 650],
            'parameters': {'language': 'javaScript', 'jsCode': FORMAT_STATUS_RESPONSE_CODE}
        })
        print('  + format_status_response')

    # 8. audit + reset
    if 'audit_status' not in nb:
        wf['nodes'].append({
            'id': 'audit_status', 'name': 'audit_status',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3300, 650],
            'parameters': {'operation': 'executeQuery', 'query': AUDIT_STATUS_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + audit_status')

    if 'reset_gestao_status' not in nb:
        wf['nodes'].append({
            'id': 'reset_gestao_status', 'name': 'reset_gestao_status',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [3500, 650],
            'parameters': {'operation': 'executeQuery', 'query': RESET_GESTAO_STATUS_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + reset_gestao_status')

    # 9. Rewire — caminho EXECUTA agora vai pro switch_b_ou_c primeiro
    # Antes: switch_acao_gestao output 2 (EXECUTA) → load_meta_token
    # Agora: switch_acao_gestao output 2 (EXECUTA) → switch_b_ou_c
    #         switch_b_ou_c STATUS → load_meta_token → 4 insights → merge → format → audit → reset → send
    #         switch_b_ou_c fallback (B) → load_meta_token (mantém B atual)
    wf['connections']['switch_acao_gestao'] = {
        'main': [
            [{'node': 'prep_persist_gestao', 'type': 'main', 'index': 0}],
            [{'node': 'build_gestao_response', 'type': 'main', 'index': 0}],
            [{'node': 'switch_b_ou_c', 'type': 'main', 'index': 0}],
            [{'node': 'reset_gestao_simples', 'type': 'main', 'index': 0}]
        ]
    }

    # switch_b_ou_c outputs
    wf['connections']['switch_b_ou_c'] = {
        'main': [
            [{'node': 'load_meta_token', 'type': 'main', 'index': 0}],  # STATUS
            [{'node': 'load_meta_token', 'type': 'main', 'index': 0}]   # fallback B
        ]
    }

    # load_meta_token: hoje vai pra precheck_meta_account (do item 2)
    # Pra STATUS, queremos pular precheck e ir direto pras 4 insights
    # Solução: deixa precheck rodar (não machuca) mas vai pros 4 insights em paralelo
    # Aproveitando que load_meta_token → precheck_meta_account → ... → switch_a_ou_b
    # E switch_a_ou_b já tem GESTAO output → execute_gestao_action.
    # Pra STATUS, precisamos diferenciar AINDA: depois do load_meta_token, se é STATUS, vai pras insights.
    #
    # Approach mais limpo: load_meta_token → branch direto pelas 4 insights quando STATUS.
    # Refator: vou conectar load_meta_token a um Switch novo "switch_status_ou_fluxo_normal" que detecta STATUS
    # e roteia pras 4 insights paralelas em vez de precheck/etc.

    if 'switch_status_ou_normal' not in nb:
        wf['nodes'].append({
            'id': 'switch_status_ou_normal', 'name': 'switch_status_ou_normal',
            'type': 'n8n-nodes-base.switch', 'typeVersion': 3.2,
            'position': [3800, 100],
            'parameters': {
                'rules': {
                    'values': [{
                        'conditions': {
                            'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                            'combinator': 'and',
                            'conditions': [{
                                'leftValue': "={{ ($('process_gestao_step').item?.json?.gestao?.verbo) || '' }}",
                                'rightValue': 'STATUS',
                                'operator': {'type': 'string', 'operation': 'equals'}
                            }]
                        },
                        'renameOutput': True, 'outputKey': 'STATUS'
                    }]
                },
                'options': {'fallbackOutput': 'extra'}
            }
        })
        print('  + switch_status_ou_normal (após load_meta_token)')

    # load_meta_token → switch_status_ou_normal
    wf['connections']['load_meta_token'] = {'main': [[{'node': 'switch_status_ou_normal', 'type': 'main', 'index': 0}]]}
    # switch_status_ou_normal STATUS → 4 insights (paralelo) ; fallback → precheck_meta_account
    wf['connections']['switch_status_ou_normal'] = {
        'main': [
            [
                {'node': 'meta_insights_today', 'type': 'main', 'index': 0},
                {'node': 'meta_insights_yesterday', 'type': 'main', 'index': 0},
                {'node': 'meta_insights_7d', 'type': 'main', 'index': 0},
                {'node': 'meta_insights_30d', 'type': 'main', 'index': 0}
            ],
            [{'node': 'precheck_meta_account', 'type': 'main', 'index': 0}]
        ]
    }

    # Cada insight → merge_insights
    for n_name in ['meta_insights_today', 'meta_insights_yesterday', 'meta_insights_7d', 'meta_insights_30d']:
        wf['connections'][n_name] = {'main': [[{'node': 'merge_insights', 'type': 'main', 'index': 0}]]}

    wf['connections']['merge_insights'] = {'main': [[{'node': 'format_status_response', 'type': 'main', 'index': 0}]]}
    wf['connections']['format_status_response'] = {'main': [[{'node': 'audit_status', 'type': 'main', 'index': 0}]]}
    wf['connections']['audit_status'] = {'main': [[{'node': 'reset_gestao_status', 'type': 'main', 'index': 0}]]}
    wf['connections']['reset_gestao_status'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}

    # send_gestao_msg precisa ler text/telefone — format_status_response já entrega no shape certo
    # mas send_gestao_msg usa $json.text. format_status_response retorna {text, telefone}.
    # MAS audit_status (Postgres) + reset_gestao_status (Postgres) ficam entre format e send.
    # Postgres não passa $json. Preciso mudar a ordem ou usar referência absoluta.
    # Solução: send_gestao_msg referencia $('format_status_response').item.json
    # Vou ajustar o body do send_gestao_msg pra usar referência absoluta como fallback.

    snd = nb['send_gestao_msg']
    body_params = snd['parameters'].get('bodyParameters', {}).get('parameters', [])
    for p in body_params:
        if p.get('name') == 'text':
            # Aceita $json.text (B) OR format_status_response (C)
            p['value'] = "={{ $json.text || $('format_status_response').item?.json?.text || '' }}"
        if p.get('name') == 'number':
            p['value'] = "={{ $json.telefone || $('format_status_response').item?.json?.telefone || '' }}"
    print('  ↻ send_gestao_msg: aceita text/telefone de $json OU format_status_response')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Sub-projeto C (STATUS) implementado')


if __name__ == '__main__':
    main()
