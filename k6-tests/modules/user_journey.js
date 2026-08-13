import { fail, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { assertSafeTargets } from '../config.js';
import * as api from './api_client.js';

export const tickerCases = new SharedArray('verified ticker cases', function () {
    return JSON.parse(open('../data/tickers.json'));
});

export const tickers = tickerCases.map((item) => item.symbol);

export function requestTickerDataset(ticker, options = {}) {
    return [
        api.getSummary(ticker, options),
        api.getQuote(ticker, options),
        api.getNews(ticker, options),
        api.getMethodology(ticker, options),
        api.getDCF(ticker, options),
        api.getDDM(ticker, options),
        api.getRelative(ticker, options),
        api.getAssetBased(ticker, options),
        api.getResidualIncome(ticker, options),
    ];
}

function responseFailure(ticker, response) {
    if (response.status !== 200) return `${ticker} ${response.url}: HTTP ${response.status}`;
    if (!api.contractPassed(response)) return `${ticker} ${response.url}: contract check failed`;
    return null;
}

export function prepareAndVerifyCaches() {
    assertSafeTargets();
    const failures = [];
    const allowLiveWarmup = __ENV.PERF_ALLOW_LIVE_WARMUP === 'true';

    if (allowLiveWarmup) {
        for (const ticker of tickers) {
            for (const response of requestTickerDataset(ticker, {
                phase: 'warmup',
                cacheOnly: false,
                scenario: 'bounded_live_warmup',
            })) {
                sleep(1);
            }
        }
        const snapshotWarm = api.getSnapshots(tickers, {
            phase: 'warmup',
            cacheOnly: false,
            scenario: 'bounded_live_warmup',
        });
        sleep(1);
    }

    for (const ticker of tickers) {
        for (const response of requestTickerDataset(ticker, {
            phase: 'cache_probe',
            cacheOnly: true,
            scenario: 'cache_probe',
        })) {
            const failure = responseFailure(ticker, response);
            if (failure) failures.push(failure);
        }
    }
    const snapshotProbe = api.getSnapshots(tickers, {
        phase: 'cache_probe',
        cacheOnly: true,
        scenario: 'cache_probe',
    });
    const snapshotFailure = responseFailure('snapshots', snapshotProbe);
    if (snapshotFailure) failures.push(snapshotFailure);

    if (failures.length > 0) {
        fail(`Cache precondition failed: ${failures.join('; ')}`);
    }
    return { cacheReady: true, tickers };
}

export function smokeJourney(options = {}) {
    api.healthCheck(options);
    api.invalidTickerContract(options);
    api.tooManySnapshotsContract(options);
    api.getSnapshots(tickers, options);
    requestTickerDataset(tickers[0], options);
}

export function valueInvestorJourney(options = {}) {
    api.healthCheck(options);
    const ticker = tickers[(__VU + __ITER) % tickers.length];
    api.getSummary(ticker, options);
    api.getQuote(ticker, options);
    sleep(1);
    api.getSnapshots(tickers, options);
    api.getNews(ticker, options);
    sleep(2);
    api.getMethodology(ticker, options);
    const valuationActions = [
        api.getDCF,
        api.getDDM,
        api.getRelative,
        api.getAssetBased,
        api.getResidualIncome,
    ];
    valuationActions[(__VU + __ITER) % valuationActions.length](ticker, options);
    sleep(3);
}
