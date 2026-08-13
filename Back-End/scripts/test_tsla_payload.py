import asyncio
from app.api.routes.valuation import calculate_valuations
async def main():
    try:
        from app.services.summary import FinnhubProvider
        provider = FinnhubProvider()
        res = await provider.fetch_financial_data('TSLA')
        import json
        print("Finnhub Data:", json.dumps(res.data.get('financial_statements', {}).get('quarterly', {}).get('cash_flow', {}).get('rows', [])[:3], indent=2))
        print("CFO:", json.dumps(res.data.get('instants', {}).get('netCashFromOperatingActivities'), indent=2))
    except Exception as e:
        print("Err:", e)
asyncio.run(main())
