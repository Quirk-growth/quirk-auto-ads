# scripts/g_10_fix_media_9digito.py
# Bug: o caminho de MIDIA nunca recebeu a correcao do 9o digito. media_normalize_phone
# gera o telefone SEM o 9 e media_select_cliente faz match exato -> nao acha o cliente
# (clientes guarda COM o 9) -> no vazio estanca a cadeia -> a midia enviada some.
# Fix (espelha o do caminho de texto): canonicaliza COM o 9 + variantes, e o select casa
# qualquer variante; alwaysOutputData pra nao morrer em silencio.
#   python3 g_10_fix_media_9digito.py          -> dry-run (+ syntax)
#   python3 g_10_fix_media_9digito.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

NEW_NORM = r"""// Extrai telefone da MIDIA e canonicaliza SEMPRE pra forma COM o 9 (bate com clientes.telefone / PK).
const body = $input.first().json.body || {};
const raw = body.chat?.phone || body.message?.sender_pn?.split('@')[0] || body.message?.from || '';
const digits = String(raw).replace(/[+\s\-@]/g, '').replace(/s.whatsapp.net.*$/, '').replace(/[^0-9]/g, '');

function com9(n) {
  if (n && n.startsWith('55')) {
    const rest = n.slice(2);
    if (rest.length === 10) return '55' + rest.slice(0, 2) + '9' + rest.slice(2);
  }
  return n;
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
    telefone_normalizado: com9(digits),
    telefone_variantes: variantes(digits),
    message_id: body.message?.id || ''
  }
}];"""

NEW_QUERY = ('={{ "SELECT * FROM auto_ads.clientes WHERE telefone IN (" + '
             '($json.telefone_variantes && $json.telefone_variantes.length ? $json.telefone_variantes : [$json.telefone_normalizado])'
             '.map(v => "\'" + String(v).replace(/[^0-9]/g, "") + "\'").join(",") + ") LIMIT 1" }}')

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

open("/tmp/_g10.js", "w").write("async function _w(){\n" + NEW_NORM + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g10.js"], capture_output=True, text=True)
print("SYNTAX:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode:
    print(r.stderr[:600]); sys.exit(1)

subprocess.run(["node", "-e",
    "function c(n){if(n&&n.startsWith('55')){const r=n.slice(2);if(r.length===10)return '55'+r.slice(0,2)+'9'+r.slice(2);}return n;}"
    "console.log('  554198443588 (Jimenne) ->', c('554198443588'));"])

if not DEPLOY:
    print("[DRY-RUN]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_media9.json", "w"), ensure_ascii=False, indent=2)
N["media_normalize_phone"]["parameters"]["jsCode"] = NEW_NORM
N["media_select_cliente"]["parameters"]["query"] = NEW_QUERY
N["media_select_cliente"]["parameters"].setdefault("options", {}).pop("queryReplacement", None)
N["media_select_cliente"]["alwaysOutputData"] = True
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("DEPLOYADO: caminho de mídia canonicalizado + busca tolerante.")
