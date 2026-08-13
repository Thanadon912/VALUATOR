import { scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, valueInvestorJourney } from '../modules/user_journey.js';

export const options = scenarioOptions({
    stages: [
        { duration: __ENV.LOAD_RAMP_UP || '30s', target: Number(__ENV.LOAD_VUS || 5) },
        { duration: __ENV.LOAD_HOLD || '3m', target: Number(__ENV.LOAD_VUS || 5) },
        { duration: __ENV.LOAD_RAMP_DOWN || '30s', target: 0 },
    ],
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () { valueInvestorJourney({ cacheOnly: true, phase: 'measurement', scenario: 'baseline' }); }
