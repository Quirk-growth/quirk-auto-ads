"""
c_27_fix_video_creative_cta.py

Bugs encontrados no teste E2E de vídeo (16/06/2026):

1. CTA do vídeo rejeitado pelo Meta com erro 400:
     "Remova o parâmetro 'link' do valor do tipo de chamada para ação WHATSAPP_MESSAGE."

   No c_25 incluí `value: {link: waLink, app_destination: 'WHATSAPP'}` mas
   o Meta só aceita `value: {app_destination: 'WHATSAPP'}` no CTA do
   video_data (sem 'link'). O nó antigo de imagem também não tinha 'link'
   no CTA — eu errei ao copiar.

2. Tratamento de erro em postJson engolia a mensagem detalhada do Meta:
     "Request failed with status code 400" sem nem o error_user_msg do Meta.

   Fix: try/catch que extrai e.response.body (n8n encapsula a resposta
   HTTP do erro) e lança Error com a mensagem real.

Validação pós-fix:
  - Vídeo: sample-5s.mp4 upload → status=ready em <8s →
    creative.id=1765154441600808 → ad.id=120245785466710046 → DB success.
  - Campanha id=37 "Apartamento 4Q Moema SP" criada com video_data e
    custom_locations Moema raio 4km.
"""

import sys
sys.path.insert(0, '/Users/renanreal/quirk_auto_ads/scripts')
from n8n_api import get_workflow, update_workflow

WF_ID = 'fBUin1UPt5xJEp6g'
wf = get_workflow(WF_ID)
applied = False
for n in wf['nodes']:
    if n['name'] == 'meta_d3_creative':
        c = n['parameters']['jsCode']
        n1 = c.replace(
            "call_to_action: { type: 'WHATSAPP_MESSAGE', value: { link: waLink, app_destination: 'WHATSAPP' } }",
            "call_to_action: { type: 'WHATSAPP_MESSAGE', value: { app_destination: 'WHATSAPP' } }"
        )
        n2 = n1.replace(
            "async function postJson(url, body) {\n  return await this.helpers.httpRequest({\n    method: 'POST', url, headers: baseHeaders, body, json: true,\n    returnFullResponse: false,\n  });\n}",
            "async function postJson(url, body) {\n  try {\n    return await this.helpers.httpRequest({\n      method: 'POST', url, headers: baseHeaders, body, json: true,\n      returnFullResponse: false,\n    });\n  } catch (e) {\n    const detail = e?.response?.body || e?.cause?.response?.body || e?.message || String(e);\n    throw new Error('Meta API error: ' + (typeof detail === 'string' ? detail : JSON.stringify(detail)));\n  }\n}"
        )
        if n2 != c:
            n['parameters']['jsCode'] = n2
            applied = True
        break

if applied:
    clean = {'executionOrder': wf.get('settings', {}).get('executionOrder','v1')}
    update_workflow(WF_ID, name=wf['name'], nodes=wf['nodes'],
                    connections=wf['connections'], settings=clean)
    print("✅ Fix aplicado")
else:
    print("ℹ️  fix já aplicado ao vivo (este script é só registro)")
