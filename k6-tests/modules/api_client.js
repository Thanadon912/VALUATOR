import http from 'k6/http';
import { check } from 'k6';
import {
    BASE_URL,
    businessCheckFailures,
    businessCorrectness,
    cacheIsolationFailures,
    monteCarloTimeoutCount,
    providerFallbackCount,
    valuationInvalidResults,
} from '../config.js';

const RESPONSE_STATUSES = new Set(['success', 'partial', 'unavailable', 'missing_input', 'stale', 'error']);
const VALUATION_STATUSES = new Set(['CALCULATED', 'APPLICABLE', 'MISSING_INPUT', 'INAPPLICABLE', 'UNAVAILABLE', 'INVALID_INPUT']);
const DCF_METHODS = new Set([
    'Standard Driver-Based DCF',
    'Capitalized R&D DCF',
    'Regulatory FCFE',
    'Normalized Median DCF',
]);
const contractResults = new Map();

function finite(value) {
    return typeof value === 'number' && Number.isFinite(value);
}

function safeJson(response) {
    try {
        return response.json();
    } catch (_) {
        return null;
    }
}

function tickerClass(ticker) {
    return ticker ? 'verified_equity' : 'none';
}

function requestOptions(route, domain, options = {}) {
    const cacheOnly = options.cacheOnly !== false;
    return {
        tags: {
            route,
            domain,
            scenario: options.scenario || __ENV.PERF_SCENARIO || 'unspecified',
            cache_state: cacheOnly ? 'warm' : 'live_warmup',
            ticker_class: tickerClass(options.ticker),
            provider_mode: cacheOnly ? 'cache_only' : 'live_integration',
            test_type: __ENV.PERF_TEST_TYPE || 'manual',
            phase: options.phase || 'measurement',
            name: options.name || route,
        },
        headers: cacheOnly ? { 'X-VALUATOR-Cache-Only': 'true' } : {},
        timeout: options.timeout || '60s',
    };
}

function record(response, label, predicate, metric = businessCheckFailures, skip = false) {
    if (skip) {
        contractResults.set(response.url, true);
        return true;
    }
    const ok = check(response, { [label]: predicate });
    contractResults.set(response.url, (contractResults.get(response.url) ?? true) && ok);
    businessCorrectness.add(ok);
    if (!ok) metric.add(1);
    return ok;
}

export function contractPassed(response) {
    return contractResults.get(response.url) !== false;
}

function recordWarnings(payload) {
    const warnings = Array.isArray(payload?.warnings) ? payload.warnings : [];
    const assumptions = payload?.underlying_assumptions || {};
    const computational = Array.isArray(assumptions.computational_warnings)
        ? assumptions.computational_warnings
        : [];
    for (const warning of warnings.concat(computational)) {
        if (/fallback|provider/i.test(String(warning))) providerFallbackCount.add(1);
        if (/monte carlo.*timeout|timeout.*monte carlo/i.test(String(warning))) monteCarloTimeoutCount.add(1);
    }
}

function validateModule(module) {
    return module && RESPONSE_STATUSES.has(module.status)
        && typeof module.message === 'string'
        && Array.isArray(module.source_refs);
}

