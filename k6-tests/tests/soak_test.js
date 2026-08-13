import { scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, valueInvestorJourney } from '../modules/user_journey.js';

export const options = scenarioOptions({
    setupTimeout: __ENV.SOAK_SETUP_TIMEOUT || '15m',
    stages: [
        { duration: __ENV.SOAK_RAMP_UP || '1m', target: Number(__ENV.SOAK_VUS || 5) },
        { duration: __ENV.SOAK_HOLD || '30m', target: Number(__ENV.SOAK_VUS || 5) },
        { duration: __ENV.SOAK_RAMP_DOWN || '1m', target: 0 },
    ],
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () { valueInvestorJourney({ cacheOnly: true, phase: 'measurement', scenario: 'soak_30m' }); }
