import { scenarioOptions } from '../config.js';
import { prepareAndVerifyCaches, smokeJourney } from '../modules/user_journey.js';

export const options = scenarioOptions({
    vus: 1,
    iterations: 1,
});

export function setup() { return prepareAndVerifyCaches(); }
export default function () { smokeJourney({ cacheOnly: true, phase: 'measurement', scenario: 'smoke' }); }