function validateValuationPayload(payload, ticker, route) {
    if (!payload || payload.ticker !== ticker || !VALUATION_STATUSES.has(payload.valuation_status)) return false;
    if (typeof payload.timestamp !== 'string' || Number.isNaN(Date.parse(payload.timestamp))) return false;
    if (typeof payload.valuation_methodology !== 'string' || !payload.valuation_methodology) return false;
    if (!payload.engine_metadata || !Array.isArray(payload.projections)
        || !payload.monte_carlo_results || !payload.implied_expectations
        || !payload.underlying_assumptions) return false;
    if (!finite(payload.margin_of_safety_percentage)) return false;
    if (payload.valuation_status === 'CALCULATED' || payload.valuation_status === 'APPLICABLE') {
        if (!finite(payload.computed_fair_value) || payload.computed_fair_value <= 0) return false;
    } else if (payload.valuation_status === 'INAPPLICABLE') {
        if (payload.computed_fair_value !== null && !finite(payload.computed_fair_value)) return false;
    } else if (payload.computed_fair_value !== null) {
        return false;
    }
    if (route === 'dcf' && payload.valuation_status === 'CALCULATED') {
        if (!DCF_METHODS.has(payload.valuation_methodology)) return false;
        const mc = payload.monte_carlo_results;
        const percentiles = [mc.bear_p10, mc.base_p50, mc.bull_p90];
        if (percentiles.every(finite)) {
            if (!(mc.bear_p10 <= mc.base_p50 && mc.base_p50 <= mc.bull_p90)) return false;
            if (mc.iteration_count !== 10_000 || mc.valid_sample_count !== 10_000) return false;
        } else {
            if (!percentiles.every((value) => value === null || value === undefined)) return false;
            const warnings = payload.underlying_assumptions.computational_warnings;
            if (!Array.isArray(warnings)
                || !warnings.some((warning) => /Monte Carlo unavailable: insufficient comparable annual history/i.test(String(warning)))) {
                return false;
            }
        }
        if (Object.keys(payload.implied_expectations).length === 0) {
            const warnings = payload.underlying_assumptions.computational_warnings;
            if (!Array.isArray(warnings) || warnings.length === 0) return false;
        }
    }
    return true;
}

export function healthCheck(options = {}) {
    const res = http.get(`${BASE_URL}/health`, requestOptions('health', 'platform', { ...options, cacheOnly: true }));
    record(res, 'health contract', (r) => r.status === 200 && safeJson(r)?.status === 'ok');
    return res;
}

export function getSummary(ticker, options = {}) {
    const res = http.get(`${BASE_URL}/api/stocks/${ticker}/summary`, requestOptions('summary', 'stock_data', { ...options, ticker }));
    record(res, 'summary contract and ticker isolation', (r) => {
        const body = safeJson(r);
        const data = body?.data;
        return r.status === 200 && body?.ticker === ticker && RESPONSE_STATUSES.has(body?.status)
            && Array.isArray(body?.sources) && Array.isArray(body?.warnings)
            && ['quote', 'key_facts', 'company_overview', 'valuation_measures', 'financial_highlights']
                .every((name) => validateModule(data?.[name]));
    }, cacheIsolationFailures, options.phase === 'warmup');
    return res;
}

export function getQuote(ticker, options = {}) {
    const res = http.get(`${BASE_URL}/api/stocks/${ticker}/quote`, requestOptions('quote', 'stock_data', { ...options, ticker }));
    record(res, 'quote contract and ticker isolation', (r) => {
        const body = safeJson(r);
        return r.status === 200 && body?.ticker === ticker && body?.data?.symbol === ticker
            && RESPONSE_STATUSES.has(body?.status) && Array.isArray(body?.sources) && Array.isArray(body?.warnings)
            && (body.data.price === null || finite(body.data.price));
    }, cacheIsolationFailures, options.phase === 'warmup');
    return res;
}

export function getNews(ticker, options = {}) {
    const res = http.get(`${BASE_URL}/api/stocks/${ticker}/news`, requestOptions('news', 'stock_data', { ...options, ticker }));
    record(res, 'news contract and ticker isolation', (r) => {
        const body = safeJson(r);
        return r.status === 200 && body?.ticker === ticker
            && typeof body?.status === 'string' && body.status.startsWith('success')
            && Array.isArray(body?.articles)
            && body.articles.every((article) => Number.isInteger(article.id)
                && typeof article.headline === 'string'
                && typeof article.summary === 'string'
                && typeof article.source === 'string'
                && Number.isInteger(article.timestamp)
                && typeof article.url === 'string'
                && typeof article.image === 'string'
                && typeof article.topic === 'string'
                && finite(article.relevance_score));
    }, cacheIsolationFailures, options.phase === 'warmup');
    return res;
}

