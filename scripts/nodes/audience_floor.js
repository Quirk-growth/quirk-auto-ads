// MOTOR DE TAMANHO DE PÚBLICO (decisão interna Quirk — cliente não vê).
// Estima o público na Meta; se < 50k, AFROUXA sozinho e re-estima até ter volume.
// Ordem de afrouxamento (preserva a estratégia): camadas extras -> iOS -> base viajante (última).
const v = $('validate').first().json;
let t = JSON.parse(JSON.stringify(v.json_extrator.targeting_meta));
const adAccountId = v.cliente.ad_account_id;
const token = $('load_meta_token').first().json.valor;
const apiBase = 'https://graph.facebook.com/v25.0';
const FLOOR = 50000;

async function estimate(spec) {
  try {
    const url = `${apiBase}/act_${adAccountId}/delivery_estimate?optimization_goal=REACH`
      + `&targeting_spec=${encodeURIComponent(JSON.stringify(spec))}`
      + `&access_token=${encodeURIComponent(token)}`;
    const r = await this.helpers.httpRequest({ method: 'GET', url, returnFullResponse: false });
    const d = (typeof r === 'string') ? JSON.parse(r) : r;
    const de = (d.data || [{}])[0];
    const lo = de.estimate_mau_lower_bound;
    return (lo === undefined || lo === null) ? -1 : lo;
  } catch (e) { return -1; } // -1 = não consegui estimar -> não afrouxa, sobe como está
}

let size = await estimate.call(this, t);
const trilha = [{ etapa: 'original', size }];

let guard = 0;
while (size >= 0 && size < FLOOR && guard++ < 8) {
  let mudou = false;
  if (t.flexible_spec && t.flexible_spec.length > 1) {
    t.flexible_spec.pop();                 // 1) tira camadas extras (secundário/valor), mantém a base
    mudou = true;
  } else if (t.user_os) {
    delete t.user_os;                      // 2) tira iOS
    mudou = true;
  } else if (t.flexible_spec && t.flexible_spec.length === 1) {
    delete t.flexible_spec;                // 3) por fim, tira a própria base viajante (= abre)
    mudou = true;
  }
  if (!mudou) break;                       // já é o mais aberto (região pequena) — usa assim mesmo
  size = await estimate.call(this, t);
  trilha.push({ etapa: 'afrouxou', size });
}

return [{ json: {
  targeting_meta: t,
  publico_final_size: size,
  afrouxou: trilha.length > 1,
  trilha,
  publico_original: v.json_extrator.publico_escolhido,
}}];
