# Dashboard Migration Notes

## Old vs New Dashboard

This repository now has **two dashboard implementations**:

### 1. New Arthayukti Dashboard (Active) ✓
**Location:** `ui/templates/index.html`
**Status:** Currently served at `/`
**Description:** Clean, modern, dark-themed dashboard with proper API wiring

**Files:**
- `ui/templates/index.html` - Main template
- `ui/static/css/arthayukti.css` - Dark theme stylesheet
- `ui/static/js/arthayukti.js` - Dashboard controller
- `ARTHAYUKTI_DASHBOARD.md` - User guide

**Features:**
- Beautiful dark theme with Arthayukti branding
- Automatic mode detection (Paper/Live/Idle)
- Real-time polling of all APIs
- Clean panel-based layout
- Proper error handling
- No conflicting implementations

### 2. Old Dashboards (Preserved)
**Location:** `ui/templates/base.html` and `ui/templates/dashboard.html`
**Status:** Not currently served, preserved for reference
**Description:** Previous implementations with HTMX and Tailwind

**Files:**
- `ui/templates/base.html` - HTMX-based modular dashboard
- `ui/templates/dashboard.html` - Tailwind CSS all-in-one dashboard  
- `ui/static/dashboard.js` - Old dashboard controller
- `ui/static/dashboard_v2.js` - Alternative implementation
- `ui/static/dashboard.css` - Old stylesheets

**Why Preserved:**
- May contain useful components for future reference
- Allows easy rollback if needed
- No harm in keeping (not loaded by default)

## Switching Between Dashboards

To switch back to an old dashboard, edit `ui/dashboard.py`:

```python
@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("index.html", {"request": request})
    # Change to: return templates.TemplateResponse("base.html", {"request": request})
    # Or: return templates.TemplateResponse("dashboard.html", {"request": request})
```

## Cleanup (Optional)

If you want to remove old dashboard files after confirming the new one works:

```bash
# Remove old templates (be careful!)
rm ui/templates/base.html
rm ui/templates/dashboard.html

# Remove old static files
rm ui/static/dashboard.js
rm ui/static/dashboard_v2.js  
rm ui/static/dashboard.css
rm ui/static/ui-polish.js

# Keep only new Arthayukti files:
# - ui/templates/index.html
# - ui/static/css/arthayukti.css
# - ui/static/js/arthayukti.js
```

## Recommendation

**Keep the old files for now** until the new dashboard has been thoroughly tested in production. After 1-2 weeks of stable operation, consider cleanup.
