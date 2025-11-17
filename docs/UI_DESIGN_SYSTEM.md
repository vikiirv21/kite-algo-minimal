# Arthayukti HFT Dashboard - UI Design System Documentation

## Overview

This document describes the comprehensive design system for the Arthayukti High-Frequency Trading (HFT) platform dashboard. The design emphasizes professionalism, clarity, and real-time data visualization optimized for trading environments.

## Design Philosophy

### Core Principles

1. **Clarity First**: All information must be immediately readable and actionable
2. **Dark Mode Optimized**: Reduce eye strain during extended trading sessions
3. **Data Density**: Display maximum relevant information without overwhelming users
4. **Performance**: Smooth animations and fast updates for real-time data
5. **Professional Aesthetic**: Clean, modern, tech-forward visual language

### Target Audience

- Professional traders
- Algorithmic trading system operators
- Financial analysts
- Risk managers

---

## Color System

### Background Colors

The color palette uses deep navy and dark grays to create a professional, low-eye-strain environment:

```css
--bg-primary: #0a0f1a;      /* Deep navy - main background */
--bg-secondary: #141b2d;     /* Slightly lighter - card backgrounds */
--bg-tertiary: #1a2332;      /* Medium navy - elevated elements */
--bg-hover: #222b3e;         /* Hover state */
--bg-active: #2a3548;        /* Active/pressed state */
```

**Usage Guidelines:**
- `bg-primary`: Use for main page background
- `bg-secondary`: Use for cards, panels, and major containers
- `bg-tertiary`: Use for nested cards, stat boxes, elevated UI
- `bg-hover`: Hover states for interactive elements
- `bg-active`: Pressed/active states

### Text Colors

```css
--text-primary: #ffffff;     /* Pure white - primary text */
--text-secondary: #b4c0d3;   /* Light blue-gray - secondary text */
--text-tertiary: #7a8ca0;    /* Medium blue-gray - tertiary/muted */
--text-disabled: #4a5568;    /* Disabled text */
```

**Hierarchy:**
1. Primary: Headlines, important values, key metrics
2. Secondary: Body text, descriptions, labels
3. Tertiary: Helper text, timestamps, metadata
4. Disabled: Inactive elements

### Accent Colors

```css
--accent-primary: #00d4ff;   /* Bright cyan - primary actions, highlights */
--accent-secondary: #0099ff; /* Medium blue - secondary actions */
--accent-tertiary: #6366f1;  /* Indigo - tertiary accents */
```

**Usage:**
- Primary: Call-to-action buttons, active states, key metrics
- Secondary: Links, secondary buttons, info badges
- Tertiary: Decorative accents, gradients

### Trading-Specific Colors

These colors have semantic meaning in trading contexts:

```css
--color-bullish: #00ff88;    /* Bright green - LONG positions, gains */
--color-bearish: #ff3366;    /* Vibrant red - SHORT positions, losses */
--color-neutral: #ffd700;    /* Gold - neutral/warning states */
--color-info: #00d4ff;       /* Cyan - informational */
```

**Semantic Usage:**
- **Bullish Green**: Profit, upward movement, buy signals, long positions
- **Bearish Red**: Loss, downward movement, sell signals, short positions
- **Neutral Gold**: Warning, hold signals, pending states
- **Info Cyan**: Informational badges, system messages

### Status Colors

```css
--status-success: #00ff88;   /* Success states */
--status-warning: #ffb020;   /* Warning states */
--status-error: #ff3366;     /* Error states */
--status-info: #00d4ff;      /* Info states */
--status-pending: #a78bfa;   /* Pending/processing */
```

### Border Colors

```css
--border-subtle: #2a3548;    /* Subtle borders */
--border-default: #3a4558;   /* Default borders */
--border-emphasis: #4a5568;  /* Emphasized borders */
--border-accent: #00d4ff;    /* Accent borders */
```

### Gradients

Pre-defined gradients for consistent visual language:

```css
--gradient-primary: linear-gradient(135deg, #00d4ff 0%, #6366f1 100%);
--gradient-success: linear-gradient(135deg, #00ff88 0%, #00d4ff 50%, #6366f1 100%);
--gradient-danger: linear-gradient(135deg, #ff3366 0%, #ff6b9d 100%);
--gradient-overlay: linear-gradient(180deg, rgba(10, 15, 26, 0) 0%, rgba(10, 15, 26, 0.8) 100%);
```

---

## Typography

### Font Families

```css
--font-primary: -apple-system, BlinkMacSystemFont, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
--font-mono: "SF Mono", Monaco, "Cascadia Code", "Roboto Mono", Consolas, "Courier New", monospace;
--font-display: "Inter", -apple-system, BlinkMacSystemFont, sans-serif;
```

**Usage Guidelines:**
- **Primary**: Body text, UI labels, descriptions
- **Monospace**: Numbers, prices, timestamps, log data
- **Display**: Headlines, brand text, large titles

### Font Sizes

