# Extrai o prompt VIVO (estavelBlock) do no build_agente_body, decodifica de verdade
# (o literal usa escapes \uXXXX) e salva legivel pra inspecao.
import json, n8n_api

wf = n8n_api.get_workflow("fBUin1UPt5xJEp6g")
jc = {n["name"]: n for n in wf["nodes"]}["build_agente_body"]["parameters"]["jsCode"]

OUT = "/private/tmp/claude-501/-Users-renanreal/ab66a44f-e962-4572-9a57-ed9c526973ed/scratchpad/prompt_vivo.txt"

i = jc.find('const estavelBlock = "')
assert i >= 0, "nao achei estavelBlock"
start = i + len('const estavelBlock = "') - 1   # inclui a aspa de abertura
j = start + 1
while j < len(jc):
    if jc[j] == '"' and jc[j-1] != '\\':
        break
    j += 1
literal = jc[start:j+1]                          # inclui as duas aspas
texto = json.loads(literal)                      # decodifica \n, \", \uXXXX corretamente
open(OUT, "w").write(texto)
print("salvo:", OUT, "| chars:", len(texto))

for bloco in ["Bloco 5 ", "Bloco 6 ", "Bloco 8 "]:
    k = texto.find(bloco)
    end = texto.find("Bloco ", k + 10)
    print(f"\n{'='*25} {bloco.strip()} {'='*25}")
    print(texto[k:end] if k >= 0 else "NAO ENCONTRADO")
