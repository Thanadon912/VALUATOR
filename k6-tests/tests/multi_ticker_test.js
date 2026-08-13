import { scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, requestTickerDataset } from '../modules/user_journey.js';

const duration = __ENV.MULTI_TICKER_DURATION || '3m';
const vus = Number(__ENV.MULTI_TICKER_VUS || 2);
export const options = scenarioOptions({
    scenarios: {
        aapl: { executor: 'constant-vus', exec: 'aapl', vus, duration, tags: { ticker_class: 'verified_us_equity' } },
        jpm: { executor: 'constant-vus', exec: 'jpm', vus, duration, tags: { ticker_class: 'verified_regulated_equity' } },
        tsm: { executor: 'constant-vus', exec: 'tsm', vus, duration, tags: { ticker_class: 'verified_adr_equity' } },
    },
});

export function setup() { return prepareAndVerifyCaches(); }
function run(ticker) { requestTickerDataset(ticker, { cacheOnly: true, phase: 'measurement', scenario: 'multi_ticker' }); }
export function aapl() { run('AAPL'); }
export function jpm() { run('JPM'); }
export function tsm() { run('TSM'); }