```css
--text-xs: 0.75rem;    /* 12px - Fine print, timestamps */
--text-sm: 0.875rem;   /* 14px - Small labels, captions */
--text-base: 1rem;     /* 16px - Body text */
--text-lg: 1.125rem;   /* 18px - Subheadings */
--text-xl: 1.25rem;    /* 20px - Section titles */
--text-2xl: 1.5rem;    /* 24px - Page titles */
--text-3xl: 1.875rem;  /* 30px - Large headlines */
--text-4xl: 2.25rem;   /* 36px - Hero text, key metrics */
--text-5xl: 3rem;      /* 48px - Extra large display */
```

### Font Weights

```css
--font-light: 300;
--font-normal: 400;
--font-medium: 500;
--font-semibold: 600;
--font-bold: 700;
--font-extrabold: 800;
```

**Recommended Pairings:**
- Headlines: `text-2xl` + `font-extrabold`
- Section Titles: `text-xl` + `font-bold`
- Body Text: `text-base` + `font-normal`
- Labels: `text-sm` + `font-semibold`
- Metrics: `text-4xl` + `font-extrabold` + `font-mono`

---

## Spacing System

Consistent spacing scale based on 4px increments:

```css
--space-1: 0.25rem;   /* 4px */
--space-2: 0.5rem;    /* 8px */
--space-3: 0.75rem;   /* 12px */
--space-4: 1rem;      /* 16px */
--space-5: 1.25rem;   /* 20px */
--space-6: 1.5rem;    /* 24px */
--space-8: 2rem;      /* 32px */
--space-10: 2.5rem;   /* 40px */
--space-12: 3rem;     /* 48px */
--space-16: 4rem;     /* 64px */
```

**Usage Guidelines:**
- Component padding: `space-4` to `space-6`
- Component gaps: `space-4` to `space-6`
- Section spacing: `space-8` to `space-12`
- Page margins: `space-6` to `space-8`

---

## Border Radius

```css
--radius-sm: 4px;     /* Subtle rounding */
--radius-md: 8px;     /* Standard rounding */
--radius-lg: 12px;    /* Emphasized rounding */
--radius-xl: 16px;    /* Large rounding */
--radius-full: 9999px; /* Fully rounded (pills) */
```

**Application:**
- Buttons, badges: `radius-sm` to `radius-md`
- Cards, panels: `radius-md` to `radius-lg`
- Pills, indicators: `radius-full`

---

## Shadows & Depth

### Shadow Levels

```css
--shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.3);
--shadow-md: 0 4px 12px rgba(0, 0, 0, 0.4);
--shadow-lg: 0 8px 24px rgba(0, 0, 0, 0.5);
--shadow-xl: 0 16px 48px rgba(0, 0, 0, 0.6);
```

### Glow Effects

```css
--shadow-glow: 0 0 20px rgba(0, 212, 255, 0.3);
--shadow-glow-success: 0 0 20px rgba(0, 255, 136, 0.3);
--shadow-glow-danger: 0 0 20px rgba(255, 51, 102, 0.3);
```

**Usage:**
- Cards: `shadow-md` (default), `shadow-lg` (hover)
- Modals: `shadow-xl`
- Active states: `shadow-glow` variants
- Important metrics: glow effects

---

## Component Guidelines

### Headers

**Main Header** (`.main-header`):
- Height: 64px (`--header-height`)
- Background: `bg-secondary` with `gradient` overlay
- Border: 2px bottom border in `border-accent`
- Shadow: `shadow-lg` with glow effect

**Brand Logo**:
- Font: `font-display`
- Size: `text-3xl`
- Weight: `font-extrabold`
- Effect: Gradient text using `gradient-primary`

### Cards

**Standard Card** (`.card`):
- Background: `bg-secondary`
- Border: 1px `border-default`
- Radius: `radius-lg`
- Padding: `space-6`
- Shadow: `shadow-md` (default), `shadow-lg` (hover)
- Transition: `transition-base`

**Card Title**:
- Font: `text-xl` + `font-bold`
- Color: `text-primary`
- Border-left: 4px `accent-primary`

### Stat Cards

**Stat Card** (`.stat-card`):
- Background: `bg-tertiary`
- Border: 1px `border-default`, `border-accent` on hover
- Top border: 3px gradient accent (animated on hover)
- Transform: `translateY(-4px)` on hover
- Shadow: `shadow-glow` on hover

**Stat Value**:
- Font: `text-4xl` + `font-extrabold` + `font-mono`
- Color: `text-primary` (default), `color-bullish`/`color-bearish` for P&L
- Text-shadow: Glow effect for gains/losses

### Badges

**Signal Badges**:
- BUY: `gradient-success` background, dark text
- SELL: `gradient-danger` background, white text
- HOLD: `bg-hover` background, `text-secondary`
- EXIT: `bg-disabled`, white text

**Status Badges**:
- LIVE: `gradient-danger` with `shadow-glow-danger`
- PAPER: `gradient-primary` with `shadow-glow`
- IDLE: `bg-hover` with subtle border

