#!/usr/bin/env python3
"""
Fix: precheck quebrava em B/C (PAUSAR, REATIVAR, ENCERRAR, ALTERAR_*,
STATUS) porque o nó precheck_meta_account + eval_precheck referenciavam
nodes que SÓ rodam no fluxo CONFIRMAR (sub-projeto A).

Bug observado: 'Sim' pra confirmar PAUSAR → execução abortava no
precheck_meta_account com 'Node validate hasn\\'t been executed'.

Causa: armadilha de $(node) — n8n joga erro se o node referenciado
não rodou na execução atual.

Fixes:
1. precheck_meta_account.url: troca $('validate').item.json.cliente
   .ad_account_id por $('select_cliente').item.json.ad_account_id.
   select_cliente roda em TODOS os fluxos (CONFIRMAR e gestão).
2. eval_precheck: usa try/catch pra ler verba_em_centavos (que só
   vem de validate em CONFIRMAR). Em gestão, verba=0 e o check de
   spend_cap é pulado (faz sentido: PAUSAR não gasta).
"""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import n8n_api, config


EVAL_PRECHECK_V2 = """const precheck = $('precheck_meta_account').first().json;

let verba_em_centavos = 0;
try { verba_em_centavos = $('validate').item.json.verba_em_centavos || 0; } catch(e) {}

const telefone = $('normalize_phone').first().json.telefone_normalizado;

let ok = true;
let motivo = '';
let categoria = 'ok';

if (precheck?.error) {
  ok = false;
  motivo = 'Erro consultando conta Meta: ' + (precheck.error.message || '').slice(0,150);
  categoria = 'meta_api';
} else if (precheck.account_status !== 1) {
  ok = false;
  categoria = 'conta_inativa';
  const status_map = {2: 'desativada', 3: 'sem método de pagamento', 7: 'em revisão', 9: 'em risco', 100: 'pendente fechamento', 101: 'fechada', 201: 'em qualquer revisão', 202: 'em risco de fraude'};
  motivo = `Conta de anúncios está ${status_map[precheck.account_status] || ('status ' + precheck.account_status)}. Verifica no Business Manager.`;
} else if (verba_em_centavos > 0) {
  const spend_cap = parseInt(precheck.spend_cap || '0');
  const amount_spent = parseInt(precheck.amount_spent || '0');
  if (spend_cap > 0) {
    const disponivel = spend_cap - amount_spent;
    if (disponivel < verba_em_centavos) {
      ok = false;
      categoria = 'spend_cap';
      motivo = `Sua conta Meta atingiu o limite de gastos. Disponível: R$ ${(disponivel/100).toFixed(2)}. Aumenta o limite no Business Manager (Configurações → Conta → Limite de gastos) OU troca de conta.`;
    }
  }
}

return [{
  json: {
    ok, motivo, categoria, telefone,
    precheck_summary: {
      account_status: precheck.account_status,
      spend_cap_brl: precheck.spend_cap ? (parseInt(precheck.spend_cap)/100).toFixed(2) : null,
      amount_spent_brl: precheck.amount_spent ? (parseInt(precheck.amount_spent)/100).toFixed(2) : null,
      balance_brl: precheck.balance ? (parseInt(precheck.balance)/100).toFixed(2) : null
    }
  }
}];
"""


PRECHECK_URL = (
    "={{ 'https://graph.facebook.com/v25.0/act_' + $('select_cliente').item.json.ad_account_id + "
    "'?fields=name,account_status,spend_cap,amount_spent,balance,disable_reason,funding_source_details&access_token=' + "
    "$('load_meta_token').item.json.valor }}"
)


def main():
    WF_ID = config.get_workflow_id()
    wf = n8n_api.get_workflow(WF_ID)
    nb = {n['name']: n for n in wf['nodes']}

    nb['precheck_meta_account']['parameters']['url'] = PRECHECK_URL
    print('  ↻ precheck_meta_account.url: validate → select_cliente')

    nb['eval_precheck']['parameters']['jsCode'] = EVAL_PRECHECK_V2
    print('  ↻ eval_precheck: try/catch em validate; spend_cap só em CONFIRMAR')

    clean_settings = {'executionOrder': wf.get('settings', {}).get('executionOrder', 'v1')}
    n8n_api.update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'], connections=wf['connections'], settings=clean_settings)
    print('\n✓ Precheck robusto pra ambos fluxos (A: criação, B/C: gestão)')


if __name__ == '__main__':
    main()
