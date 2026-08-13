---
name: VALUATOR
description: A premium market-expectations instrument for disciplined investors.
colors:
  workspace-black: "#010302"
  midnight-ledger: "#0B0F17"
  research-surface: "#121824"
  quiet-border: "#1E293B"
  strong-ink: "#EFFAF4"
  muted-ink: "#90B09E"
  signal-green: "#B7FF3C"
  data-emerald: "#34D399"
  data-sky: "#38BDF8"
  data-cyan: "#22D3EE"
  data-violet: "#A78BFA"
  warning-amber: "#F59E0B"
  negative-rose: "#FB7185"
typography:
  headline:
    fontFamily: "Inter, Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "18px"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  title:
    fontFamily: "Inter, Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "14px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "normal"
  body:
    fontFamily: "Inter, Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "normal"
  label:
    fontFamily: "Inter, Geist, ui-sans-serif, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 600
    lineHeight: 1.3
    letterSpacing: "0.01em"
  financial:
    fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "12px"
    fontWeight: 500
    lineHeight: 1.4
    letterSpacing: "normal"
rounded:
  sm: "4px"
  md: "8px"
  control: "10px"
  card: "12px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.signal-green}"
    textColor: "{colors.workspace-black}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 14px"
    height: "36px"
  button-ghost:
    backgroundColor: "{colors.research-surface}"
    textColor: "{colors.strong-ink}"
    typography: "{typography.label}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "36px"
  workspace-input:
    backgroundColor: "{colors.midnight-ledger}"
    textColor: "{colors.strong-ink}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "8px 12px"
    height: "38px"
  glass-card:
    backgroundColor: "{colors.research-surface}"
    textColor: "{colors.strong-ink}"
    rounded: "{rounded.card}"
    padding: "16px"
  status-chip:
    backgroundColor: "{colors.midnight-ledger}"
    textColor: "{colors.data-emerald}"
    typography: "{typography.label}"
    rounded: "{rounded.pill}"
    padding: "4px 8px"
---

# Design System: VALUATOR

## Overview

**Creative North Star: "The Analyst’s Instrument Panel"**

The interface has quiet institutional precision: compact, deliberate, and built for repeated analytical work. Like a calibrated instrument panel, every surface earns its place by clarifying company facts, provider estimates, user assumptions, or app-derived calculations.

Near-black layers establish focus while strong white type and restrained Signal Green reveal hierarchy and state. Information density is welcome when alignment, spacing, and financial typography keep it scannable. The system must never feel like a promotional SaaS landing page, a uniformly green dashboard, or a decorative sci-fi control room.

**Key Characteristics:**

- Compact and data-dense without becoming cramped.
- Source-aware, traceable, and explicit about unavailable data.
- Dark, layered, and restrained, with color reserved for meaning.
- Responsive through state changes rather than decorative choreography.

## Colors

Black-green foundations create depth; Signal Green and a small analytical spectrum communicate action, series identity, warnings, and negative outcomes.

### Primary

- **Signal Green:** Reserved for active navigation, primary actions, selected controls, positive status, and the principal chart series. Its scarcity creates authority.

### Secondary

- **Data Emerald:** Positive financial values and supporting series that must remain distinct from the primary action color.
- **Data Sky and Data Cyan:** Comparative series, informational states, and secondary analytical signals.
- **Data Violet:** Categorical chart separation where adjacent series need stronger perceptual distance; it does not communicate warning, gain, or loss.

### Tertiary

- **Warning Amber:** Missing inputs, bottlenecks, caution, and computational warnings.
- **Negative Rose:** Negative values, destructive actions, and adverse states; never use it as decoration.

### Neutral

- **Black-Green Workspace:** The outermost application background and deepest visual boundary.
- **Midnight Ledger:** The primary page canvas and recessed control surface.
- **Research Surface:** Cards, panels, menus, and grouped analytical content.
- **Quiet Border:** Thin separators and low-contrast panel outlines.
- **Strong Ink:** Headings, primary values, and high-confidence content.
- **Muted Ink:** Supporting labels, metadata, source context, and secondary explanations.

**The Signal, Not Paint Rule.** Signal Green marks action or meaning; it must never flood large panels or make the page read as uniformly green.

**The Semantic Spectrum Rule.** Sky, cyan, amber, and rose identify data or state. They are forbidden as arbitrary decoration.

## Typography

**Display Font:** Inter with Geist and system sans-serif fallbacks  
**Body Font:** Inter with Geist and system sans-serif fallbacks  
**Label/Mono Font:** Geist Mono with system monospace fallbacks

**Character:** The sans-serif voice is neutral, compact, and highly legible. Monospaced, tabular figures give prices, percentages, assumptions, and projections the stable rhythm of a financial instrument.

### Hierarchy