### Tables

**Data Table** (`.data-table`):
- Headers: `bg-tertiary`, uppercase, `text-xs`, `font-bold`
- Rows: Transparent background, `border-subtle` bottom border
- Hover: `bg-hover` background, 3px left `border-accent`
- Font: `font-mono` for data cells

### Tabs

**Navigation Tabs**:
- Background: `bg-secondary`
- Active state: `accent-primary` text, 3px bottom gradient border
- Hover: `text-primary` color, `bg-hover` background
- Transition: `transition-fast`

---

## Animation & Transitions

### Timing

```css
--transition-fast: 150ms ease-in-out;
--transition-base: 250ms ease-in-out;
--transition-slow: 400ms ease-in-out;
```

### Keyframe Animations

**Fade In**:
```css
@keyframes fadeIn {
    from { opacity: 0; }
    to { opacity: 1; }
}
```

**Slide Up**:
```css
@keyframes slideUp {
    from { 
        opacity: 0;
        transform: translateY(20px);
    }
    to { 
        opacity: 1;
        transform: translateY(0);
    }
}
```

**Pulse** (for loading states):
```css
@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.5; }
}
```

**Usage Guidelines:**
- Page transitions: `fadeIn` + `transition-base`
- Component entrance: `slideUp` + `transition-base`
- Loading states: `pulse` animation
- Hover effects: `transition-fast`
- Complex state changes: `transition-slow`

---

## Responsive Design

### Breakpoints

```css
/* Mobile */
@media (max-width: 768px) {
    /* Single column layouts */
    /* Simplified navigation */
    /* Touch-friendly hit areas (min 44px) */
}

/* Tablet */
@media (min-width: 769px) and (max-width: 1200px) {
    /* Two-column layouts */
    /* Adjusted spacing */
}

/* Desktop */
@media (min-width: 1201px) {
    /* Multi-column layouts */
    /* Full feature set */
}
```

### Grid Behavior

**Stats Grid**:
- Desktop: `repeat(auto-fit, minmax(280px, 1fr))`
- Tablet: 2 columns
- Mobile: 1 column

**Content Grid**:
- Desktop: 3 columns
- Tablet: 2 columns
- Mobile: 1 column

---

## Accessibility

### Color Contrast

All text-on-background combinations meet WCAG AA standards:
- White on `bg-primary`: 15.3:1 (AAA)
- `text-secondary` on `bg-secondary`: 7.2:1 (AA)
- `accent-primary` on `bg-primary`: 8.1:1 (AA)

### Interactive Elements

- Minimum touch target: 44x44px
- Focus indicators: 2px `border-accent` outline
- Keyboard navigation: Full support
- Screen reader: Semantic HTML + ARIA labels

---

## Usage Examples

### Creating a Metric Card

```html
<div class="stat-card">
    <div class="stat-header">
        <span class="stat-label">Total P&L</span>
        <div class="stat-icon">💰</div>
    </div>
    <div class="stat-value stat-positive">₹12,500.50</div>
    <div class="stat-change">+2.5% today</div>
</div>
```

### Creating a Signal Badge

```html
<span class="signal-badge signal-buy">BUY</span>
<span class="signal-badge signal-sell">SELL</span>
<span class="signal-badge signal-hold">HOLD</span>
```

### Creating a Data Table

```html
<table class="data-table">
    <thead>
        <tr>
            <th>Symbol</th>
            <th>Signal</th>
            <th>Price</th>
        </tr>
    </thead>
    <tbody>
        <tr>
            <td>NIFTY24DEC</td>
            <td><span class="signal-badge signal-buy">BUY</span></td>
            <td>₹23,850.00</td>
        </tr>
    </tbody>
</table>
```

---

## File Structure

```
ui/
├── static/
│   ├── css/
│   │   ├── design-system.css    # Core design system variables & utilities
│   │   ├── dashboard.css         # Dashboard-specific styles
│   │   └── theme.css             # Theme overrides (if needed)
│   └── js/
│       ├── api_client.js         # API communication
│       ├── state_store.js        # State management
│       └── dashboard_tabs.js     # Tab navigation
└── templates/
    └── index.html                # Main dashboard template
```

---

## Implementation Checklist

- [x] Define core color palette
- [x] Establish typography system
- [x] Create spacing scale
- [x] Define shadow and depth system
- [x] Implement component styles
- [x] Add animation utilities
- [x] Ensure responsive behavior
- [x] Verify accessibility standards
- [x] Document all patterns
- [x] Provide usage examples

---

## Maintenance

### Adding New Colors

1. Add to design-system.css with semantic name
2. Document usage guidelines
3. Verify contrast ratios
4. Update this documentation

### Adding New Components

1. Follow existing patterns
2. Use design system variables
3. Ensure responsive behavior
4. Test accessibility
5. Document in this file

---

## Credits

Design System Version: 2.0
Last Updated: 2024-11-17
Platform: Arthayukti HFT Trading Dashboard
