#!/usr/bin/env python3
"""
Hardening 1: gate de pre-check da conta Meta antes de tentar criar campanha.

Bug que motivou: gastamos várias horas debugando "compliance error" que na
verdade era spend_cap esgotado. Meta retorna erro genérico mascarando a causa.

Fix: novo node `precheck_meta_account` (HTTP GET) + `eval_precheck` (Code)
entre `validate` e `load_meta_token`. Roda 1 chamada Meta API e barra:

- account_status != 1 (ACTIVE) → bloqueia com 'Conta desativada/restrita'
- amount_spent >= spend_cap - verba_em_centavos → 'Spend cap esgotado.
  Disponível: R$ X. Aumenta no BM ou troca de conta.'
- balance < 100 e funding_source_details.type == 20 (pré-pago Pix) →
  warning mas deixa passar

Se OK → continua normal pra load_meta_token → meta_d1.
Se barrado → vai pra audit_validacao_falhou + manda msg pro cliente.
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    # 1. HTTP GET pra status da conta + spend cap
    if 'precheck_meta_account' not in nb:
        wf['nodes'].append({
            'id': 'precheck_meta_account', 'name': 'precheck_meta_account',
            'type': 'n8n-nodes-base.httpRequest', 'typeVersion': 4.2,
            'position': [3900, 100],
            'parameters': {
                'method': 'GET',
                'url': "={{ 'https://graph.facebook.com/v25.0/act_' + $('validate').item.json.cliente.ad_account_id + '?fields=name,account_status,spend_cap,amount_spent,balance,disable_reason,funding_source_details&access_token=' + $('load_meta_token').item.json.valor }}",
                'options': {},
            },
            'continueOnFail': True
        })
        print('  + precheck_meta_account adicionado')

    # 2. Code node que avalia o resultado
    EVAL_CODE = """// Avalia status da conta + spend cap antes de tentar criar campanha
const precheck = $('precheck_meta_account').first().json;
const verba_em_centavos = $('validate').item.json.verba_em_centavos || 3000;
const telefone = $('normalize_phone').first().json.telefone_normalizado;

let ok = true;
let motivo = '';
let categoria = 'ok';

if (precheck?.error) {
  ok = false; motivo = 'Erro consultando conta Meta: ' + (precheck.error.message || '').slice(0,150); categoria = 'meta_api';
} else if (precheck.account_status !== 1) {
  ok = false; categoria = 'conta_inativa';
  const status_map = {2: 'desativada', 3: 'sem método de pagamento', 7: 'em revisão', 9: 'em risco', 100: 'pendente fechamento', 101: 'fechada', 201: 'em qualquer revisão', 202: 'em risco de fraude'};
  motivo = `Conta de anúncios está ${status_map[precheck.account_status] || ('status ' + precheck.account_status)}. Verifica no Business Manager.`;
} else {
  const spend_cap = parseInt(precheck.spend_cap || '0');
  const amount_spent = parseInt(precheck.amount_spent || '0');
  if (spend_cap > 0) {
    const disponivel = spend_cap - amount_spent;
    if (disponivel < verba_em_centavos) {
      ok = false; categoria = 'spend_cap';
      motivo = `Sua conta Meta atingiu o limite de gastos. Disponível: R$ ${(disponivel/100).toFixed(2)}. Aumenta o limite no Business Manager (Configurações → Conta → Limite de gastos) OU troca de conta.`;
    }
  }
}

