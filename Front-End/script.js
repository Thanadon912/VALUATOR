const form = document.querySelector("#ticker-form");
const input = document.querySelector("#ticker-input");
const statusText = document.querySelector("#form-status");
const revenueMetric = document.querySelector("#metric-revenue");
const dcfMetric = document.querySelector("#metric-dcf");
const newsMetric = document.querySelector("#metric-news");

const tickerPattern = /^[A-Z][A-Z0-9.-]{0,9}$/;

form.addEventListener("submit", (event) => {
  event.preventDefault();

  const ticker = input.value.trim().toUpperCase();
  input.value = ticker;
  statusText.classList.remove("is-error");

  if (!tickerPattern.test(ticker)) {
    statusText.textContent = "Enter a valid US ticker symbol to begin.";
    statusText.classList.add("is-error");
    revenueMetric.textContent = "Ticker needed";
    dcfMetric.textContent = "Inputs needed";
    newsMetric.textContent = "Not loaded";
    return;
  }

  statusText.textContent = `${ticker} workspace is ready for data sources and DCF assumptions.`;
  revenueMetric.textContent = "Data pending";
  dcfMetric.textContent = "Add inputs";
  newsMetric.textContent = "Source needed";
});
