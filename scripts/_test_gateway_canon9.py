# scripts/_test_gateway_canon9.py
# Testa o codigo REALMENTE DEPLOYADO do parse_payment (gateway) num harness Node,
# injetando um cliente Asaas com telefone SEM o 9 -> deve sair canonico (com o 9).
import json, subprocess, n8n_api

jc = {n['name']: n for n in n8n_api.get_workflow("2ZnZqb4wFous4uEs")['nodes']}['parse_payment']['parameters']['jsCode']

HARNESS = """
const MOCK = {
  webhook: { body: { event: 'PAYMENT_RECEIVED',
    payment: { customer: 'cus_TESTE', value: 497, externalReference: 'auto-ads-mensal', subscription: 'sub_TESTE' } } },
  load_config_asaas: { admin_passphrase: 'x', asaas_api_key: 'k',
    asaas_group_name: 'Auto Ads - Imob', asaas_product_value_cents: '49700' },
};
function $(name){ return { first: () => ({ json: MOCK[name] }) }; }
const ctx = { helpers: { httpRequest: async () => ({
  // Asaas devolvendo o telefone SEM o 9 (o caso que quebrava)
  mobilePhone: '41 98443588', email: 'teste@x.com', name: 'Cliente Teste'
}) } };

async function run(){
__CODE__
}
run.call(ctx).then(r => {
  const j = r[0].json;
  console.log('retorno:', JSON.stringify({skip:j.skip, motivo:j.motivo, telefone:j.telefone, nome:j.nome}));
  const t = j.telefone || '';
  console.log('telefone:', t, '| digitos:', t.length);
  console.log(t === '5541998443588' ? 'CANONICO OK (com o 9)' : 'FALHOU - esperado 5541998443588');
}).catch(e => console.log('erro no harness:', String(e).slice(0,200)));
"""

open("/tmp/_gwtest.js", "w").write(HARNESS.replace("__CODE__", jc))
r = subprocess.run(["node", "/tmp/_gwtest.js"], capture_output=True, text=True)
print(r.stdout or r.stderr[:600])
