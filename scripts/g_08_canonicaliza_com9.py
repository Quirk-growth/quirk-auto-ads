# scripts/g_08_canonicaliza_com9.py
# Causa raiz (2a camada do 9o digito): o fluxo inteiro (conversas/campanhas/estado, ~15 nos)
# usa telefone_normalizado, mas o WhatsApp entrega ora COM ora SEM o 9. A tabela clientes
# guarda COM o 9 (PK). Quando chega SEM, o telefone nao existe em clientes -> FK viola em
# upsert_conversa/insert_campanha -> execucao morre -> cliente sem resposta.
# Fix: normalize_phone canonicaliza telefone_normalizado SEMPRE pra forma COM o 9. Assim todos
# os nos de baixo batem com a PK da clientes, sem tocar em nenhum deles nem migrar dado.
#   python3 g_08_canonicaliza_com9.py          -> dry-run (+ syntax check)
#   python3 g_08_canonicaliza_com9.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

NEW = r"""// Extrai telefone e canonicaliza SEMPRE pra forma COM o 9 (bate com clientes.telefone / PK).
const body = $input.first().json.body || {};
const raw = body.chat?.phone || body.message?.sender_pn?.split('@')[0] || body.message?.from || '';
const digits = String(raw).replace(/[+\s\-@]/g, '').replace(/s.whatsapp.net.*$/, '').replace(/[^0-9]/g, '');

// BR movel: 55 + DDD(2) + [9] + 8 digitos. WhatsApp entrega ora com, ora sem o 9.
function com9(n) {
  if (n && n.startsWith('55')) {
    const rest = n.slice(2);
    if (rest.length === 10) return '55' + rest.slice(0, 2) + '9' + rest.slice(2); // sem 9 -> com 9
  }
  return n; // ja 13 (com 9) ou nao-BR
}
function variantes(n) {
  const set = new Set();
  if (n) set.add(n);
  if (n && n.startsWith('55')) {
    const rest = n.slice(2);
    if (rest.length === 11 && rest[2] === '9') set.add('55' + rest.slice(0, 2) + rest.slice(3));
    else if (rest.length === 10) set.add('55' + rest.slice(0, 2) + '9' + rest.slice(2));
  }
  return [...set];
}

return [{
  json: {
    ...$input.first().json,
    telefone_normalizado: com9(digits),      // CANONICO = com o 9
    telefone_variantes: variantes(digits),   // ambas as formas p/ select_cliente (rede de seguranca)
    mensagem_texto: body.message?.text || body.chat?.wa_lastMessageTextVote || ''
  }
}];"""

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

open("/tmp/_g08.js", "w").write("async function _w(){\n" + NEW + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g08.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode != 0:
    print(r.stderr[:600]); sys.exit(1)

# teste da canonicalizacao
subprocess.run(["node", "-e",
    "function c(n){if(n&&n.startsWith('55')){const r=n.slice(2);if(r.length===10)return '55'+r.slice(0,2)+'9'+r.slice(2);}return n;}"
    "console.log('  554198443588 (Jimenne, sem 9) ->', c('554198443588'));"
    "console.log('  5511980838409 (Renan, com 9)  ->', c('5511980838409'));"])

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado.]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_canon9.json", "w"), ensure_ascii=False, indent=2)
N["normalize_phone"]["parameters"]["jsCode"] = NEW
cs = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=cs)
print("\nDEPLOYADO: telefone_normalizado canonico com o 9. Backup salvo.")