export function getMethodology(ticker, options = {}) {
    const res = http.get(`${BASE_URL}/api/v1/valuation/methodology?ticker=${ticker}`, requestOptions('methodology', 'valuation', { ...options, ticker }));
    record(res, 'methodology contract and ticker isolation', (r) => {
        const body = safeJson(r);
        return r.status === 200 && body?.ticker === ticker && RESPONSE_STATUSES.has(body?.status)
            && DCF_METHODS.has(body?.methodology) && Array.isArray(body?.warnings);
    }, cacheIsolationFailures, options.phase === 'warmup');
    return res;
}

function valuationRequest(route, path, ticker, options = {}) {
    const res = http.get(`${BASE_URL}${path}?ticker=${ticker}`, requestOptions(route, 'valuation', {
        ...options,
        ticker,
        timeout: route === 'dcf' || route === 'relative' ? '90s' : '60s',
    }));
    const valid = record(res, `${route} business contract`, (r) => {
        const body = safeJson(r);
        recordWarnings(body);
        return r.status === 200 && validateValuationPayload(body, ticker, route);
    }, valuationInvalidResults, options.phase === 'warmup');
    if (!valid && res.status === 503) cacheIsolationFailures.add(1);
    return res;
}

export function getDCF(ticker, options = {}) { return valuationRequest('dcf', '/api/v1/valuation/dcf', ticker, options); }
export function getDDM(ticker, options = {}) { return valuationRequest('ddm', '/api/v1/valuation/ddm', ticker, options); }
export function getAssetBased(ticker, options = {}) { return valuationRequest('asset_based', '/api/v1/valuation/asset-based', ticker, options); }
export function getRelative(ticker, options = {}) { return valuationRequest('relative', '/api/v1/valuation/relative', ticker, options); }
export function getResidualIncome(ticker, options = {}) { return valuationRequest('residual_income', '/api/v1/valuation/residual-income', ticker, options); }

export function getSnapshots(tickers, options = {}) {
    const unique = [...new Set(tickers)];
    const query = encodeURIComponent(unique.join(','));
    const res = http.get(`${BASE_URL}/api/stocks/snapshots?tickers=${query}`, requestOptions('snapshots', 'saved_stocks', options));
    record(res, 'snapshot order, schema, and ticker isolation', (r) => {
        const body = safeJson(r);
        if (r.status !== 200 || !RESPONSE_STATUSES.has(body?.status) || !Array.isArray(body?.data)) return false;
        if (body.data.length !== unique.length || body.data.some((item, i) => item.ticker !== unique[i])) return false;
        return body.data.every((item) => RESPONSE_STATUSES.has(item.status)
            && Array.isArray(item.sources) && Array.isArray(item.warnings)
            && (item.price === null || finite(item.price)));
    }, cacheIsolationFailures, options.phase === 'warmup');
    return res;
}

export function invalidTickerContract(options = {}) {
    const params = requestOptions('invalid_ticker', 'negative_contract', options);
    params.responseCallback = http.expectedStatuses(422);
    const res = http.get(`${BASE_URL}/api/stocks/%24BAD/summary`, params);
    record(res, 'invalid ticker returns 422', (r) => r.status === 422 && safeJson(r)?.detail);
    return res;
}

export function tooManySnapshotsContract(options = {}) {
    const tickers = Array.from({ length: 21 }, (_, index) => `T${index}`).join(',');
    const params = requestOptions('snapshots_limit', 'negative_contract', options);
    params.responseCallback = http.expectedStatuses(422);
    const res = http.get(`${BASE_URL}/api/stocks/snapshots?tickers=${tickers}`, params);
    record(res, 'snapshots reject more than 20 tickers', (r) => r.status === 422 && /maximum of 20/i.test(String(safeJson(r)?.detail)));
    return res;
}

export function cacheMissContract(ticker, options = {}) {
    const params = requestOptions('cache_miss', 'negative_contract', {
        ...options,
        ticker,
        cacheOnly: true,
    });
    params.responseCallback = http.expectedStatuses(503);
    const res = http.get(`${BASE_URL}/api/stocks/${ticker}/summary`, params);
    record(res, 'cold cache miss is explicit', (r) => {
        const detail = safeJson(r)?.detail;
        return r.status === 503 && detail?.code === 'performance_cache_miss'
            && typeof detail?.resource === 'string' && detail.resource.length > 0;
    });
    return res;
}
