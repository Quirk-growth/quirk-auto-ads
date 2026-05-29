"""
Constantes do projeto Quirk Auto Ads — usadas pelos scripts de build do workflow n8n.

Mantenha tudo aqui pra evitar drift entre scripts.
"""
import os

# ──────────────────────────────────────────────
# n8n
# ──────────────────────────────────────────────
N8N_URL = "https://n8n.quirkgrowth.online"
N8N_API_KEY_PATH = os.path.expanduser("~/.config/n8n-quirk/api_key.txt")

WORKFLOW_NAME = "Quirk Auto Ads"
WEBHOOK_PATH = "quirk-auto-ads"
WORKFLOW_URL = f"{N8N_URL}/webhook/{WEBHOOK_PATH}"

# Persistência local do ID do workflow (não vai pro git)
WORKFLOW_ID_FILE = "/Users/renanreal/quirk_auto_ads/n8n_workflow/.workflow_id"

# ──────────────────────────────────────────────
# Credentials no n8n (IDs criados via API)
# ──────────────────────────────────────────────
POSTGRES_CRED = {"id": "uPzd3Pjx8g5F7GF6", "name": "Quirk Auto Ads Postgres"}
ANTHROPIC_CRED = {"id": "WqFBad1qVsyh6ole", "name": "Quirk Anthropic"}
# Header auth credentials — usadas em HTTP nodes genéricos (Anthropic API + UAZAPI)
ANTHROPIC_HEADER_CRED = {"id": "Hr9Eb7pGMXTH9hD5", "name": "Quirk Anthropic Header"}
UAZAPI_HEADER_CRED = {"id": "CGuMGDKk5aSWIYFS", "name": "Quirk UAZAPI Header"}

# ──────────────────────────────────────────────
# Supabase
# ──────────────────────────────────────────────
SUPABASE_PROJECT_REF = "gnqxetyrurdpjsnkuhli"
SUPABASE_REGION = "sa-east-1"

# ──────────────────────────────────────────────
# Externals
# ──────────────────────────────────────────────
UAZAPI_BASE = "https://quirkgrowth.uazapi.com"
META_GRAPH_BASE = "https://graph.facebook.com/v25.0"

# ──────────────────────────────────────────────
# Prompts (caminhos absolutos pra evitar bug de CWD)
# ──────────────────────────────────────────────
PROMPTS_DIR = "/Users/renanreal/quirk_auto_ads/prompts"

def load_prompt(name: str) -> str:
    """Lê um prompt do diretório prompts/. Argumentos: 'agente_principal', 'classifier', 'extrator'."""
    path = f"{PROMPTS_DIR}/{name}.md"
    with open(path, "r") as f:
        return f.read()


def get_workflow_id() -> str:
    """Lê o ID do workflow do arquivo local."""
    with open(WORKFLOW_ID_FILE) as f:
        return f.read().strip()
