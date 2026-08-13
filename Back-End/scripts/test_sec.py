from app.providers.sec import SecCompanyFactsProvider
from app.core.config import get_settings
import json

settings = get_settings()
provider = SecCompanyFactsProvider(
    user_agent=settings.sec_user_agent,
    timeout_seconds=settings.provider_timeout_seconds,
    supply_chain_ai_enabled=False,
    customer_mix_ai_enabled=False,
)
result = provider.fetch("AAPL")
bs = result.data.get("financial_statements", {}).get("annual", {}).get("balance_sheet", {})
for r in bs.get("rows", []):
    if r["id"] == "cash":
        print(json.dumps(r, indent=2))
