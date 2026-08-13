import { scenarioOptions, assertSafeTargets } from '../config.js';
import { cacheMissContract, healthCheck } from '../modules/api_client.js';

export const options = scenarioOptions({ vus: 1, iterations: 1 });
export function setup() { assertSafeTargets(); return { cold: true }; }
export default function () {
    healthCheck({ phase: 'measurement', scenario: 'cold_cache' });
    const uncachedTicker = `ZQ${String(Date.now()).slice(-8)}`;
    cacheMissContract(uncachedTicker, { phase: 'measurement', scenario: 'cold_cache' });
}