return [{
  json: {
    ok, motivo, categoria,
    telefone,
    precheck_summary: {
      account_status: precheck.account_status,
      spend_cap_brl: precheck.spend_cap ? (parseInt(precheck.spend_cap)/100).toFixed(2) : null,
      amount_spent_brl: precheck.amount_spent ? (parseInt(precheck.amount_spent)/100).toFixed(2) : null,
      balance_brl: precheck.balance ? (parseInt(precheck.balance)/100).toFixed(2) : null
    }
  }
}];
"""
    if 'eval_precheck' not in nb:
        wf['nodes'].append({
            'id': 'eval_precheck', 'name': 'eval_precheck',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [4050, 100],
            'parameters': {'language': 'javaScript', 'jsCode': EVAL_CODE}
        })
        print('  + eval_precheck adicionado')

    # 3. IF: precheck ok? → continua | senão → manda msg de erro
    if 'if_precheck_ok' not in nb:
        wf['nodes'].append({
            'id': 'if_precheck_ok', 'name': 'if_precheck_ok',
            'type': 'n8n-nodes-base.if', 'typeVersion': 2,
            'position': [4150, 100],
            'parameters': {
                'conditions': {
                    'options': {'caseSensitive': True, 'typeValidation': 'loose'},
                    'combinator': 'and',
                    'conditions': [{
                        'leftValue': "={{ $('eval_precheck').item.json.ok }}",
                        'rightValue': True,
                        'operator': {'type': 'boolean', 'operation': 'true', 'singleValue': True}
                    }]
                }
            }
        })
        print('  + if_precheck_ok adicionado')

    # 4. Build msg de erro pro cliente
    BUILD_PRECHECK_ERROR_CODE = """const e = $('eval_precheck').first().json;
return [{
  json: {
    text: '⚠️ ' + e.motivo + '\\n\\nQuando arrumar, manda CONFIRMAR de novo.',
    telefone: e.telefone
  }
}];
"""
    if 'build_precheck_error_msg' not in nb:
        wf['nodes'].append({
            'id': 'build_precheck_error_msg', 'name': 'build_precheck_error_msg',
            'type': 'n8n-nodes-base.code', 'typeVersion': 2,
            'position': [4250, 250],
            'parameters': {'language': 'javaScript', 'jsCode': BUILD_PRECHECK_ERROR_CODE}
        })
        print('  + build_precheck_error_msg adicionado')

    # 5. Audit do precheck barrado
    AUDIT_PRECHECK_QUERY = """INSERT INTO auto_ads.audit_log (telefone, evento, detalhes)
SELECT
  '{{ $('eval_precheck').item.json.telefone }}',
  'precheck_barrado',
  jsonb_build_object(
    'categoria', '{{ $('eval_precheck').item.json.categoria }}',
    'motivo', '{{ ($('eval_precheck').item.json.motivo || '').replace(/'/g, "''") }}',
    'precheck_summary', '{{ JSON.stringify($('eval_precheck').item.json.precheck_summary).replace(/'/g, "''") }}'::jsonb
  )"""
    if 'audit_precheck' not in nb:
        wf['nodes'].append({
            'id': 'audit_precheck', 'name': 'audit_precheck',
            'type': 'n8n-nodes-base.postgres', 'typeVersion': 2.6,
            'position': [4250, 400],
            'parameters': {'operation': 'executeQuery', 'query': AUDIT_PRECHECK_QUERY, 'options': {}},
            'credentials': {'postgres': config.POSTGRES_CRED}
        })
        print('  + audit_precheck adicionado')

    # ─── Rewire ───
    # Era: load_meta_token → switch_a_ou_b
    # Vira: load_meta_token → precheck_meta_account → eval_precheck → if_precheck_ok
    #         ok=true  → switch_a_ou_b (fluxo normal)
    #         ok=false → audit_precheck → build_precheck_error_msg → send_gestao_msg
    wf['connections']['load_meta_token'] = {'main': [[{'node': 'precheck_meta_account', 'type': 'main', 'index': 0}]]}
    wf['connections']['precheck_meta_account'] = {'main': [[{'node': 'eval_precheck', 'type': 'main', 'index': 0}]]}
    wf['connections']['eval_precheck'] = {'main': [[{'node': 'if_precheck_ok', 'type': 'main', 'index': 0}]]}
    wf['connections']['if_precheck_ok'] = {
        'main': [
            [{'node': 'switch_a_ou_b', 'type': 'main', 'index': 0}],
            [{'node': 'audit_precheck', 'type': 'main', 'index': 0}]
        ]
    }
    wf['connections']['audit_precheck'] = {'main': [[{'node': 'build_precheck_error_msg', 'type': 'main', 'index': 0}]]}
    wf['connections']['build_precheck_error_msg'] = {'main': [[{'node': 'send_gestao_msg', 'type': 'main', 'index': 0}]]}

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Pre-check da conta Meta plugado entre load_meta_token e Meta API calls')


if __name__ == '__main__':
    main()
