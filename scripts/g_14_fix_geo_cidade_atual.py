# scripts/g_14_fix_geo_cidade_atual.py
# BUG (exec 22794, campanha 10): cliente pediu "mesma localizacao, raio maior de 8km".
# O extrator devolveu cidade:"" (correto — nenhuma cidade nova foi nomeada), mas
# build_targeting_atualizado exigia cidade e retornava {error} -> o objeto de erro ia
# direto pro no da Meta como body -> JSON invalido -> check_gestao_result via motivo ""
# -> cliente recebia "erro desconhecido".
#
# Correcoes (2 nos, so codigo, sem rewiring):
#  A) build_targeting_atualizado: quando o cliente NAO nomeia cidade, reaproveita a
#     cidade atual da campanha (sel.geo_cidade_atual + conjunto.geo_estado). E os dois
#     retornos de erro passam a carregar motivo_usuario legivel.
#  B) check_gestao_result: no ramo ALTERAR_PUBLICO/GEO, se build_targeting_atualizado
#     retornou erro, curto-circuita com motivo claro em vez de chamar/ler a Meta.
#
#   python3 g_14_fix_geo_cidade_atual.py          -> dry-run (+ node --check)
#   python3 g_14_fix_geo_cidade_atual.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

# ---- Edit A: build_targeting_atualizado ----
A_ANCHOR = """  if (!cidade) {
    return [{ json: { error: 'cidade_nao_identificada', cidade, raio_km } }];
  }"""
A_NEW = """  // Cliente nao nomeou cidade nova (ex: "mesma localizacao, raio maior") -> reaproveita a cidade atual da campanha
  if (!cidade) {
    cidade = sel.geo_cidade_atual || '';
    if (!estado) estado = (json_ext.conjunto && json_ext.conjunto.geo_estado) || '';
  }
  if (!cidade) {
    return [{ json: { error: 'cidade_nao_identificada', motivo_usuario: 'nao entendi qual cidade ou bairro usar. Me manda o nome, ex: "Pinheiros, SP".', cidade, raio_km } }];
  }"""

A2_ANCHOR = """  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', cidade, estado, raio_km } }];
  }"""
A2_NEW = """  if (!key) {
    return [{ json: { error: 'cidade_nao_encontrada_meta', motivo_usuario: `nao encontrei "${cidade}" no mapa do Meta. Confere o nome, ou tenta a cidade em vez do bairro.`, cidade, estado, raio_km } }];
  }"""

# ---- Edit B: check_gestao_result ----
B_ANCHOR = "else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(verbo)) result = classify('meta_update_adset_targeting');"
B_NEW = """else if (['ALTERAR_PUBLICO', 'ALTERAR_GEO'].includes(verbo)) {
  let bt = null;
  try { bt = $('build_targeting_atualizado').first().json; } catch(e) {}
  if (bt && bt.error) {
    result = { ok: false, classe: 'dado', motivo: bt.motivo_usuario || bt.error };
  } else {
    result = classify('meta_update_adset_targeting');
  }
}"""

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}

def patch(node, pairs):
    jc = N[node]["parameters"]["jsCode"]
    for anchor, new in pairs:
        c = jc.count(anchor)
        if c != 1:
            print(f"ABORTAR [{node}]: ancora apareceu {c}x (esperava 1):\n  {anchor[:70]}...")
            sys.exit(1)
        jc = jc.replace(anchor, new, 1)
    # syntax
    open("/tmp/_chk.js", "w").write("async function _w(){\n" + jc + "\n}\n")
    r = subprocess.run(["node", "--check", "/tmp/_chk.js"], capture_output=True, text=True)
    print(f"  {node}: syntax", "OK" if r.returncode == 0 else "FALHOU")
    if r.returncode:
        print(r.stderr[:600]); sys.exit(1)
    return jc

jc_A = patch("build_targeting_atualizado", [(A_ANCHOR, A_NEW), (A2_ANCHOR, A2_NEW)])
jc_B = patch("check_gestao_result", [(B_ANCHOR, B_NEW)])

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado]")
    sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_geo_fix.json", "w"), ensure_ascii=False, indent=2)
N["build_targeting_atualizado"]["parameters"]["jsCode"] = jc_A
N["check_gestao_result"]["parameters"]["jsCode"] = jc_B
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"],
                        settings={"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")})
print("\nDEPLOYADO. Backup: n8n_workflow/backup_main_pre_geo_fix.json")
