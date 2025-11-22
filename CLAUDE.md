# Open Inbox DocumentCloud Add-On - Developer Guide

## Overview
Open Inbox is a DocumentCloud Add-On that converts DocumentCloud documents into browsable email-like interfaces. It extracts metadata from document tags, creates SQLite databases, and deploys them to GitHub Pages for viewing.

## Project Structure

### Core Files
- **main.py** - DocumentCloud Add-On logic that processes documents and creates SQLite databases
- **index.html** - Main email explorer interface (single-page app)
- **collections.html** - Collections browser page
- **config.yaml** - DocumentCloud Add-On configuration
- **requirements.txt** - Python dependencies
- **.github/workflows/run-addon.yml** - GitHub Actions workflow for DocumentCloud

### Collections Directory
- **collections/*.db** - SQLite database files created by the Add-On
- **collections/index.json** - Metadata about available collections (manually maintained currently)

## Key Features

### Working Features
- Extracts email metadata from DocumentCloud document tags (from, to, subject, date)
- Creates SQLite databases with email-like structure
- Commits databases to GitHub repository via API
- Web interface for browsing/searching emails
- Links back to original DocumentCloud documents
- Dynamic collection titles from database metadata
- Mobile-responsive design

### Removed/Non-functional Features
- **Starred emails** - Removed (was not implemented)
- **Sent folder** - Removed (emails don't have folder field populated)
- **Upload button** - Replaced with Help/About modal

## Database Schema

### Tables
1. **emails** - Main email records table
   - document_id (unique DC identifier)
   - sender_email, sender_name
   - recipient_email, recipient_name
   - subject, body, preview
   - date_sent
   - metadata (JSON - includes document_url)

2. **collection_info** - Metadata about the collection
   - id, name, display_name
   - created_at, record_count

3. **contacts** - Extracted email addresses
4. **email_search** - FTS5 virtual table for full-text search

## Known Issues & Solutions

### Mobile Loading Issues
- **Problem**: Call stack exceeded when converting large arrays to base64
- **Solution**: Skip localStorage caching on mobile devices, use chunked processing on desktop

### Custom Domain SSL
- **Problem**: Shows "Not Secure" on custom domains
- **Solution**: Enable "Enforce HTTPS" in GitHub Pages settings, ensure proper DNS configuration

### Button Event Listeners
- **Problem**: Buttons stop working when elements don't exist
- **Solution**: Always check if DOM elements exist before adding event listeners

## Development Tips

### Testing Locally
```bash
# Test the Add-On locally
python main.py --query "your search query"

# Serve the web interface locally
python -m http.server 8000
# Then visit http://localhost:8000
```

### Debugging Mobile
1. Enable mobile browser dev tools:
   - iOS: Settings → Safari → Advanced → Web Inspector
   - Android: Chrome DevTools remote debugging
2. Check console for detailed logging added throughout

### Adding New Collections
When the Add-On creates a new database:
1. It automatically commits to `collections/[id]_[name].db`
2. You need to manually update `collections/index.json` with metadata
3. Future improvement: Auto-update index.json in main.py

### URL Structure
- Collections page: `/collections.html`
- View collection: `/?emails=[collection_id]`
- The site works on both:
  - `morisy.github.io/open-inbox/`
  - `morisy.com/open-inbox/` (custom domain)

## Common Commands

### Lint and Type Checking
```bash
# Currently no linting configured
# TODO: Add ruff or flake8 for Python
# TODO: Add eslint for JavaScript in HTML
```

### Git Operations
```bash
# The Add-On auto-commits databases
# Manual commits for code changes:
git add .
git commit -m "Your message"
git push origin main
```

## Architecture Decisions

### Why Single HTML Files?
- Simplicity for GitHub Pages hosting
- No build process required
- SQL.js allows client-side SQLite queries
- Self-contained, works offline once loaded

### Why GitHub as Database Storage?
- Free hosting via GitHub Pages
- Version control for data
- No backend server needed
- DocumentCloud Add-Ons can commit directly via GitHub API

### Database Size Limits
- GitHub API: 100MB per file (we limit to 50MB)
- localStorage: ~10MB (skip on mobile)
- SQL.js can handle large databases client-side

## Future Improvements

### High Priority
1. Auto-update collections/index.json when creating new databases
2. Add pagination or virtual scrolling for large email lists
3. Improve mobile performance with lazy loading

### Nice to Have
1. Export functionality (CSV, JSON)
2. Advanced search filters (date range, attachments)
3. Email threading visualization
4. Bulk operations on emails
5. Progressive Web App features

## DocumentCloud Add-On Specifics

### Required Environment Variables
- `TOKEN` - GitHub personal access token (set in DocumentCloud Add-On settings)
- `GITHUB_REPO` - Repository name (owner/repo format)

### Add-On Parameters
- `collection_name` - Name for the email collection
- `date_format` - Date parsing format (default: %Y-%m-%d)

### How DocumentCloud Runs This
1. User selects documents in DocumentCloud
2. Runs Add-On which calls main.py
3. Add-On extracts metadata from doc.data tags
4. Creates SQLite database
5. Commits to GitHub via API
6. Returns GitHub Pages URL to user

### Common Add-On Methods
```python
# From documentcloud.addon import AddOn
self.set_progress(0-100)  # Update progress bar
self.set_message("Status")  # Update status message
self.upload_file(file)  # Upload file back to DocumentCloud
self.send_mail("Subject", "Body")  # Email user
```

### Accessing Document Data
```python
# Document metadata stored in doc.data dictionary
doc.data.get('from')  # Get sender
doc.data.get('to')    # Get recipient
doc.data.get('subject')  # Get subject
doc.data.get('docDate')  # Get document date

# Document properties
doc.id  # Unique document ID
doc.title  # Document title
doc.full_text  # Full extracted text
doc.page_count  # Number of pages
doc.source  # Source of document
doc.created_at  # When uploaded
doc.canonical_url  # Public URL
```

## Security Considerations
- Never commit secrets/keys to repository
- Document URLs are public in DocumentCloud
- Databases are publicly accessible via GitHub Pages
- No authentication on the web interface

## Contact & Resources

### DocumentCloud Documentation
- **Add-On Tutorial**: https://github.com/MuckRock/documentcloud-hello-world-addon/wiki
- **Add-On Python Library**: https://github.com/MuckRock/python-documentcloud-addon
- **DocumentCloud API**: https://www.documentcloud.org/help/api/
- **Python Client Library**: https://github.com/MuckRock/python-documentcloud
- **Add-On Development Guide**: https://github.com/MuckRock/documentcloud-hello-world-addon/wiki/Add-On-Development

### Key API Endpoints
- Document data structure: https://www.documentcloud.org/help/api/#documents
- Document metadata (doc.data): Stored as key-value pairs accessible via `doc.data`
- Full text access: `doc.full_text` or `doc.get_full_text()`

### Reusable GitHub Workflows
- **Official Workflow**: https://github.com/MuckRock/documentcloud-addon-workflows
- Used in `.github/workflows/run-addon.yml`

### This Add-On
- **Open Inbox Add-On Page**: https://www.documentcloud.org/add-ons/morisy/open-inbox/
- **Repository**: https://github.com/morisy/open-inbox
- **Live Site**: https://morisy.github.io/open-inbox/