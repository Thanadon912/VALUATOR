import urllib.request
import json
from datetime import datetime
from threading import Lock
from time import monotonic

YAHOO_QUOTE_CACHE_TTL_SECONDS = 8
YAHOO_SUMMARY_CACHE_TTL_SECONDS = 6 * 60 * 60

_cookie_jar = None
_crumb = None
_lock = Lock()

def _get_opener():
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    return opener

def _init_session():
    global _crumb, _cookie_jar
    with _lock:
        if _crumb:
            return
        opener = _get_opener()
        try:
            opener.open("https://fc.yahoo.com", timeout=5)
        except Exception:
            pass
        try:
            res = opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
            _crumb = res.read().decode("utf-8").strip()
            # Store the opener in global state so it retains cookies?
            # actually urllib.request.HTTPCookieProcessor uses a global CookieJar by default if we don't pass one, wait, no it doesn't.
            # Let's just create one and store it.
        except Exception:
            pass
import http.cookiejar

class YahooQuoteProvider:
    def __init__(self):
        self.cookie_jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookie_jar))
        self.opener.addheaders = [("User-Agent", "Mozilla/5.0")]
        self.crumb = None
        self._cache_lock = Lock()
        self._quote_cache = {}
        self._summary_cache = {}
        self._request_locks = {}

    def _request_lock(self, kind: str, ticker: str):
        key = (kind, ticker)
        with self._cache_lock:
            return self._request_locks.setdefault(key, Lock())

    def _cached(self, cache: dict, ticker: str, ttl_seconds: int):
        with self._cache_lock:
            cached = cache.get(ticker)
            if cached and monotonic() - cached[0] < ttl_seconds:
                return cached[1]
        return None

    def _store(self, cache: dict, ticker: str, payload: dict) -> None:
        if payload:
            with self._cache_lock:
                cache[ticker] = (monotonic(), payload)

    def _ensure_crumb(self):
        with _lock:
            if self.crumb:
                return
            try:
                self.opener.open("https://fc.yahoo.com", timeout=5)
            except Exception:
                pass
            try:
                res = self.opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=5)
                self.crumb = res.read().decode("utf-8").strip()
            except Exception:
                pass

    def get_quote(self, ticker: str) -> dict:
        normalized = ticker.upper()
        cached = self._cached(self._quote_cache, normalized, YAHOO_QUOTE_CACHE_TTL_SECONDS)
        if cached is not None:
            return cached
        with self._request_lock("quote", normalized):
            cached = self._cached(self._quote_cache, normalized, YAHOO_QUOTE_CACHE_TTL_SECONDS)
            if cached is not None:
                return cached
            payload = self._fetch_quote(normalized)
            self._store(self._quote_cache, normalized, payload)
            return payload

    def _fetch_quote(self, ticker: str) -> dict:
        self._ensure_crumb()
        if not self.crumb:
            return {}
        try:
            url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={ticker}&crumb={self.crumb}"
            res = self.opener.open(url, timeout=5)
            data = json.loads(res.read())
            results = data.get("quoteResponse", {}).get("result", [])
            if not results:
                return {}
            
            quote = results[0]
            
            # Map Yahoo fields to our standard format
            mapped = {
                "regularMarketPrice": quote.get("regularMarketPrice"),
                "regularMarketChange": quote.get("regularMarketChange"),
                "regularMarketChangePercent": quote.get("regularMarketChangePercent"),
                "marketCap": quote.get("marketCap"),
                "beta": quote.get("beta"),
                "trailingPE": quote.get("trailingPE"),
                "forwardPE": quote.get("forwardPE"),
                "epsTrailingTwelveMonths": quote.get("epsTrailingTwelveMonths"),
                "priceToBook": quote.get("priceToBook"),
                "bookValue": quote.get("bookValue"),
                "priceToSalesTrailing12Months": quote.get("priceToSalesTrailing12Months"),
                "enterpriseValue": quote.get("enterpriseValue"),
                "enterpriseToEbitda": quote.get("enterpriseToEbitda"),
                "sharesOutstanding": quote.get("sharesOutstanding"),
                "fiftyTwoWeekChangePercent": quote.get("fiftyTwoWeekChangePercent"),
                "fiftyTwoWeekChange": quote.get("fiftyTwoWeekChange"),
                "quoteType": quote.get("quoteType"),
                "currency": quote.get("currency"),
                "extendedPrice": quote.get("postMarketPrice") or quote.get("preMarketPrice"),
                "extendedChange": quote.get("postMarketChange") or quote.get("preMarketChange"),
                "extendedChangePercent": quote.get("postMarketChangePercent") or quote.get("preMarketChangePercent"),
                "marketState": quote.get("marketState", "REGULAR"),
            }
            
            # timestamp formatting
            post_time = quote.get("postMarketTime")
            pre_time = quote.get("preMarketTime")
            ext_time = post_time or pre_time
            if ext_time:
                mapped["extendedHoursTimestamp"] = datetime.fromtimestamp(ext_time).strftime("%b %d at %I:%M:%S %p EDT")
            else:
                mapped["extendedHoursTimestamp"] = None
                
            reg_time = quote.get("regularMarketTime")
            if reg_time:
                mapped["regularMarketTime"] = datetime.fromtimestamp(reg_time).strftime("%b %d at %I:%M:%S %p EDT")
            else:
                mapped["regularMarketTime"] = None
                
            return mapped
        except Exception:
            return {}

    def get_quote_summary_metrics(self, ticker: str) -> dict:
        normalized = ticker.upper()
        cached = self._cached(
            self._summary_cache,
            normalized,
            YAHOO_SUMMARY_CACHE_TTL_SECONDS,
        )
        if cached is not None:
            return cached
        with self._request_lock("summary", normalized):
            cached = self._cached(
                self._summary_cache,
                normalized,
                YAHOO_SUMMARY_CACHE_TTL_SECONDS,
            )
            if cached is not None:
                return cached
            payload = self._fetch_quote_summary_metrics(normalized)
            self._store(self._summary_cache, normalized, payload)
            return payload

    def _fetch_quote_summary_metrics(self, ticker: str) -> dict:
        self._ensure_crumb()
        if not self.crumb:
            return {}
        try:
            modules = "defaultKeyStatistics,financialData,summaryDetail"
            url = (
                f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{ticker}"
                f"?modules={modules}&crumb={self.crumb}"
            )
            res = self.opener.open(url, timeout=10)
            data = json.loads(res.read())
            result = (data.get("quoteSummary", {}).get("result") or [{}])[0]
            default_stats = result.get("defaultKeyStatistics", {}) or {}
            financial_data = result.get("financialData", {}) or {}
            summary_detail = result.get("summaryDetail", {}) or {}

            def raw(obj: dict, key: str):
                value = obj.get(key)
                if isinstance(value, dict):
                    return value.get("raw")
                return value

            return {
                "enterpriseValue": raw(default_stats, "enterpriseValue"),
                "enterpriseToEbitda": raw(default_stats, "enterpriseToEbitda"),
                "ebitda": raw(financial_data, "ebitda"),
                "totalCash": raw(financial_data, "totalCash"),
                "totalDebt": raw(financial_data, "totalDebt"),
                "trailingPE": raw(summary_detail, "trailingPE") or raw(default_stats, "trailingPE"),
                "forwardPE": raw(summary_detail, "forwardPE") or raw(default_stats, "forwardPE"),
                "trailingEps": raw(default_stats, "trailingEps"),
                "priceToBook": raw(default_stats, "priceToBook"),
                "bookValue": raw(default_stats, "bookValue"),
            }
        except Exception:
            return {}

yahoo_provider = YahooQuoteProvider()

def get_yahoo_quote(ticker: str) -> dict:
    return yahoo_provider.get_quote(ticker)

def get_yahoo_quote_summary_metrics(ticker: str) -> dict:
    return yahoo_provider.get_quote_summary_metrics(ticker)

def get_yahoo_52w_change(ticker: str) -> float | None:
    try:
        quote = get_yahoo_quote(ticker)
        val = quote.get("fiftyTwoWeekChangePercent")
        if val is None:
            val = quote.get("fiftyTwoWeekChange")
        if val is not None:
            return float(val)
    except Exception:
        pass
    return None
