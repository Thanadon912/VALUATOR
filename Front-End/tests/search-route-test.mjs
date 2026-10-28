import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

async function runTests() {
  console.log("--- Running Search Route Tests ---");

  let fetchCalls = [];
  const originalFetch = globalThis.fetch;
  const originalEnvKey = process.env.GEMINI_API_KEY;

  // Hermetic mock: intercept all network calls
  globalThis.fetch = async (url) => {
    const urlStr = String(url);
    fetchCalls.push(urlStr);

    // Mock Gemini API call (ensure NO external network traffic to Google)
    if (urlStr.includes("generativelanguage.googleapis.com")) {
      return new Response(
        JSON.stringify({
          candidates: [
            {
              content: { parts: [{ text: "MOCK_AI_SYMBOL" }] },
              finishReason: "STOP",
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }

    // Mock backend /validate endpoint
    if (
      urlStr.includes("/api/stocks/AAPL/validate") ||
      urlStr.includes("/api/stocks/META/validate") ||
      urlStr.includes("/api/stocks/COKE/validate") ||
      urlStr.includes("/api/stocks/F/validate")
    ) {
      return new Response(JSON.stringify({ valid: true }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    if (
      urlStr.includes("/api/stocks/FORD/validate") ||
      urlStr.includes("/api/stocks/XYZW/validate")
    ) {
      return new Response(JSON.stringify({ valid: false }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }

    return new Response(JSON.stringify({ valid: false }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  };

  try {
    const routeMod = require("../.next/server/app/api/search/route.js");
    const GET = routeMod.routeModule.userland.GET;

    // Test 1: Direct cached ticker ("meta") -> 0 fetch calls (<1ms)
    fetchCalls = [];
    const res1 = await GET(new Request("http://localhost:3000/api/search?q=meta"));
    assert.equal(res1.status, 200);
    const data1 = await res1.json();
    assert.equal(data1.symbol, "META");
    assert.equal(fetchCalls.length, 0, "Cached 'meta' must make ZERO fetch calls");
    console.log("✓ Test 1 Passed: 'meta' resolved instantly from In-Memory Cache (0 fetch calls)");

    // Test 2: Spaced letters "m e t a" -> 0 fetch calls
    fetchCalls = [];
    const res2 = await GET(new Request("http://localhost:3000/api/search?q=m%20e%20t%20a"));
    assert.equal(res2.status, 200);
    const data2 = await res2.json();
    assert.equal(data2.symbol, "META");
    assert.equal(fetchCalls.length, 0, "Spaced 'm e t a' must strip spaces and hit memory cache with 0 fetch calls");
    console.log("✓ Test 2 Passed: 'm e t a' stripped spaces and resolved from In-Memory Cache (0 fetch calls)");

    // Test 3: Common alias "facebook" -> 0 fetch calls
    fetchCalls = [];
    const res3 = await GET(new Request("http://localhost:3000/api/search?q=facebook"));
    assert.equal(res3.status, 200);
    const data3 = await res3.json();
    assert.equal(data3.symbol, "META");
    assert.equal(fetchCalls.length, 0, "Alias 'facebook' must make ZERO fetch calls");
    console.log("✓ Test 3 Passed: 'facebook' resolved to META from In-Memory Aliases (0 fetch calls)");

    // Test 4: Ticker collision handling: "coke" must resolve to "COKE" (Coca-Cola Consolidated), NOT "KO"!
    fetchCalls = [];
    const res4 = await GET(new Request("http://localhost:3000/api/search?q=coke"));
    assert.equal(res4.status, 200);
    const data4 = await res4.json();
    assert.equal(data4.symbol, "COKE", "Ticker 'coke' must resolve to COKE, not KO");
    console.log("✓ Test 4 Passed: 'coke' resolved to COKE (Coca-Cola Consolidated, NOT overridden to KO)");

    // Test 5: Company name "coca cola" -> resolves to "KO"
    fetchCalls = [];
    const res5 = await GET(new Request("http://localhost:3000/api/search?q=coca%20cola"));
    assert.equal(res5.status, 200);
    const data5 = await res5.json();
    assert.equal(data5.symbol, "KO");
    assert.equal(fetchCalls.length, 0, "Pre-populated alias 'coca cola' must resolve in 0 fetch calls");
    console.log("✓ Test 5 Passed: 'coca cola' resolved to KO from In-Memory Aliases (0 fetch calls)");

    // Test 6: Candidate <= 5 chars that is NOT a valid ticker ("ford") checks /validate, sees false, falls back to alias "F"
    fetchCalls = [];
    const res6 = await GET(new Request("http://localhost:3000/api/search?q=ford"));
    assert.equal(res6.status, 200);
    const data6 = await res6.json();
    assert.equal(data6.symbol, "F");
    const fordValidateCalls = fetchCalls.filter((url) => url.includes("/api/stocks/FORD/validate"));
    assert.equal(fordValidateCalls.length, 1, "'ford' should check /validate once to verify if FORD ticker exists");
    console.log("✓ Test 6 Passed: 'ford' verified not a ticker via /validate, then cleanly resolved to 'F'");

    // Test 7: Long company name (>5 chars e.g. "UnknownLongCompany")
    // MUST NOT waste an HTTP call to /validate before routing to AI!
    fetchCalls = [];
    await GET(new Request("http://localhost:3000/api/search?q=UnknownLongCompany"));
    const validateCalls = fetchCalls.filter((url) => url.includes("/validate"));
    assert.equal(validateCalls.length, 0, "Long company names (>5 chars) must NEVER call /validate");
    console.log("✓ Test 7 Passed: Long company names (>5 chars) bypass /validate check (0 wasted validate calls)");

    // Test 8: Empty query validation
    const res8 = await GET(new Request("http://localhost:3000/api/search?q="));
    assert.equal(res8.status, 400);
    console.log("✓ Test 8 Passed: Empty query correctly rejected with 400 Bad Request");

    // Test 9: Company name "spacex" -> resolves to "SPCX" in 0 fetch calls (<1ms)
    fetchCalls = [];
    const res9 = await GET(new Request("http://localhost:3000/api/search?q=SPACEX"));
    assert.equal(res9.status, 200);
    const data9 = await res9.json();
    assert.equal(data9.symbol, "SPCX");
    assert.equal(fetchCalls.length, 0, "Pre-populated alias 'spacex' must resolve to SPCX with 0 fetch calls");
    console.log("✓ Test 9 Passed: 'SPACEX' resolved to SPCX from In-Memory Aliases (0 fetch calls)");

    console.log("\n>>> ALL 9 SEARCH ROUTE TESTS PASSED SUCCESSFULLY! <<<\n");
  } finally {
    globalThis.fetch = originalFetch;
    if (originalEnvKey !== undefined) {
      process.env.GEMINI_API_KEY = originalEnvKey;
    }
  }
}

runTests().catch((err) => {
  console.error("Test failed:", err);
  process.exit(1);
});
