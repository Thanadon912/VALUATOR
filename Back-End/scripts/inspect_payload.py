from app.services.dcf import get_dcf_inputs
from app.core.api import get_sec_filings_client
from pprint import pprint
import asyncio

async def main():
    sec_client = get_sec_filings_client()
    try:
        response = await get_dcf_inputs("AAPL", "dcf-vi-latest", sec_client)
        print("ANNUAL METRICS:")
        annual = response["data"]["historical_metrics"]["annual"]
        for row in annual[:3]:
            print(row.keys())
            print("change_in_net_working_capital:", row.get("change_in_net_working_capital"))
            print("revenue:", row.get("revenue"))
        
        print("\nEQUITY BRIDGE INPUTS:")
        eb = response["data"]["equity_bridge_inputs"]
        print(eb.keys())
        for k, v in eb.items():
            print(k, ":", v)
    finally:
        await sec_client.close()

asyncio.run(main())
