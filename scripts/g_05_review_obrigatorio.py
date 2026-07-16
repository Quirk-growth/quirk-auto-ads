# scripts/g_05_review_obrigatorio.py
# Corrige 3 problemas reais do prompt vivo (build_agente_body / estavelBlock):
#  1) Bloco 6 passo 9 ("aguarde o 'sim'") contradiz o Bloco 8 -> agente pula o review.
#  2) Diferencial nao bloqueia avancar (so valor/regiao/criativo bloqueiam).
#  3) Verba so aparece no passo 8; nao esta na coleta inicial.
#  + Metragem e quantidade de comodos nao existiam no prompt.
# O literal do prompt usa escapes \uXXXX -> ancoras convertidas com json.dumps(ensure_ascii=True).
#   python3 g_05_review_obrigatorio.py          -> dry-run (+ syntax check)
#   python3 g_05_review_obrigatorio.py deploy   -> aplica (backup antes)
import json, subprocess, sys, n8n_api

WF = "fBUin1UPt5xJEp6g"
DEPLOY = len(sys.argv) > 1 and sys.argv[1] == "deploy"

REPLACES = [
    # 1) pergunta inicial: inclui metragem, comodos, diferencial e verba
    (
        'Exemplo de tom: "Pra montar a campanha preciso de: tipo do imóvel, valor, bairro/região e o objetivo (morar, investir ou veraneio). Pode me passar?"',
        'Exemplo de tom: "Pra montar a campanha preciso de: tipo do imóvel, valor, metragem, quantos cômodos, bairro/cidade, o objetivo (morar, investir ou veraneio), o diferencial do produto e a verba diária (entre R$10 e R$100). Pode me passar?"'
    ),
    # 2) lista de dados: acrescenta metragem e comodos
    (
        '- Tipo de imóvel e fase (lançamento, pronto, estoque)',
        '- Tipo de imóvel e fase (lançamento, pronto, estoque)\n- Metragem (m²)\n- Quantidade de cômodos (quartos/suítes/vagas)'
    ),
    # 3) itens que bloqueiam avancar: agora inclui metragem, comodos, diferencial e verba
    (
        'ITENS QUE BLOQUEIAM AVANÇAR (não siga sem eles): valor do imóvel, BAIRRO/REGIÃO EXATA e criativo recebido. Sem região confirmada = campanha no Brasil todo (erro grave). Faltou algum? Pergunte de forma curta antes de prosseguir.',
        'ITENS QUE BLOQUEIAM AVANÇAR (não siga sem eles): valor do imóvel, BAIRRO/REGIÃO EXATA, criativo recebido, METRAGEM, QUANTIDADE DE CÔMODOS, DIFERENCIAL DO PRODUTO e VERBA DIÁRIA (entre R$10 e R$100). Sem região confirmada = campanha no Brasil todo (erro grave). O diferencial, a metragem e os cômodos são o que enriquecem o anúncio — NUNCA prossiga sem eles. Faltou algum? Pergunte de forma curta antes de prosseguir.'
    ),
    # 4) Bloco 6 passos 8 e 9: verba ja coletada + mata o "aguarde o sim"
    (
        '8. Sugira a FAIXA de verba de forma SUCINTA — uma frase, sem explicação longa.\n9. Faça um resumo curto da campanha e aguarde o "sim".',
        '8. A verba já foi coletada no Bloco 5. Só se o cliente não souber definir, sugira a FAIXA de forma SUCINTA — uma frase, sem explicação longa (sempre entre R$10 e R$100/dia).\n9. Apresente o REVIEW COMPLETO OBRIGATÓRIO (Bloco 8) e aguarde a palavra CONFIRMADO. NUNCA aceite "sim", "ok" ou similar como confirmação.'
    ),
    # 5) Bloco 8 item 2: review completo obrigatorio com checklist + proibicao
    (
        '2. Faça um resumo CURTO incluindo OBRIGATORIAMENTE: nome da campanha, objetivo, BAIRRO/CIDADE/REGIÃO EXATA do imóvel, público (rótulo Quirk), FAIXA ETÁRIA (ex: 30–64 anos), VERBA DIÁRIA COMO NÚMERO FECHADO. Em poucas linhas, não um relatório. Sem região ou faixa etária no resumo = NÃO mostre CONFIRMAR.',
        '2. REVIEW COMPLETO OBRIGATÓRIO — o resumo DEVE conter TODOS estes itens, sem exceção: nome da campanha, objetivo, tipo + VALOR do imóvel, METRAGEM, QUANTIDADE DE CÔMODOS, DIFERENCIAL DO PRODUTO, BAIRRO/CIDADE/REGIÃO EXATA, público (rótulo Quirk), FAIXA ETÁRIA (ex: 30–64 anos), VERBA DIÁRIA COMO NÚMERO FECHADO e qual CRIATIVO será usado. Formato: lista de linhas curtas — enxuto, mas COMPLETO; não pule item. Faltou QUALQUER um destes = É PROIBIDO mostrar CONFIRMADO; pergunte o que falta antes. Receber o criativo NÃO é gatilho de confirmação — o review completo vem SEMPRE antes de qualquer campanha subir.'
    ),
]

def to_js(s):
    return json.dumps(s, ensure_ascii=True)[1:-1]

wf = n8n_api.get_workflow(WF)
N = {n["name"]: n for n in wf["nodes"]}
jc = N["build_agente_body"]["parameters"]["jsCode"]
orig_len = len(jc)

for i, (old, new) in enumerate(REPLACES, 1):
    o, nw = to_js(old), to_js(new)
    c = jc.count(o)
    print(f"[{i}] âncora encontrada {c}x — {old[:60]}...")
    if c != 1:
        print(f"    ABORTAR: esperava 1 ocorrência, achei {c}"); sys.exit(1)
    jc = jc.replace(o, nw, 1)

print(f"\nlen: {orig_len} -> {len(jc)} (delta {len(jc)-orig_len})")

open("/tmp/_g05check.js", "w").write("async function _w(){\n" + jc + "\n}\n")
r = subprocess.run(["node", "--check", "/tmp/_g05check.js"], capture_output=True, text=True)
print("SYNTAX CHECK:", "OK" if r.returncode == 0 else "FALHOU")
if r.returncode != 0:
    print(r.stderr[:800]); sys.exit(1)

if not DEPLOY:
    print("\n[DRY-RUN — nada deployado.]"); sys.exit(0)

json.dump(wf, open("../n8n_workflow/backup_main_pre_review.json", "w"), ensure_ascii=False, indent=2)
N["build_agente_body"]["parameters"]["jsCode"] = jc
clean_settings = {"executionOrder": wf.get("settings", {}).get("executionOrder", "v1")}
n8n_api.update_workflow(WF, nodes=wf["nodes"], connections=wf["connections"], settings=clean_settings)
print("\nDEPLOYADO: review obrigatório + diferencial/metragem/cômodos/verba bloqueantes. Backup salvo.")
