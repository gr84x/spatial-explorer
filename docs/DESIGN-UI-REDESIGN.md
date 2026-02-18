# UI Redesign Design Document

**Task ID:** T-1565  
**Project:** Spatial Explorer — V1.0 Core (PRJ-057)  
**Category:** Design  
**Author:** Systems Architect  
**Date:** 2026-02-18  
**Status:** Draft

---

## Table of Contents

1. [Problem Statement](#problem-statement)
2. [Requirements](#requirements)
3. [Current State Analysis](#current-state-analysis)
4. [Options Considered](#options-considered)
5. [Tradeoff Analysis](#tradeoff-analysis)
6. [Recommendation](#recommendation)
7. [Design Specification](#design-specification)
8. [Component Specifications](#component-specifications)
9. [Animation & Micro-interactions](#animation--micro-interactions)
10. [Typography System](#typography-system)
11. [Responsive Breakpoints](#responsive-breakpoints)
12. [Implementation Roadmap](#implementation-roadmap)
13. [Open Questions & Risks](#open-questions--risks)

---

## Problem Statement

Spatial Explorer currently has a functional but utilitarian UI built with inline CSS in a monolithic HTML file. While the existing interface works, it lacks:

- **Mobile-first design**: Current breakpoints are retrofitted, not designed mobile-first
- **Visual polish**: The UI feels like a prototype rather than a professional tool
- **Purposeful animations**: No micro-interactions to communicate state changes
- **Consistent typography**: Font sizing and spacing are ad-hoc
- **Modern workflows**: Standard patterns like command palettes, keyboard shortcuts, and progressive disclosure are missing

The goal is to transform Spatial Explorer into a **polished, professional scientific visualization tool** that researchers would be proud to use and share in publications.

---

## Requirements

### Must-Have (P0)

| ID | Requirement | Rationale |
|----|-------------|-----------|
| R1 | Mobile-first responsive design | Primary use case includes tablet/laptop on lab bench |
| R2 | Touch-friendly controls (44px minimum tap targets) | Scientific users often work on tablets |
| R3 | Professional dark theme with subtle depth | Reduce eye strain during extended analysis |
| R4 | Consistent typography scale | Improve readability and visual hierarchy |
| R5 | Meaningful loading states | Datasets can take 1-3 seconds to parse |
| R6 | Smooth panel transitions | 200-300ms animations for panel open/close |
| R7 | Accessibility (WCAG 2.1 AA) | Institutional accessibility requirements |
| R8 | Export-quality visuals | Scientists share screenshots in presentations |
| R9 | Clear visual hierarchy | Legend, controls, and canvas have distinct roles |
| R10 | Keyboard navigation for power users | Speed up repetitive workflows |

### Nice-to-Have (P1)

| ID | Requirement | Rationale |
|----|-------------|-----------|
| R11 | Command palette (Cmd/Ctrl+K) | Quick access to all actions |
| R12 | Collapsible sidebar panels | Maximize canvas real estate |
| R13 | Customizable color themes | User preference |
| R14 | Onboarding tour for first-time users | Reduce learning curve |
| R15 | Gesture-based zoom on mobile | Natural mobile interaction |
| R16 | Floating toolbar overlay | Context-sensitive controls |

### Out of Scope

- Backend/API changes (purely frontend)
- Data processing performance (separate optimization task)
- New analysis features (phenotype clustering, etc.)
- Branding/logo changes

---

## Current State Analysis

### Existing UI Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Header (title + dataset badge)                                 │
├─────────────────────────────────────┬───────────────────────────┤
│                                     │  Cell Types Card          │
│                                     ├───────────────────────────┤
│  Visualization Canvas (65%)         │  Phenotype Gate Card      │
│  - Toolbar row at top               ├───────────────────────────┤
│  - Gene search input                │  Selected Cell Card       │
│  - Export controls                  ├───────────────────────────┤
│                                     │  How to Use Card          │
└─────────────────────────────────────┴───────────────────────────┘
```

### Current Strengths
- ✅ Clean dark color palette with good contrast
- ✅ Logical card-based sidebar layout
- ✅ Functional glassmorphism (blur + transparency)
- ✅ Decent responsive breakpoints exist
- ✅ URL state persistence works well

### Current Weaknesses
- ❌ All CSS is inline (~400 lines in `<style>` block)
- ❌ No CSS custom property system beyond basic colors
- ❌ Breakpoints are desktop-first (mobile is afterthought)
- ❌ Zero animations/transitions on state changes
- ❌ Typography is generic system fonts with inconsistent sizing
- ❌ Controls are too small for touch (some buttons ~32px)
- ❌ No loading states (parse happens synchronously)
- ❌ Sidebar is always visible (wastes mobile space)
- ❌ Gene input is cramped on mobile
- ❌ No keyboard shortcuts documented or implemented

### Technical Debt
- Inline styles make theming/maintenance difficult
- No CSS architecture (BEM, utility classes, etc.)
- Event listeners inline with UI logic
- No component abstraction

---

## Options Considered

### Option A: CSS Refactor Only (Minimal)

**Approach**: Extract inline CSS to external stylesheet, add animations, improve responsive behavior. Keep HTML structure intact.

**Changes:**
- Move CSS to `styles.css`
- Add CSS variables for spacing/typography
- Add transition properties to interactive elements
- Adjust breakpoints for mobile-first
- Increase touch target sizes

**Scope**: ~2-3 days engineering effort

---

### Option B: Layout Restructure (Medium)

**Approach**: Redesign layout with collapsible sidebar, floating toolbar, and mobile-optimized gene search. Refactor CSS to external file with utility classes.

**Changes:**
- New layout: sidebar collapses to icon-only rail on mobile
- Floating toolbar over canvas (pan/zoom/export)
- Command palette for quick actions
- New typography scale (modular scale)
- Subtle animations on all interactive elements
- Loading skeleton states

**Scope**: ~5-7 days engineering effort

---

### Option C: Component-Based Rewrite (Major)

**Approach**: Full rewrite using web components or a minimal framework (Lit, Preact). CSS modules or scoped styles. Modern build pipeline.

**Changes:**
- Introduce build step (Vite/esbuild)
- Web components for each UI section
- CSS-in-JS or CSS modules
- Full animation library integration
- Design tokens system

**Scope**: ~10-15 days engineering effort

---

### Option D: Hybrid Evolution (Recommended)

**Approach**: Progressive enhancement without introducing build dependencies. External CSS with BEM-like conventions, vanilla JS component patterns, CSS-only animations.

**Changes:**
- External `styles/` directory with organized CSS
- Mobile-first breakpoints
- CSS custom properties for design tokens
- JS module for animation orchestration
- Collapsible panels with smooth transitions
- Touch-optimized controls
- Loading states via CSS

**Scope**: ~5-8 days engineering effort

---

## Tradeoff Analysis

| Criterion | Option A (Minimal) | Option B (Medium) | Option C (Major) | Option D (Hybrid) |
|-----------|-------------------|-------------------|------------------|-------------------|
| **Mobile UX** | ⚠️ Improved | ✅ Good | ✅ Excellent | ✅ Good |
| **Animation Quality** | ⚠️ Basic | ✅ Smooth | ✅ Excellent | ✅ Smooth |
| **Maintainability** | ⚠️ Moderate | ✅ Good | ✅ Excellent | ✅ Good |
| **Build Complexity** | ✅ None | ✅ None | ❌ Required | ✅ None |
| **Effort** | ✅ Low (2-3d) | ⚠️ Med (5-7d) | ❌ High (10-15d) | ⚠️ Med (5-8d) |
| **Risk** | ✅ Low | ⚠️ Medium | ❌ High | ⚠️ Medium |
| **Matches Goals** | ❌ Partial | ✅ Full | ✅ Full | ✅ Full |
| **Future Proof** | ⚠️ Moderate | ✅ Good | ✅ Excellent | ✅ Good |

### Risk Assessment

| Option | Key Risks | Mitigation |
|--------|-----------|------------|
| A | UI still feels dated after work | - |
| B | Mobile layout complexity | Incremental testing on real devices |
| C | Build system maintenance burden | - |
| D | Scope creep during implementation | Clear specification, timeboxing |

---

## Recommendation

**Recommended: Option D (Hybrid Evolution)**

### Justification

1. **Matches all requirements** without introducing build dependencies
2. **Preserves zero-build philosophy** that makes the project accessible
3. **Progressive enhancement** allows shipping incremental improvements
4. **CSS custom properties** provide theming foundation for future
5. **Reasonable effort** for the quality improvement gained

### Rejected Alternatives

- **Option A**: Doesn't achieve the "professional feel" goal; lipstick on a pig
- **Option B**: Similar to D but doesn't establish design token system
- **Option C**: Build dependency is unnecessary for this project's complexity and harms the "open index.html and go" developer experience

---

## Design Specification

### Color System

```css
:root {
  /* Background layers (darkest to lightest) */
  --bg-base: #09090b;           /* zinc-950 */
  --bg-surface: #0e0f11;        /* Elevated panels */
  --bg-overlay: rgba(14,15,17,0.88);  /* Modal/dropdown backdrop */
  
  /* Interactive surfaces */
  --surface-primary: rgba(24,24,27,0.72);   /* Cards, inputs */
  --surface-secondary: rgba(39,39,42,0.55); /* Hover states */
  --surface-tertiary: rgba(63,63,70,0.40);  /* Active states */
  
  /* Borders */
  --border-subtle: rgba(255,255,255,0.06);
  --border-default: rgba(255,255,255,0.10);
  --border-emphasis: rgba(255,255,255,0.18);
  
  /* Text */
  --text-primary: rgba(255,255,255,0.95);
  --text-secondary: rgba(255,255,255,0.72);
  --text-muted: rgba(255,255,255,0.50);
  --text-disabled: rgba(255,255,255,0.32);
  
  /* Accent palette */
  --accent-blue: #3b82f6;       /* Primary actions */
  --accent-blue-muted: #60a5fa; /* Links, highlights */
  --accent-green: #22c55e;      /* Success, high expression */
  --accent-amber: #f59e0b;      /* Warnings, gate matches */
  --accent-red: #ef4444;        /* Errors, destructive */
  
  /* Gradients */
  --gradient-glow-blue: radial-gradient(
    ellipse 800px 500px at 30% -5%,
    rgba(59,130,246,0.12),
    transparent 60%
  );
  --gradient-glow-green: radial-gradient(
    ellipse 600px 400px at 85% 5%,
    rgba(34,197,94,0.06),
    transparent 55%
  );
}
```

### Spacing Scale

Using an 8px base with multipliers:

```css
:root {
  --space-1: 4px;   /* Tight inline gaps */
  --space-2: 8px;   /* Default gap */
  --space-3: 12px;  /* Component padding */
  --space-4: 16px;  /* Card padding */
  --space-5: 24px;  /* Section spacing */
  --space-6: 32px;  /* Large gaps */
  --space-8: 48px;  /* Layout sections */
}
```

### Border Radius

```css
:root {
  --radius-sm: 6px;   /* Small buttons, badges */
  --radius-md: 10px;  /* Inputs, buttons */
  --radius-lg: 14px;  /* Cards, panels */
  --radius-xl: 20px;  /* Modals, large cards */
  --radius-full: 9999px; /* Pills, avatars */
}
```

### Shadow System

```css
:root {
  --shadow-sm: 0 1px 2px rgba(0,0,0,0.25);
  --shadow-md: 0 4px 12px rgba(0,0,0,0.35);
  --shadow-lg: 0 8px 24px rgba(0,0,0,0.45);
  --shadow-xl: 0 16px 48px rgba(0,0,0,0.55);
  
  /* Glow effects */
  --glow-blue: 0 0 20px rgba(59,130,246,0.25);
  --glow-green: 0 0 16px rgba(34,197,94,0.20);
}
```

---

## Component Specifications

### 1. Application Shell

```
┌─────────────────────────────────────────────────────────────────┐
│  ┌─ Header ─────────────────────────────────────────────────┐  │
│  │ [Logo] Spatial Explorer    [dataset.csv ▼]    [⌘K] [☰]  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                 │
│  ┌─ Canvas ────────────────────────┐ ┌─ Sidebar ────────────┐  │
│  │                                 │ │ ▾ Cell Types         │  │
│  │     [Visualization Area]       │ │   Legend rows...     │  │
│  │                                 │ ├──────────────────────┤  │
│  │ ┌─ Floating Toolbar ──────────┐│ │ ▾ Phenotype Gate     │  │
│  │ │ [+] [-] [⊙] [↺]   [Gene▼]  ││ │   Gate builder...    │  │
│  │ └─────────────────────────────┘│ ├──────────────────────┤  │
│  │                                 │ │ ▾ Selection          │  │
│  │        [Scale Bar]              │ │   Cell details...    │  │
│  └─────────────────────────────────┘ └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Header Bar

**Desktop (>768px)**:
- Height: 56px
- Logo + title (left)
- Dataset dropdown (center)
- Command palette trigger + hamburger (right)

**Mobile (<768px)**:
- Height: 48px  
- Hamburger (left), Logo (center), Search (right)
- Dataset selector in drawer

```css
.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 56px;
  padding: 0 var(--space-4);
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border-subtle);
  position: sticky;
  top: 0;
  z-index: 100;
}

@media (max-width: 768px) {
  .header {
    height: 48px;
    padding: 0 var(--space-3);
  }
}
```

### 3. Floating Toolbar

Positioned over the canvas (bottom-center on desktop, bottom-left on mobile).

**Contents**:
- Zoom in/out buttons
- Reset view button
- Gene search input (expandable)
- Export dropdown

```css
.floating-toolbar {
  position: absolute;
  bottom: var(--space-4);
  left: 50%;
  transform: translateX(-50%);
  
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  
  background: var(--surface-primary);
  backdrop-filter: blur(12px);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-lg);
}

@media (max-width: 768px) {
  .floating-toolbar {
    left: var(--space-3);
    right: var(--space-3);
    transform: none;
    justify-content: space-between;
  }
}
```

### 4. Sidebar Panel

**Desktop**: Fixed width (340px), scrollable  
**Tablet**: Collapsible icon rail (56px) → expanded (340px)  
**Mobile**: Drawer overlay (slides from right)

```css
.sidebar {
  width: 340px;
  min-width: 340px;
  height: 100%;
  overflow-y: auto;
  padding: var(--space-4);
  background: var(--bg-surface);
  border-left: 1px solid var(--border-subtle);
  
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
}

@media (max-width: 1024px) {
  .sidebar {
    position: fixed;
    right: 0;
    top: 56px;
    bottom: 0;
    z-index: 90;
    transform: translateX(100%);
    transition: transform 280ms cubic-bezier(0.4, 0, 0.2, 1);
  }
  
  .sidebar.is-open {
    transform: translateX(0);
  }
}
```

### 5. Collapsible Card

```html
<section class="card" data-expanded="true">
  <button class="card__header" aria-expanded="true">
    <span class="card__title">Cell Types</span>
    <span class="card__count">7</span>
    <svg class="card__chevron">...</svg>
  </button>
  <div class="card__body">
    <!-- Content -->
  </div>
</section>
```

```css
.card {
  background: var(--surface-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.card__header {
  display: flex;
  align-items: center;
  width: 100%;
  padding: var(--space-3) var(--space-4);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: background 150ms ease;
}

.card__header:hover {
  background: var(--surface-secondary);
}

.card__body {
  padding: 0 var(--space-4) var(--space-4);
  overflow: hidden;
  transition: max-height 250ms cubic-bezier(0.4, 0, 0.2, 1),
              padding 250ms ease,
              opacity 200ms ease;
}

.card[data-expanded="false"] .card__body {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}

.card__chevron {
  transition: transform 250ms cubic-bezier(0.4, 0, 0.2, 1);
}

.card[data-expanded="false"] .card__chevron {
  transform: rotate(-90deg);
}
```

### 6. Legend Row

```html
<label class="legend-row">
  <input type="checkbox" class="legend-row__checkbox" checked />
  <span class="legend-row__swatch" style="--swatch-color: #f472b6"></span>
  <span class="legend-row__name">Tumor</span>
  <span class="legend-row__count">2,431 / 2,431</span>
</label>
```

```css
.legend-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background 120ms ease;
  
  /* Touch target */
  min-height: 44px;
}

.legend-row:hover {
  background: var(--surface-secondary);
}

.legend-row__swatch {
  width: 12px;
  height: 12px;
  border-radius: 3px;
  background: var(--swatch-color);
  box-shadow: 0 0 0 3px rgba(255,255,255,0.06);
}

.legend-row__name {
  flex: 1;
  font-size: 0.875rem;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.legend-row__count {
  font-size: 0.75rem;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}
```

### 7. Input Field

```css
.input {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  
  background: rgba(0,0,0,0.25);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  
  transition: border-color 150ms ease,
              box-shadow 150ms ease;
  
  /* Touch target */
  min-height: 44px;
}

.input:focus-within {
  border-color: var(--accent-blue);
  box-shadow: 0 0 0 3px rgba(59,130,246,0.15);
}

.input__field {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 0.9375rem;
}

.input__field::placeholder {
  color: var(--text-muted);
}
```

### 8. Button Variants

```css
/* Base button */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: var(--space-2);
  
  padding: var(--space-2) var(--space-3);
  min-height: 44px;
  min-width: 44px;
  
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-primary);
  
  background: var(--surface-primary);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  cursor: pointer;
  
  transition: background 120ms ease,
              border-color 120ms ease,
              transform 80ms ease;
}

.btn:hover {
  background: var(--surface-secondary);
  border-color: var(--border-emphasis);
}

.btn:active {
  transform: scale(0.97);
}

/* Primary variant */
.btn--primary {
  background: var(--accent-blue);
  border-color: var(--accent-blue);
  color: white;
}

.btn--primary:hover {
  background: #2563eb; /* blue-600 */
}

/* Icon-only */
.btn--icon {
  padding: 0;
  width: 44px;
  height: 44px;
}
```

### 9. Tooltip

```css
.tooltip {
  position: absolute;
  z-index: 1000;
  padding: var(--space-2) var(--space-3);
  max-width: 280px;
  
  background: var(--bg-overlay);
  backdrop-filter: blur(8px);
  border: 1px solid var(--border-default);
  border-radius: var(--radius-md);
  box-shadow: var(--shadow-md);
  
  font-size: 0.8125rem;
  color: var(--text-primary);
  line-height: 1.4;
  
  pointer-events: none;
  opacity: 0;
  transform: translateY(4px);
  transition: opacity 150ms ease,
              transform 150ms ease;
}

.tooltip.is-visible {
  opacity: 1;
  transform: translateY(0);
}
```

### 10. Loading Skeleton

```css
.skeleton {
  background: linear-gradient(
    90deg,
    var(--surface-primary) 0%,
    var(--surface-secondary) 50%,
    var(--surface-primary) 100%
  );
  background-size: 200% 100%;
  animation: skeleton-shimmer 1.5s ease-in-out infinite;
  border-radius: var(--radius-sm);
}

@keyframes skeleton-shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}
```

---

## Animation & Micro-interactions

### Animation Tokens

```css
:root {
  /* Durations */
  --duration-fast: 120ms;
  --duration-normal: 200ms;
  --duration-slow: 300ms;
  --duration-slower: 400ms;
  
  /* Easings */
  --ease-out: cubic-bezier(0.0, 0.0, 0.2, 1);     /* Decelerate */
  --ease-in-out: cubic-bezier(0.4, 0.0, 0.2, 1); /* Standard */
  --ease-bounce: cubic-bezier(0.34, 1.56, 0.64, 1); /* Playful */
}
```

### State Transition Map

| Element | Trigger | Property | Duration | Easing |
|---------|---------|----------|----------|--------|
| Button | hover | background, border | 120ms | ease |
| Button | active | transform (scale) | 80ms | ease |
| Card | expand/collapse | max-height, opacity | 250ms | ease-in-out |
| Sidebar | open/close | transform | 280ms | ease-in-out |
| Tooltip | show/hide | opacity, transform | 150ms | ease |
| Input | focus | border, shadow | 150ms | ease |
| Legend row | check/uncheck | opacity | 200ms | ease |
| Canvas overlay | loading | opacity | 300ms | ease |
| Floating toolbar | appear | opacity, transform | 200ms | ease-out |

### Key Animations

**Panel Slide-In:**
```css
@keyframes slide-in-right {
  from {
    transform: translateX(100%);
    opacity: 0;
  }
  to {
    transform: translateX(0);
    opacity: 1;
  }
}
```

**Fade-Scale In (for modals/tooltips):**
```css
@keyframes fade-scale-in {
  from {
    opacity: 0;
    transform: scale(0.95);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
```

**Loading Pulse (for skeleton):**
```css
@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}
```

### Reduced Motion Support

```css
@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## Typography System

### Font Stack

```css
:root {
  --font-sans: "Inter", system-ui, -apple-system, BlinkMacSystemFont, 
               "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, SFMono-Regular, 
               "SF Mono", Menlo, Consolas, monospace;
}
```

**Web Font Loading (optional, graceful fallback):**
```html
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" 
      rel="stylesheet" />
```

### Type Scale (1.2 ratio - Minor Third)

| Name | Size | Line Height | Weight | Use Case |
|------|------|-------------|--------|----------|
| `text-xs` | 0.75rem (12px) | 1.5 | 400 | Captions, metadata |
| `text-sm` | 0.875rem (14px) | 1.5 | 400 | Body text, inputs |
| `text-base` | 1rem (16px) | 1.5 | 400 | Default body |
| `text-lg` | 1.125rem (18px) | 1.4 | 500 | Emphasized body |
| `text-xl` | 1.25rem (20px) | 1.3 | 600 | Card titles |
| `text-2xl` | 1.5rem (24px) | 1.25 | 600 | Page title |

```css
.text-xs { font-size: 0.75rem; line-height: 1.5; }
.text-sm { font-size: 0.875rem; line-height: 1.5; }
.text-base { font-size: 1rem; line-height: 1.5; }
.text-lg { font-size: 1.125rem; line-height: 1.4; font-weight: 500; }
.text-xl { font-size: 1.25rem; line-height: 1.3; font-weight: 600; }
.text-2xl { font-size: 1.5rem; line-height: 1.25; font-weight: 600; }
```

### Typography Utilities

```css
.font-medium { font-weight: 500; }
.font-semibold { font-weight: 600; }
.tabular-nums { font-variant-numeric: tabular-nums; }
.truncate {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
```

---

## Responsive Breakpoints

### Mobile-First Breakpoint Strategy

| Name | Min-Width | Target Devices |
|------|-----------|----------------|
| `sm` | 640px | Large phones (landscape) |
| `md` | 768px | Tablets (portrait) |
| `lg` | 1024px | Tablets (landscape), small laptops |
| `xl` | 1280px | Laptops, small desktops |
| `2xl` | 1536px | Large desktops |

```css
/* Mobile-first: base styles are for smallest screens */

/* Small (640px+) */
@media (min-width: 640px) { }

/* Medium (768px+) */
@media (min-width: 768px) { }

/* Large (1024px+) */
@media (min-width: 1024px) { }

/* XL (1280px+) */
@media (min-width: 1280px) { }
```

### Layout Behavior by Breakpoint

| Breakpoint | Canvas | Sidebar | Toolbar |
|------------|--------|---------|---------|
| Base (<640) | Full width | Drawer (off-screen) | Bottom (compact) |
| sm (640-767) | Full width | Drawer (off-screen) | Bottom (compact) |
| md (768-1023) | Full width | Drawer (off-screen) | Bottom (full) |
| lg (1024-1279) | Flex: 1 | Fixed 340px | Floating (canvas) |
| xl (1280+) | Flex: 1 | Fixed 380px | Floating (canvas) |

---

## Implementation Roadmap

### Phase 1: Foundation (Day 1-2)

1. **Extract CSS to external files**
   - `styles/tokens.css` — Design tokens (colors, spacing, etc.)
   - `styles/base.css` — Reset, typography, utilities
   - `styles/components.css` — Component styles
   - `styles/layout.css` — Layout grid, responsive rules

2. **Update HTML structure**
   - Add semantic landmarks (`<header>`, `<main>`, `<aside>`)
   - Add ARIA attributes for accessibility
   - Add data attributes for JS interaction

3. **Implement design tokens**
   - CSS custom properties for all colors/spacing
   - Typography scale classes

### Phase 2: Layout & Responsiveness (Day 3-4)

1. **Mobile-first layout rewrite**
   - Base styles for mobile
   - Progressive enhancement breakpoints

2. **Collapsible sidebar**
   - Off-canvas drawer for mobile/tablet
   - Toggle button in header
   - Overlay backdrop

3. **Floating toolbar**
   - Position over canvas
   - Responsive behavior

### Phase 3: Animations & Polish (Day 5-6)

1. **Add transitions**
   - Button hover/active states
   - Card expand/collapse
   - Sidebar open/close
   - Tooltip fade

2. **Loading states**
   - Skeleton loading for file parse
   - Canvas loading overlay

3. **Touch optimization**
   - 44px minimum touch targets
   - Touch-friendly scrolling

### Phase 4: Finishing & Testing (Day 7-8)

1. **Keyboard navigation**
   - Tab order
   - Focus indicators
   - Escape to close panels

2. **Accessibility audit**
   - Color contrast check
   - Screen reader testing
   - Reduced motion support

3. **Cross-browser testing**
   - Chrome, Firefox, Safari
   - iOS Safari, Android Chrome
   - Touch device testing

---

## Open Questions & Risks

### Open Questions

| ID | Question | Decision Needed By |
|----|----------|-------------------|
| Q1 | Should we include Inter font or rely on system fonts? | Phase 1 |
| Q2 | Should command palette (Cmd+K) be P0 or P1? | Phase 2 |
| Q3 | How should export UI work on mobile? | Phase 2 |
| Q4 | Should we add a "focus mode" that hides all UI? | Phase 3 |

### Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Breaking existing functionality during refactor | Medium | High | Incremental changes with regression testing |
| Mobile performance issues with complex UI | Low | Medium | Test on real devices throughout development |
| Scope creep adding "just one more thing" | High | Medium | Strict adherence to P0 requirements; timebox phases |
| CSS specificity conflicts | Medium | Low | BEM naming convention, careful cascade order |

---

## Review Checklist

- [x] Does it solve the stated problem? **Yes** — Professional, mobile-first, animated UI
- [x] Is it feasible within constraints? **Yes** — No new dependencies, ~8 day estimate
- [x] Are edge cases handled? **Yes** — Responsive layouts, reduced motion, accessibility
- [x] Is it maintainable? **Yes** — Organized CSS, design tokens, clear component structure

---

## Appendix: File Structure

```
web/
├── index.html              # Minimal HTML shell
├── app.js                  # Application entry (unchanged)
├── data.js                 # Data utilities (unchanged)
├── render.js               # Canvas rendering (unchanged)
├── ui.js                   # UI logic (minor updates for new classes)
├── styles/
│   ├── tokens.css          # Design tokens (colors, spacing, etc.)
│   ├── base.css            # Reset, typography, utilities
│   ├── components.css      # Button, input, card, legend, etc.
│   └── layout.css          # App shell, responsive grid
└── webgl_points.js         # WebGL (unchanged)
```

---

*End of Design Document*
