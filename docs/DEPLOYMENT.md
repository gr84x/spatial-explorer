# Deployment

Spatial Explorer is deployed as a static site.

## Production

**URL:** https://spatialexplorer.gr84x.com

### Infrastructure
- **Hosting:** DigitalOcean App Platform (Static Site)
- **CDN/SSL:** Cloudflare (proxied)
- **DNS:** Cloudflare zone `gr84x.com`

### Auto-Deploy
The app auto-deploys from the `main` branch of `gr84x/spatial-explorer`.

Push to `main` → DigitalOcean rebuilds → Live in ~2 minutes.

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
