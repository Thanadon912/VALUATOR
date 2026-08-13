import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

type MobileIssue = {
  kind: string;
  target: string;
  detail: string;
};

function issueSummary(issues: MobileIssue[]): string {
  return issues
    .map((issue) => `${issue.kind}: ${issue.target} — ${issue.detail}`)
    .join("\n");
}

export async function expectMobileIntegrity(page: Page): Promise<void> {
  await expect(page.locator("body")).toBeVisible();
  await page.evaluate(() => document.fonts.ready);

  const audit = await page.evaluate(() => {
    const viewportWidth = document.documentElement.clientWidth;
    const issues: MobileIssue[] = [];
    const selector = [
      "a[href]",
      "button",
      "input:not([type='hidden'])",
      "select",
      "textarea",
      "summary",
      "[role='button']",
      "[role='link']",
      "[role='tab']",
      "[role='checkbox']",
      "[role='switch']",
      "[role='combobox']",
    ].join(",");

    function targetFor(element: Element): string {
      const htmlElement = element as HTMLElement;
      const label = element.getAttribute("aria-label")
        || element.getAttribute("name")
        || htmlElement.innerText
        || element.getAttribute("placeholder")
        || element.tagName.toLowerCase();
      return label.trim().replace(/\s+/g, " ").slice(0, 90);
    }

    function hasHorizontalScrollAncestor(element: Element): boolean {
      let parent = element.parentElement;
      while (parent && parent !== document.body) {
        const style = window.getComputedStyle(parent);
        if (
          ["auto", "scroll"].includes(style.overflowX)
          && parent.scrollWidth > parent.clientWidth + 1
        ) {
          return true;
        }
        parent = parent.parentElement;
      }
      return false;
    }

    if (document.documentElement.scrollWidth > viewportWidth + 1) {
      issues.push({
        kind: "page-overflow",
        target: "document",
        detail: `${document.documentElement.scrollWidth}px content in ${viewportWidth}px viewport`,
      });
    }

    for (const element of document.querySelectorAll(selector)) {
      const htmlElement = element as HTMLElement;
      const style = window.getComputedStyle(htmlElement);
      const ownRect = htmlElement.getBoundingClientRect();
      const labelledControl = element.matches('input[type="checkbox"], input[type="radio"]')
        ? element.closest("label")
        : null;
      const rect = labelledControl?.getBoundingClientRect() ?? ownRect;
      if (
        style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity) === 0
        || rect.width === 0
        || rect.height === 0
      ) {
        continue;
      }
      if (
        !hasHorizontalScrollAncestor(element)
        && (rect.left < -1 || rect.right > viewportWidth + 1)
      ) {
        issues.push({
          kind: "offscreen-control",
          target: targetFor(element),
          detail: `horizontal bounds ${rect.left.toFixed(1)}..${rect.right.toFixed(1)} in ${viewportWidth}px viewport`,
        });
      }
    }

    for (const element of document.querySelectorAll([
      "input:not([type='hidden']):not([type='button']):not([type='checkbox']):not([type='color']):not([type='file']):not([type='radio']):not([type='range']):not([type='reset']):not([type='submit'])",
      "select",
      "textarea",
    ].join(","))) {
      const htmlElement = element as HTMLElement;
      const style = window.getComputedStyle(htmlElement);
      const rect = htmlElement.getBoundingClientRect();
      if (style.display === "none" || style.visibility === "hidden" || rect.width === 0 || rect.height === 0) {
        continue;
      }
      const fontSize = Number.parseFloat(style.fontSize);
      if (fontSize < 16) {
        issues.push({
          kind: "ios-input-zoom",
          target: targetFor(element),
          detail: `${fontSize}px input text; mobile form controls require at least 16px`,
        });
      }
    }

    return issues;
  });

  expect(audit, issueSummary(audit)).toEqual([]);
}

export async function expectPrimaryTouchTargets(page: Page): Promise<void> {
  const issues = await page.evaluate(() => {
    const results: MobileIssue[] = [];
    const selector = [
      "button",
      "input:not([type='hidden'])",
      "select",
      "summary",
      "nav a[href]",
      "[role='tab']",
    ].join(",");
    for (const element of document.querySelectorAll(selector)) {
      const htmlElement = element as HTMLElement;
      const style = window.getComputedStyle(htmlElement);
      const ownRect = htmlElement.getBoundingClientRect();
      const labelledControl = element.matches('input[type="checkbox"], input[type="radio"]')
        ? element.closest("label")
        : null;
      const rect = labelledControl?.getBoundingClientRect() ?? ownRect;
      if (
        style.display === "none"
        || style.visibility === "hidden"
        || Number(style.opacity) === 0
        || rect.width === 0
        || rect.height === 0
        || (element as HTMLButtonElement).disabled
      ) {
        continue;
      }
      if (rect.width < 44 || rect.height < 44) {
        const label = element.getAttribute("aria-label")
          || htmlElement.innerText
          || element.getAttribute("placeholder")
          || element.tagName.toLowerCase();
        results.push({
          kind: "touch-target",
          target: label.trim().replace(/\s+/g, " ").slice(0, 90),
          detail: `${rect.width.toFixed(1)}×${rect.height.toFixed(1)}px`,
        });
      }
    }
    return results;
  });

  expect(issues, issueSummary(issues)).toEqual([]);
}

export async function expectWcag22AA(page: Page): Promise<void> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();
  const violations = results.violations.map((violation) => ({
    id: violation.id,
    impact: violation.impact,
    help: violation.help,
    nodes: violation.nodes.map((node) => ({
      target: node.target.join(" "),
      html: node.html,
      failureSummary: node.failureSummary,
    })),
  }));

  expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
}
