import { scenarioOptions } from '../config.js';
import { getDCF } from '../modules/api_client.js';
import { prepareAndVerifyCaches, tickers } from '../modules/user_journey.js';

export const options = scenarioOptions({
    vus: Number(__ENV.CPU_VUS || 2),
    duration: __ENV.CPU_DURATION || '3m',
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () {
    getDCF(tickers[(__VU + __ITER) % tickers.length], {
        cacheOnly: true,
        phase: 'measurement',
        scenario: 'cpu_dcf_10000_mc',
    });
}
