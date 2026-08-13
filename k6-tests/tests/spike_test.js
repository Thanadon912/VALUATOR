import { scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, valueInvestorJourney } from '../modules/user_journey.js';

export const options = scenarioOptions({
    stages: [
        { duration: __ENV.SPIKE_BASELINE || '1m', target: Number(__ENV.SPIKE_BASELINE_VUS || 5) },
        { duration: __ENV.SPIKE_RAMP || '5s', target: Number(__ENV.SPIKE_VUS || 50) },
        { duration: __ENV.SPIKE_HOLD || '1m', target: Number(__ENV.SPIKE_VUS || 50) },
        { duration: __ENV.SPIKE_RECOVERY || '5s', target: Number(__ENV.SPIKE_BASELINE_VUS || 5) },
        { duration: __ENV.SPIKE_OBSERVE || '2m', target: Number(__ENV.SPIKE_BASELINE_VUS || 5) },
        { duration: __ENV.SPIKE_COOLDOWN || '30s', target: 0 },
    ],
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () { valueInvestorJourney({ cacheOnly: true, phase: 'measurement', scenario: 'spike' }); }
