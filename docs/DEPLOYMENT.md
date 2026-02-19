# Deployment

Spatial Explorer is deployed as a static site.

## Production

**URL:** https://spatialexplorer.gr84x.com

### Infrastructure
- **Hosting:** DigitalOcean App Platform (Static Site)
- **CDN/SSL:** Cloudflare (proxied)
- **DNS:** Cloudflare zone `gr84x.com`

### Auto-Deploy
The app auto-deploys via GitHub Actions when CI succeeds on `main`.

Merge to `main` → CI passes → GitHub Actions triggers a DigitalOcean App Platform deployment → Live in ~2 minutes.

#### GitHub Actions configuration
Required in GitHub repo settings:
- **Secret:** `DIGITALOCEAN_ACCESS_TOKEN` (DigitalOcean API token with access to App Platform)
- **Variable:** `DIGITALOCEAN_APP_ID` (DigitalOcean App Platform app ID)

The deploy workflow is `.github/workflows/deploy.yml`.

### DNS Configuration
- **Record:** CNAME `spatialexplorer` → `spatial-explorer-qqgdl.ondigitalocean.app`
- **Proxied:** Yes (Cloudflare SSL/CDN)

### Health Check
```bash
curl -I https://spatialexplorer.gr84x.com
# Should return HTTP 200
```

## Local Development

```bash
# Serve the web/ directory
cd web
python3 -m http.server 8000
# Open http://localhost:8000
```

## Static Files
All static files are in `web/`:
- `index.html` - Main app
- `styles.css` - Stylesheet
- `app.js`, `data.js`, `render.js`, `ui.js` - JavaScript modules
