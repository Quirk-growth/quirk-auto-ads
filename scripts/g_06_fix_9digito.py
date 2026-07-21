# scripts/g_06_fix_9digito.py
# Causa raiz: WhatsApp entrega numeros BR sem o 9 (554198443588); cadastro (Asaas)
# guarda com o 9 (5541998443588). select_cliente faz match exato -> nao acha o cliente
# pago -> fluxo morre. Fix: normalize_phone gera as duas variantes (com/sem 9) e
# select_cliente casa qualquer uma (WHERE telefone IN (...)).
#   python3 g_06_fix_9digito.py          -> dry-run (+ syntax check)
#   python3 g_06_fix_9digito.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

NEW_NORMALIZE = r"""// Extrai telefone do payload e normaliza (so digitos) + variantes do 9o digito.
const body = $input.first().json.body || {};
const raw = body.chat?.phone || body.message?.sender_pn?.split('@')[0] || body.message?.from || '';
const normalized = String(raw).replace(/[+\s\-@]/g, '').replace(/s.whatsapp.net.*$/, '').replace(/[^0-9]/g, '');

// Numeros BR: 55 + DDD(2) + [9] + 8 digitos. WhatsApp entrega SEM o 9; cadastro (Asaas)
// costuma ter o 9. Geramos ambos pra busca tolerante.
function brVariants(n) {
  const set = new Set();
  if (n) set.add(n);
  if (n && n.startsWith('55')) {
    const rest = n.slice(2);
    if (rest.length === 11 && rest[2] === '9') set.add('55' + rest.slice(0, 2) + rest.slice(3)); // com 9 -> sem 9
    else if (rest.length === 10) set.add('55' + rest.slice(0, 2) + '9' + rest.slice(2));          // sem 9 -> com 9
  }
  return [...set];
}

return [{
  json: {
    ...$input.first().json,
    telefone_normalizado: normalized,
    telefone_variantes: brVariants(normalized),
    mensagem_texto: body.message?.text || body.chat?.wa_lastMessageTextVote || ''
  }
}];"""

NEW_SELECT_QUERY = ('={{ "SELECT * FROM auto_ads.clientes WHERE telefone IN (" + '
                    '($json.telefone_variantes && $json.telefone_variantes.length ? $json.telefone_variantes : [$json.telefone_normalizado])'
                    '.map(v => "\'" + String(v).replace(/[^0-9]/g, "") + "\'").join(",") + ") LIMIT 1" }}')

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

# syntax check do novo normalize_phone
open("/tmp/_g06.js", "w").write("async function _w(){\n" + NEW_NORMALIZE + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g06.js"], capture_output=True, text=True)
print("SYNTAX normalize_phone:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode != 0:
    print(r.stderr[:600]); sys.exit(1)

# simula as variantes pro cliente afetado
print("\nteste de variantes (554198443588 -> deve incluir 5541998443588):")
subprocess.run(["node", "-e",
    "function b(n){const s=new Set();if(n)s.add(n);if(n&&n.startsWith('55')){const r=n.slice(2);"
    "if(r.length===11&&r[2]==='9')s.add('55'+r.slice(0,2)+r.slice(3));"
    "else if(r.length===10)s.add('55'+r.slice(0,2)+'9'+r.slice(2));}return[...s];}"
    "console.log('  554198443588 ->', JSON.stringify(b('554198443588')));"
    "console.log('  5541998443588 ->', JSON.stringify(b('5541998443588')));"])

print("\nnova query select_cliente:")
print(" ", NEW_SELECT_QUERY[:160], "...")

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado.]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_9digito.json", "w"), ensure_ascii=False, indent=2)
N["normalize_phone"]["parameters"]["jsCode"] = NEW_NORMALIZE
N["select_cliente"]["parameters"]["query"] = NEW_SELECT_QUERY
N["select_cliente"]["parameters"].setdefault("options", {})
N["select_cliente"]["parameters"]["options"].pop("queryReplacement", None)

clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=clean_settings)
print("\nDEPLOYADO: busca tolerante ao 9o digito. Backup salvo.")
