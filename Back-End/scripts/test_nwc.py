from app.core.config import get_settings
import httpx, json

settings = get_settings()
resp = httpx.get(
    "https://data.sec.gov/api/xbrl/companyfacts/CIK0000320193.json",
    headers={"User-Agent": settings.sec_user_agent},
    timeout=30,
)
facts = resp.json()
us_gaap = facts.get("facts", {}).get("us-gaap", {})

# Check for aggregate operating capital change
for concept in ["IncreaseDecreaseInOperatingCapital", "IncreaseDecreaseInOperatingLiabilities",
                 "IncreaseDecreaseInOtherOperatingCapitalNet"]:
    if concept in us_gaap:
        units = us_gaap[concept].get("units", {})
        for unit_key, entries in units.items():
            annuals = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
            if annuals:
                for a in annuals[-4:]:
                    print(f"{concept}: {a.get('val')} ({a.get('start')} to {a.get('end')})")
    else:
        print(f"{concept}: NOT FOUND")

# Also check how the provider maps
print("\n=== Component values for latest 4 years ===")
components = [
    "IncreaseDecreaseInAccountsReceivable",
    "IncreaseDecreaseInInventories",
    "IncreaseDecreaseInAccountsPayable",
    "IncreaseDecreaseInOtherOperatingAssets",
    "IncreaseDecreaseInOtherOperatingLiabilities",
    "IncreaseDecreaseInOtherReceivables",
]
for concept in components:
    if concept in us_gaap:
        units = us_gaap[concept].get("units", {})
        for unit_key, entries in units.items():
            annuals = [e for e in entries if e.get("form") == "10-K" and e.get("fp") == "FY"]
            for a in annuals[-3:]:
                print(f"  {concept}: {a.get('val'):>15,} ({a.get('end')})")
