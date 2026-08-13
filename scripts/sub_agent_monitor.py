import sys
import httpx

def check_ticker(ticker, expected_archetype):
    # Call the backend API
    url = f"http://127.0.0.1:8200/api/stocks/{ticker}/summary"
    try:
        response = httpx.get(url, timeout=60.0)
        response.raise_for_status()
    except Exception as e:
        print(f"Error fetching {ticker}: {e}")
        return False
    
    data = response.json()
    sections = data.get("data", {})
    
    # Check data density
    empty_count = 0
    total_count = 0
    
    def count_empty(obj):
        nonlocal empty_count, total_count
        if isinstance(obj, dict):
            for k, v in obj.items():
                count_empty(v)
        elif isinstance(obj, list):
            for item in obj:
                count_empty(item)
        else:
            total_count += 1
            if obj is None or obj == "" or obj == 0:
                empty_count += 1
                
    count_empty(sections)
    
    density = empty_count / total_count if total_count > 0 else 1
    print(f"[{ticker}] ({expected_archetype}) Empty density: {density*100:.2f}% (Threshold 5%)")
    
    if density > 0.05:
        print(f"FAILED: {ticker} exceeds 5% empty threshold.")
        return False
    return True

if __name__ == "__main__":
    success = True
    success &= check_ticker("AAPL", "US GAAP")
    success &= check_ticker("TSM", "IFRS/ADR")
    success &= check_ticker("JPM", "Banking/Financial")
    
    if not success:
        sys.exit(1)
    print("All target anchors passed.")