- **Headline** (700, 18px, 1.25): Page and major module titles; use sparingly.
- **Title** (600, 14px, 1.4): Card headings, table group names, and primary control labels.
- **Body** (400, 13px, 1.5): Explanations, state messages, and dense supporting content.
- **Label** (600, 11px, 0.01em): Metadata, compact controls, column labels, and status text.
- **Financial** (500, 12px, 1.4): Prices, ratios, projections, percentages, and machine-readable values; always use tabular numerals.

**The Scan Before Display Rule.** Financial tables prioritize aligned values and stable columns over expressive typography.

**The No Kicker Rule.** Never place tiny uppercase, widely tracked labels above headings as decorative “2023-style” kickers.

## Elevation

Elevation is a restrained hybrid of tonal layering, thin borders, and rare ambient shadow. Black-Green Workspace, Midnight Ledger, and Research Surface create the default hierarchy. Shadows clarify a raised card or overlay; semantic glows may reinforce focus or selected state but must remain subtle.

### Shadow Vocabulary

- **Research Card:** `0 1px 0 0 rgba(255,255,255,0.03) inset, 0 20px 40px -24px rgba(0,0,0,0.9)` gives a panel a fine top edge and a deep, diffuse base.
- **Focus Signal:** `0 0 0 3px rgba(28,209,115,0.18)` marks keyboard focus without replacing the component border.
- **Selected Signal:** `0 0 24px rgba(28,209,115,0.10)` is permitted only for a selected or live analytical state.

**The Layered at Rest Rule.** Surfaces use tone and one-pixel borders at rest. Strong shadows and glows appear only when hierarchy or state requires them.

## Components

Components feel compact, tactile, and source-aware. Every state must distinguish interactive controls from reported facts and must remain legible at financial-workspace density.

### Buttons

- **Shape:** Gently curved control corners (10px) with a compact 36px height.
- **Primary:** Signal Green with Black-Green text, 8px × 14px padding, and semibold label typography.
- **Hover / Focus:** Brighten slightly over 150ms; use the Focus Signal for keyboard focus and a restrained pressed translation for active state.
- **Secondary / Ghost:** Research Surface or transparent fill with a Quiet Border and Strong Ink; hover by raising tonal contrast, not by adding unrelated color.

### Chips

- **Style:** Fully rounded, compact labels with a recessed surface, thin border, and semantic text color.
- **State:** Selected chips may use a faint semantic tint. Warning, unavailable, positive, and negative chips must remain visually distinct.

### Cards / Containers

- **Corner Style:** Gently curved cards (12px) with smaller nested panels (8px).
- **Background:** Research Surface over Midnight Ledger; translucent cards may use restrained backdrop blur.
- **Shadow Strategy:** Use the Research Card shadow only on visually raised panels.
- **Border:** One-pixel Quiet Border; never use a thick colored stripe as decoration.
- **Internal Padding:** 16px by default, 12px for dense nested groups, and 24px only for major empty or explanatory states.

### Inputs / Fields

- **Style:** Midnight Ledger fill, Quiet Border, Strong Ink, 10px corners, and a compact 38px height.
- **Focus:** Shift the border to Signal Green and add the Focus Signal without moving layout.
- **Error / Disabled:** Use Negative Rose only for a validated error. Disabled fields reduce contrast; missing financial inputs use Warning Amber and an explicit message rather than a fabricated value.

### Navigation

Navigation uses compact 11–13px labels and 8px corners. Default items remain muted, hover states raise surface contrast, and the active route uses Signal Green with a restrained tinted background. Mobile navigation preserves the approved three-view structure rather than inventing extra destinations.

### Analytical Modules

Module headers pair a compact icon container with a 14px title, optional 12px subtitle, and a quiet divider. Loading, unavailable, warning, and error states preserve the module’s column geometry so values do not jump as data resolves.

**The Source-Aware Control Rule.** Provider facts, estimates, user assumptions, and derived values must never share an indistinguishable treatment.

## Do's and Don'ts

### Do:

- **Do** use Black-Green Workspace, Midnight Ledger, and Research Surface to establish depth before reaching for shadow.
- **Do** reserve Signal Green for active navigation, primary actions, chart series, status indicators, and selected controls.
- **Do** expose missing or unavailable data explicitly and use Warning Amber only when attention is required.
- **Do** align financial values with monospaced tabular numerals and keep tables scan-first.
- **Do** visually distinguish facts, provider estimates, user assumptions, and app-derived calculations.
- **Do** preserve reduced-motion final states and keep loading placeholders aligned to their eventual columns.
- **Do** keep every stock-analysis view scoped to the currently selected company.

### Don't:

- **Don't** use generic plain red, blue, or green, or create uniformly green pages.
- **Don't** add decorative orbs, bokeh, large gradients, floating shapes, or nested decorative cards.
- **Don't** add Related Tickers, Chart, Conversations, Historical Data, Analysis, or Options pages.
- **Don't** present placeholder values as real values or hide unavailable required inputs.
- **Don't** use tiny uppercase, widely tracked kickers above headings.
- **Don't** add color without a semantic role, or use Negative Rose and Warning Amber as decoration.
- **Don't** use oversized display typography that weakens compact financial scanning.
