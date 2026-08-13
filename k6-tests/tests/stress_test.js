import { COMMON_THRESHOLDS, scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, valueInvestorJourney } from '../modules/user_journey.js';

export const options = scenarioOptions({
    stages: [
        { duration: __ENV.STRESS_STAGE_1 || '1m', target: Number(__ENV.STRESS_VUS_1 || 5) },
        { duration: __ENV.STRESS_STAGE_2 || '2m', target: Number(__ENV.STRESS_VUS_2 || 10) },
        { duration: __ENV.STRESS_STAGE_3 || '2m', target: Number(__ENV.STRESS_VUS_3 || 20) },
        { duration: __ENV.STRESS_STAGE_4 || '2m', target: Number(__ENV.STRESS_VUS_4 || 40) },
        { duration: __ENV.STRESS_STAGE_5 || '1m', target: Number(__ENV.STRESS_VUS_5 || 80) },
        { duration: __ENV.STRESS_RECOVERY || '2m', target: Number(__ENV.STRESS_RECOVERY_VUS || 5) },
        { duration: __ENV.STRESS_COOLDOWN || '30s', target: 0 },
    ],
    thresholds: {
        ...COMMON_THRESHOLDS,
        'http_req_failed{phase:measurement}': [{ threshold: 'rate<0.10', abortOnFail: true, delayAbortEval: '30s' }],
    },
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () { valueInvestorJourney({ cacheOnly: true, phase: 'measurement', scenario: 'stress' }); }
