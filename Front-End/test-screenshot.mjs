import { chromium } from "playwright";
(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  page.on('console', msg => console.log('PAGE LOG:', msg.text()));
  page.on('pageerror', error => console.log('PAGE ERROR:', error.message));
  await page.goto("http://127.0.0.1:3200/stocks/AAPL/news");
  await page.waitForTimeout(5000);
  await browser.close();
})();
