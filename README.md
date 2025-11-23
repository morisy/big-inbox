# Open Inbox - DocumentCloud Add-On

A DocumentCloud Add-On that converts document collections into browsable, searchable email-like interfaces with progressive loading for 10,000+ documents.

## Features

- 📧 **Email Interface**: Gmail-like browsing experience for DocumentCloud documents
- 🚀 **Progressive Loading**: Instant initial load with content loading on-demand
- 🔍 **Full Search**: Fast searching across all email metadata
- 📊 **Scales to 10K+ Emails**: Chunked architecture handles large collections efficiently
- 🌐 **GitHub Pages Deployment**: Automatic deployment to static hosting
- 🔗 **Permalinks**: Direct links to specific emails

## Files & Structure

### Core Add-On Files
- `main.py` - DocumentCloud Add-On with chunked architecture
- `config.yaml` - Add-On configuration for DocumentCloud
- `requirements.txt` - Python dependencies
- `CLAUDE.md` - Developer documentation and architecture details

### Web Interface
- `index.html` - Progressive loading email explorer interface  
- `collections.html` - Collections browser page
- `js/chunk-loader.js` - Client-side chunk loading system

### Data Directory
- `collections/` - SQLite databases for existing email collections
- `collections/index.json` - Collection metadata index

### GitHub Actions
- `.github/workflows/run-addon.yml` - DocumentCloud Add-On runner

## How It Works

1. **DocumentCloud Processing**: Select documents and run the Add-On
2. **Data Extraction**: Extracts email metadata from document tags or text
3. **Chunked Storage**: Creates metadata database + content chunks (500 emails/chunk)
4. **GitHub Deployment**: Automatically deploys to GitHub Pages
5. **Progressive Loading**: Users browse instantly while content loads on-demand

## Architecture

- **Metadata Database** (~1.4MB for 2000 emails): SQLite with all email metadata for instant browsing
- **Content Chunks** (~650KB each): JSON files with full email content
- **Three-Tier Caching**: Memory → IndexedDB → Network for optimal performance
- **Static Hosting**: Works entirely on GitHub Pages with no backend

## Usage

### Running the Add-On
1. Select documents in DocumentCloud
2. Run "Open Inbox" Add-On
3. Provide collection name
4. Receive GitHub Pages URL for browsing

### Local Development
```bash
# Install dependencies
pip install -r requirements.txt

# Test Add-On locally
python main.py --query "your search query"

# View interface
python -m http.server 8000
# Visit http://localhost:8000
```

## Capacity

| Collection Size | Initial Load | Search Speed | Storage  |
|----------------|--------------|--------------|----------|
| 2,000 emails   | < 2s        | < 100ms      | ~4MB     |
| 10,000 emails  | < 2s        | < 150ms      | ~20MB    |
| 25,000 emails  | < 3s        | < 200ms      | ~50MB    |

## Links

- **Live Demo**: https://morisy.github.io/open-inbox/
- **DocumentCloud Add-On**: https://www.documentcloud.org/add-ons/morisy/open-inbox/
- **Repository**: https://github.com/morisy/open-inbox

## License

MIT License - See repository for details