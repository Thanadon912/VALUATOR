from app.core.api import get_sec_filings_client
from app.providers.sec import fetch_live_company_data
import asyncio

async def main():
    sec_client = get_sec_filings_client()
    try:
        data = await fetch_live_company_data("AAPL", sec_client)
        print("BALANCE SHEET KEYS:")
        if data.get("balance_sheet") and data["balance_sheet"].get("periods"):
            period = data["balance_sheet"]["periods"][0]
            print(list(period.keys()))
            
            for key in ["short_term_debt", "long_term_debt", "short_term_investments", "long_term_investments"]:
                print(key, period.get(key))
    finally:
        await sec_client.close()

asyncio.run(main())
