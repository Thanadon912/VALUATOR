import http from 'k6/http';
import { check, fail } from 'k6';
import {
    assertSafeTargets,
    businessCheckFailures,
    businessCorrectness,
    scenarioOptions,
    SUPABASE_URL,
} from '../config.js';

const anonKey = __ENV.SUPABASE_PUBLISHABLE_KEY || '';

export const options = scenarioOptions({
    vus: Number(__ENV.AUTH_VUS || 2),
    duration: __ENV.AUTH_DURATION || '3m',
});

function tags(route, phase = 'measurement') {
    return {
        route,
        domain: 'auth_saved_stocks',
        scenario: 'auth_saved_stocks',
        cache_state: 'not_applicable',
        ticker_class: 'none',
        provider_mode: 'isolated_supabase',
        test_type: __ENV.PERF_TEST_TYPE || 'auth',
        phase,
    };
}

function headers(token = null) {
    const result = {
        apikey: anonKey,
        'Content-Type': 'application/json',
    };
    if (token) result.Authorization = `Bearer ${token}`;
    return result;
}

function parse(response) {
    try { return response.json(); } catch (_) { return null; }
}

function verify(response, assertions) {
    const ok = check(response, assertions);
    businessCorrectness.add(ok);
    if (!ok) businessCheckFailures.add(1);
    return ok;
}

function createUser(label) {
    const nonce = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const email = `perf-${label}-${nonce}@example.test`;
    const password = `Perf-${nonce}-A1!`;
    const response = http.post(`${SUPABASE_URL}/auth/v1/signup`, JSON.stringify({ email, password }), {
        headers: headers(),
        tags: tags('auth_signup', 'setup'),
    });
    const body = parse(response);
    if (response.status !== 200 || !body?.access_token || !body?.user?.id) {
        fail(`Isolated Supabase signup failed for ${label}: HTTP ${response.status}`);
    }
    return { token: body.access_token, userId: body.user.id };
}

export function setup() {
    assertSafeTargets({ requireSupabase: true });
    if (!anonKey) fail('SUPABASE_PUBLISHABLE_KEY is required');
    const owner = createUser('owner');
    const other = createUser('other');
    const now = new Date().toISOString();
    const seed = http.post(`${SUPABASE_URL}/rest/v1/rpc/merge_saved_stocks`, JSON.stringify({
        p_items: [
            { ticker: 'AAPL', added_at: now, last_visited_at: now, last_section: 'summary' },
            { ticker: 'JPM', added_at: now, last_visited_at: now, last_section: 'valuation' },
        ],
    }), { headers: headers(owner.token), tags: tags('saved_stocks_merge', 'setup') });
    if (seed.status < 200 || seed.status >= 300) fail(`Saved-stock seed failed: HTTP ${seed.status}`);
    return { owner, other };
}

export default function (data) {
    const auth = http.get(`${SUPABASE_URL}/auth/v1/user`, {
        headers: headers(data.owner.token),
        tags: tags('auth_user'),
    });
    verify(auth, { 'auth session belongs to synthetic owner': (r) => r.status === 200 && parse(r)?.id === data.owner.userId });

    const ownerRows = http.get(`${SUPABASE_URL}/rest/v1/saved_stocks?select=ticker,last_section&order=ticker.asc`, {
        headers: headers(data.owner.token),
        tags: tags('saved_stocks'),
    });
    verify(ownerRows, {
        'owner reads exactly its saved stocks': (r) => {
            const rows = parse(r);
            return r.status === 200 && Array.isArray(rows) && rows.map((row) => row.ticker).join(',') === 'AAPL,JPM';
        },
    });

    const isolatedRows = http.get(`${SUPABASE_URL}/rest/v1/saved_stocks?select=ticker`, {
        headers: headers(data.other.token),
        tags: tags('saved_stocks'),
    });
    verify(isolatedRows, { 'second user cannot read owner rows': (r) => r.status === 200 && Array.isArray(parse(r)) && parse(r).length === 0 });

    const denied = http.get(`${SUPABASE_URL}/rest/v1/saved_stocks?select=ticker`, {
        headers: headers(),
        tags: tags('saved_stocks_denied'),
        responseCallback: http.expectedStatuses(401, 403),
    });
    verify(denied, { 'anonymous saved-stock access denied': (r) => r.status === 401 || r.status === 403 });
}

export function teardown(data) {
    http.del(`${SUPABASE_URL}/rest/v1/saved_stocks?user_id=eq.${data.owner.userId}`, null, {
        headers: headers(data.owner.token),
        tags: tags('saved_stocks_cleanup', 'teardown'),
    });
}
