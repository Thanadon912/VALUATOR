import sys
import time
from playwright.sync_api import sync_playwright

STOCKS = ["AAPL", "TSM", "JPM"]
TABS = ["summary", "statistics", "profile", "financials", "holders", "capital-allocation", "dcf"]

def check_pages():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        results = {}
        for stock in STOCKS:
            results[stock] = {}
            for tab in TABS:
                url = f"http://localhost:3001/stocks/{stock}/{tab}"
                print(f"Visiting {url} ...")
                page.goto(url, timeout=60000)
                
                # wait for page to load data
                try:
                    page.wait_for_load_state('networkidle', timeout=60000)
                    # wait an extra 2 seconds for any react rendering
                    time.sleep(2)
                except Exception as e:
                    print(f"Timeout waiting for network idle on {url}: {e}")
                
                content = page.locator('body').inner_text()
                
                # Search for missing data indicators
                missing_keywords = ["Not reported", "NaN", "—"] 
                
                found_issues = []
                for kw in missing_keywords:
                    count = content.count(kw)
                    if count > 0:
                        found_issues.append(f"{kw}: {count}")
                        # Find the first few occurrences and print surrounding text
                        idx = -1
                        occurrences = 0
                        while True:
                            idx = content.find(kw, idx + 1)
                            if idx == -1 or occurrences >= 5:
                                break
                            start = max(0, idx - 30)
                            end = min(len(content), idx + len(kw) + 30)
                            context = content[start:end].replace('\n', ' ').strip()
                            print(f"    Context '{kw}': ...{context}...")
                            occurrences += 1
                
                if ">null<" in content:
                    found_issues.append("null: rendered in UI")

                results[stock][tab] = found_issues
                if found_issues:
                    print(f"  [!] Found issues in {stock} / {tab}: {', '.join(found_issues)}")
                    page.screenshot(path=f"/tmp/screenshot_{stock}_{tab}.png", full_page=True)
                else:
                    print(f"  [OK] No missing data text found.")

        browser.close()
        
        print("\n--- SUMMARY ---")
        for stock in STOCKS:
            for tab in TABS:
                if results[stock][tab]:
                    print(f"{stock} - {tab}: {results[stock][tab]}")

if __name__ == "__main__":
    check_pages()
