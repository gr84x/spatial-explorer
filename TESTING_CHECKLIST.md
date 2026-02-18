# Testing Checklist for UI Fixes

## Pre-Test Setup
- [ ] Clear browser localStorage (or use incognito mode)
- [ ] Test in both light and dark modes
- [ ] Test on desktop and mobile viewport sizes

## Test Scenarios

### 1. Upload Overlay Behavior ✅
**Expected**: Overlay should NOT show when demo data is loaded

- [ ] Load the app fresh (demo data loads automatically)
- [ ] **VERIFY**: Demo visualization is immediately visible
- [ ] **VERIFY**: No "Drop a file or click Upload" overlay blocking the view
- [ ] **VERIFY**: Can interact with the visualization immediately
- [ ] Click "Upload" button in toolbar
- [ ] **VERIFY**: File picker opens
- [ ] Refresh page and check if overlay still hidden with demo

### 2. Export Dropdown Polish ✅
**Expected**: Clean menu items, not button-like

- [ ] Click "Export" button in toolbar
- [ ] **VERIFY**: Dropdown opens with clean menu items
- [ ] **VERIFY**: "Export PNG" and "Export SVG" look like menu items (not buttons)
- [ ] **VERIFY**: Icons are properly sized (16x16) and aligned
- [ ] **VERIFY**: Spacing between icon and text looks clean (12px gap)
- [ ] Hover over menu items
- [ ] **VERIFY**: Smooth background color transition
- [ ] **VERIFY**: Icon opacity increases on hover

### 3. Settings in Dropdown ✅
**Expected**: Resolution and µm/px visually grouped with subtle background

- [ ] With export dropdown open, scroll to bottom
- [ ] **VERIFY**: Settings section has subtle background (darker than menu)
- [ ] **VERIFY**: "Resolution" and "µm/px" are clearly labeled
- [ ] **VERIFY**: Inputs are properly sized and aligned
- [ ] **VERIFY**: Section looks good in both light and dark mode
- [ ] **VERIFY**: Divider above settings is subtle (opacity: 0.6)

### 4. "or continue with demo" Link ✅
**Expected**: Subtle link with no underline on hover

- [ ] Clear localStorage and reload (to see empty state)
- [ ] **VERIFY**: Welcome overlay appears
- [ ] **VERIFY**: "or continue with demo" text is subtle gray
- [ ] Hover over the link
- [ ] **VERIFY**: Color changes to lighter (no underline)
- [ ] **VERIFY**: Cursor shows pointer
- [ ] Click the link
- [ ] **VERIFY**: Overlay dismisses and demo shows

### 5. Footer Styling ✅
**Expected**: Clean, minimal, elegant branding

- [ ] Scroll to bottom of page
- [ ] **VERIFY**: Footer text reads "a gr84x experience" (all lowercase)
- [ ] **VERIFY**: "a" and "experience" are muted gray (opacity: 0.7)
- [ ] **VERIFY**: "gr84x" uses theme accent color (blue by default)
- [ ] **VERIFY**: Overall look is minimal and professional
- [ ] Hover over "gr84x" link
- [ ] **VERIFY**: Opacity increases smoothly (no complex effects)
- [ ] **VERIFY**: Letter-spacing increases slightly
- [ ] Switch to light mode
- [ ] **VERIFY**: Footer still looks good with proper contrast
- [ ] Click "gr84x" link
- [ ] **VERIFY**: Opens https://gr84x.com in new tab

## Regression Testing

### Core Functionality
- [ ] Gene search still works
- [ ] Cell selection still works
- [ ] Pan/zoom still works
- [ ] Export PNG/SVG still works
- [ ] Theme toggle still works
- [ ] File upload still works
- [ ] All controls respond properly

### Visual Consistency
- [ ] All changes work in light mode
- [ ] All changes work in dark mode
- [ ] No visual glitches or artifacts
- [ ] Animations are smooth
- [ ] Mobile layout still responsive

## Performance
- [ ] No noticeable performance degradation
- [ ] Dropdown opens/closes smoothly
- [ ] Page loads quickly with demo data

## Accessibility
- [ ] All interactive elements still keyboard accessible
- [ ] Focus states visible and working
- [ ] Screen reader text still appropriate
- [ ] Touch targets adequate (min 42px)

## Browser Testing
- [ ] Chrome/Edge (Chromium)
- [ ] Firefox
- [ ] Safari
- [ ] Mobile Safari (iOS)
- [ ] Mobile Chrome (Android)

## Final Checks
- [ ] No console errors
- [ ] No console warnings
- [ ] localStorage working properly
- [ ] URL state syncing works
- [ ] All tooltips still working

---

## Summary of Changes

1. **Upload overlay** - Only shows when cells.length === 0
2. **Export menu** - Cleaner, more menu-like styling
3. **Settings section** - Subtle background for visual grouping
4. **Demo link** - No underline on hover
5. **Footer** - Minimal, elegant, uses theme colors

All changes maintain backward compatibility and don't break existing functionality.
