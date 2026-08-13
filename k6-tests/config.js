import { Counter, Rate } from 'k6/metrics';

export const BASE_URL = __ENV.BASE_URL || 'http://127.0.0.1:8200';
export const SUPABASE_URL = __ENV.SUPABASE_URL || 'http://127.0.0.1:56321';

export const businessCheckFailures = new Counter('business_check_failures');
export const valuationInvalidResults = new Counter('valuation_invalid_results');
export const cacheIsolationFailures = new Counter('cache_isolation_failures');
export const providerFallbackCount = new Counter('provider_fallback_count');
export const monteCarloTimeoutCount = new Counter('monte_carlo_timeout_count');
export const businessCorrectness = new Rate('business_correctness');

const LOOPBACK_TARGET = /^http:\/\/(127\.0\.0\.1|localhost|\[::1\])(?::\d+)?(?:\/|$)/i;

export function assertSafeTargets({ requireSupabase = false } = {}) {
    if (__ENV.PERF_TARGET_ACK !== 'local-dedicated') {
        throw new Error('PERF_TARGET_ACK=local-dedicated is required');
    }
    if (!LOOPBACK_TARGET.test(BASE_URL)) {
        throw new Error(`Unsafe BASE_URL rejected: ${BASE_URL}`);
    }
    if (requireSupabase && !LOOPBACK_TARGET.test(SUPABASE_URL)) {
        throw new Error(`Unsafe SUPABASE_URL rejected: ${SUPABASE_URL}`);
    }
}

export const COMMON_THRESHOLDS = {
    checks: ['rate==1'],
    business_correctness: ['rate==1'],
    business_check_failures: ['count==0'],
    valuation_invalid_results: ['count==0'],
    cache_isolation_failures: ['count==0'],
    monte_carlo_timeout_count: ['count==0'],
    'http_req_failed{phase:measurement}': ['rate<0.01'],
    'http_req_duration{route:health,phase:measurement}': ['p(95)<250'],
    'http_req_duration{route:snapshots,phase:measurement}': ['p(95)<3000'],
    'http_req_duration{route:summary,phase:measurement}': ['p(95)<2000'],
    'http_req_duration{route:quote,phase:measurement}': ['p(95)<1000'],
    'http_req_duration{route:news,phase:measurement}': ['p(95)<2000'],
    'http_req_duration{route:methodology,phase:measurement}': ['p(95)<1000'],
    'http_req_duration{route:dcf,phase:measurement}': ['p(95)<20000'],
    'http_req_duration{route:ddm,phase:measurement}': ['p(95)<5000'],
    'http_req_duration{route:asset_based,phase:measurement}': ['p(95)<5000'],
    'http_req_duration{route:relative,phase:measurement}': ['p(95)<5000'],
    'http_req_duration{route:residual_income,phase:measurement}': ['p(95)<5000'],
    'http_req_duration{route:auth_user,phase:measurement}': ['p(95)<1000'],
    'http_req_duration{route:saved_stocks,phase:measurement}': ['p(95)<1000'],
};

export const SUMMARY_TREND_STATS = ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'];

export function scenarioOptions(overrides = {}) {
    return {
        setupTimeout: __ENV.SETUP_TIMEOUT || '15m',
        summaryTrendStats: SUMMARY_TREND_STATS,
        thresholds: COMMON_THRESHOLDS,
        ...overrides,
    };
}
