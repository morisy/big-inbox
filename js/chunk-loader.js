/**
 * Chunk Loader for Progressive Email Loading
 * Handles fetching, caching, and management of email content chunks
 */

class ChunkLoader {
    constructor(collectionId, manifestUrl) {
        this.collectionId = collectionId;
        this.manifestUrl = manifestUrl;
        this.manifest = null;
        this.memoryCache = new Map();
        this.loadingChunks = new Set();
        this.baseUrl = window.location.origin + window.location.pathname.replace(/[^/]*$/, '');
    }
    
    /**
     * Initialize the chunk loader and load manifest
     */
    async initialize() {
        try {
            console.log(`Initializing ChunkLoader for collection: ${this.collectionId}`);
            
            // Load manifest
            const response = await fetch(this.manifestUrl);
            if (!response.ok) {
                throw new Error(`Failed to load manifest: ${response.status}`);
            }
            
            this.manifest = await response.json();
            console.log(`Manifest loaded: ${this.manifest.total_emails} emails in ${this.manifest.chunks.length} chunks`);
            
            // Prefetch first chunk (most recent emails)
            if (this.manifest.chunks.length > 0) {
                this.prefetchChunk(0);
            }
            
            return this.manifest;
        } catch (error) {
            console.error('Failed to initialize ChunkLoader:', error);
            throw error;
        }
    }
    
    /**
     * Get email content by document ID
     */
    async getEmailContent(documentId, chunkId = null) {
        // Check memory cache first
        if (this.memoryCache.has(documentId)) {
            console.log(`Email ${documentId} found in memory cache`);
            return this.memoryCache.get(documentId);
        }
        
        // If chunk_id is provided, use it directly
        if (chunkId !== null && chunkId !== undefined) {
            console.log(`Loading email ${documentId} from chunk ${chunkId}`);
            const chunk = await this.loadChunk(chunkId);
            if (chunk && chunk[documentId]) {
                return chunk[documentId];
            } else {
                console.warn(`Email ${documentId} not found in chunk ${chunkId}`);
            }
        }
        
        // Fallback: Find which chunk contains this email
        const foundChunkId = await this.findChunkForEmail(documentId);
        if (foundChunkId === null) {
            console.warn(`Email ${documentId} not found in any chunk`);
            return null;
        }
        
        // Load chunk
        const chunk = await this.loadChunk(foundChunkId);
        if (!chunk || !chunk[documentId]) {
            console.warn(`Email ${documentId} not found in chunk ${foundChunkId}`);
            return null;
        }
        
        return chunk[documentId];
    }
    
    /**
     * Find which chunk contains a specific email
     */
    async findChunkForEmail(documentId) {
        // This requires either:
        // 1. Querying the metadata database for chunk_id
        // 2. Or iterating through chunks (less efficient)
        
        // For now, we'll need to search chunks
        // In production, query metadata.db for efficiency
        for (const chunkInfo of this.manifest.chunks) {
            if (this.memoryCache.has(`chunk_${chunkInfo.chunk_id}`)) {
                const chunk = this.memoryCache.get(`chunk_${chunkInfo.chunk_id}`);
                if (chunk[documentId]) {
                    return chunkInfo.chunk_id;
                }
            }
        }
        
        // If not in cache, we need to check metadata or load chunks
        // This is where metadata.db query would be most efficient
        return null;
    }
    
    /**
     * Load a specific chunk
     */
    async loadChunk(chunkId) {
        const cacheKey = `chunk_${chunkId}`;
        
        // Check memory cache
        if (this.memoryCache.has(cacheKey)) {
            return this.memoryCache.get(cacheKey);
        }
        
        // Prevent duplicate loading
        if (this.loadingChunks.has(chunkId)) {
            console.log(`Chunk ${chunkId} already loading, waiting...`);
            // Wait for existing load to complete
            await this.waitForChunk(chunkId);
            return this.memoryCache.get(cacheKey);
        }
        
        this.loadingChunks.add(chunkId);
        
        try {
            const chunkInfo = this.manifest.chunks[chunkId];
            if (!chunkInfo) {
                throw new Error(`Chunk ${chunkId} not found in manifest`);
            }
            
            console.log(`Loading chunk ${chunkId} from ${chunkInfo.path}`);
            
            // Construct URL
            const chunkUrl = this.baseUrl + chunkInfo.path;
            
            // Fetch chunk
            const response = await fetch(chunkUrl);
            if (!response.ok) {
                throw new Error(`Failed to load chunk: ${response.status}`);
            }
            
            // Handle gzipped content
            let data;
            if (chunkInfo.path.endsWith('.gz')) {
                // Browser should auto-decompress if server sends correct headers
                // Otherwise, we'd need pako or similar library
                data = await response.json();
            } else {
                data = await response.json();
            }
            
            // Cache in memory
            this.memoryCache.set(cacheKey, data);
            
            // Cache individual emails for quick access
            Object.keys(data).forEach(docId => {
                this.memoryCache.set(docId, data[docId]);
            });
            
            console.log(`Chunk ${chunkId} loaded: ${Object.keys(data).length} emails`);
            
            return data;
            
        } catch (error) {
            console.error(`Failed to load chunk ${chunkId}:`, error);
            throw error;
        } finally {
            this.loadingChunks.delete(chunkId);
        }
    }
    
    /**
     * Wait for a chunk that's currently loading
     */
    async waitForChunk(chunkId) {
        const maxWait = 30000; // 30 seconds
        const checkInterval = 100; // 100ms
        let waited = 0;
        
        while (this.loadingChunks.has(chunkId) && waited < maxWait) {
            await new Promise(resolve => setTimeout(resolve, checkInterval));
            waited += checkInterval;
        }
        
        if (waited >= maxWait) {
            throw new Error(`Timeout waiting for chunk ${chunkId}`);
        }
    }
    
    /**
     * Prefetch a chunk in the background
     */
    async prefetchChunk(chunkId) {
        if (this.memoryCache.has(`chunk_${chunkId}`)) {
            return; // Already cached
        }
        
        try {
            await this.loadChunk(chunkId);
            console.log(`Prefetched chunk ${chunkId}`);
        } catch (error) {
            console.warn(`Failed to prefetch chunk ${chunkId}:`, error);
        }
    }
    
    /**
     * Prefetch adjacent chunks for an email
     */
    async prefetchAdjacentChunks(currentChunkId) {
        const prefetchRange = 1; // Prefetch 1 chunk in each direction
        
        for (let offset = -prefetchRange; offset <= prefetchRange; offset++) {
            if (offset === 0) continue; // Skip current chunk
            
            const targetChunkId = currentChunkId + offset;
            if (targetChunkId >= 0 && targetChunkId < this.manifest.chunks.length) {
                this.prefetchChunk(targetChunkId);
            }
        }
    }
    
    /**
     * Clear memory cache (useful for memory management)
     */
    clearMemoryCache() {
        const sizeBefore = this.memoryCache.size;
        this.memoryCache.clear();
        console.log(`Cleared memory cache: ${sizeBefore} items removed`);
    }
    
    /**
     * Get cache statistics
     */
    getCacheStats() {
        return {
            memoryCacheSize: this.memoryCache.size,
            chunksLoaded: Array.from(this.memoryCache.keys())
                .filter(key => key.startsWith('chunk_')).length,
            emailsCached: Array.from(this.memoryCache.keys())
                .filter(key => !key.startsWith('chunk_')).length,
            totalChunks: this.manifest ? this.manifest.chunks.length : 0
        };
    }
}

/**
 * IndexedDB Cache Manager for persistent storage
 */
class CacheManager {
    constructor(dbName = 'OpenInboxCache', version = 1) {
        this.dbName = dbName;
        this.version = version;
        this.db = null;
        this.cacheExpiry = 7 * 24 * 60 * 60 * 1000; // 7 days
    }
    
    /**
     * Initialize IndexedDB
     */
    async initialize() {
        return new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.version);
            
            request.onerror = () => {
                console.error('Failed to open IndexedDB:', request.error);
                reject(request.error);
            };
            
            request.onsuccess = () => {
                this.db = request.result;
                console.log('IndexedDB initialized');
                resolve(this.db);
            };
            
            request.onupgradeneeded = (event) => {
                const db = event.target.result;
                
                // Create chunks store
                if (!db.objectStoreNames.contains('chunks')) {
                    const chunksStore = db.createObjectStore('chunks', { keyPath: 'id' });
                    chunksStore.createIndex('collectionId', 'collectionId', { unique: false });
                    chunksStore.createIndex('timestamp', 'timestamp', { unique: false });
                }
                
                // Create metadata store
                if (!db.objectStoreNames.contains('metadata')) {
                    db.createObjectStore('metadata', { keyPath: 'id' });
                }
                
                console.log('IndexedDB schema created/updated');
            };
        });
    }
    
    /**
     * Store a chunk in IndexedDB
     */
    async storeChunk(collectionId, chunkId, data) {
        if (!this.db) {
            await this.initialize();
        }
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['chunks'], 'readwrite');
            const store = transaction.objectStore('chunks');
            
            const record = {
                id: `${collectionId}_chunk_${chunkId}`,
                collectionId: collectionId,
                chunkId: chunkId,
                data: data,
                timestamp: Date.now()
            };
            
            const request = store.put(record);
            
            request.onsuccess = () => {
                console.log(`Stored chunk ${chunkId} in IndexedDB`);
                resolve();
            };
            
            request.onerror = () => {
                console.error(`Failed to store chunk ${chunkId}:`, request.error);
                reject(request.error);
            };
        });
    }
    
    /**
     * Retrieve a chunk from IndexedDB
     */
    async getChunk(collectionId, chunkId) {
        if (!this.db) {
            await this.initialize();
        }
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['chunks'], 'readonly');
            const store = transaction.objectStore('chunks');
            const request = store.get(`${collectionId}_chunk_${chunkId}`);
            
            request.onsuccess = () => {
                const record = request.result;
                
                if (!record) {
                    resolve(null);
                    return;
                }
                
                // Check expiry
                if (Date.now() - record.timestamp > this.cacheExpiry) {
                    console.log(`Chunk ${chunkId} expired in cache`);
                    this.deleteChunk(collectionId, chunkId);
                    resolve(null);
                    return;
                }
                
                console.log(`Retrieved chunk ${chunkId} from IndexedDB`);
                resolve(record.data);
            };
            
            request.onerror = () => {
                console.error(`Failed to retrieve chunk ${chunkId}:`, request.error);
                reject(request.error);
            };
        });
    }
    
    /**
     * Delete a chunk from IndexedDB
     */
    async deleteChunk(collectionId, chunkId) {
        if (!this.db) {
            await this.initialize();
        }
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['chunks'], 'readwrite');
            const store = transaction.objectStore('chunks');
            const request = store.delete(`${collectionId}_chunk_${chunkId}`);
            
            request.onsuccess = () => {
                console.log(`Deleted chunk ${chunkId} from IndexedDB`);
                resolve();
            };
            
            request.onerror = () => {
                console.error(`Failed to delete chunk ${chunkId}:`, request.error);
                reject(request.error);
            };
        });
    }
    
    /**
     * Clear all expired chunks
     */
    async clearExpiredChunks() {
        if (!this.db) {
            await this.initialize();
        }
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['chunks'], 'readwrite');
            const store = transaction.objectStore('chunks');
            const index = store.index('timestamp');
            
            const expiryCutoff = Date.now() - this.cacheExpiry;
            const range = IDBKeyRange.upperBound(expiryCutoff);
            
            const request = index.openCursor(range);
            let deletedCount = 0;
            
            request.onsuccess = (event) => {
                const cursor = event.target.result;
                
                if (cursor) {
                    store.delete(cursor.primaryKey);
                    deletedCount++;
                    cursor.continue();
                } else {
                    console.log(`Cleared ${deletedCount} expired chunks`);
                    resolve(deletedCount);
                }
            };
            
            request.onerror = () => {
                console.error('Failed to clear expired chunks:', request.error);
                reject(request.error);
            };
        });
    }
    
    /**
     * Get cache statistics
     */
    async getCacheStats() {
        if (!this.db) {
            await this.initialize();
        }
        
        return new Promise((resolve, reject) => {
            const transaction = this.db.transaction(['chunks'], 'readonly');
            const store = transaction.objectStore('chunks');
            const countRequest = store.count();
            
            countRequest.onsuccess = () => {
                resolve({
                    chunksStored: countRequest.result,
                    dbName: this.dbName,
                    cacheExpiryDays: this.cacheExpiry / (24 * 60 * 60 * 1000)
                });
            };
            
            countRequest.onerror = () => {
                reject(countRequest.error);
            };
        });
    }
}

/**
 * Enhanced Chunk Loader with IndexedDB support
 */
class EnhancedChunkLoader extends ChunkLoader {
    constructor(collectionId, manifestUrl) {
        super(collectionId, manifestUrl);
        this.cacheManager = new CacheManager();
        this.initialized = false;
    }
    
    async initialize() {
        // Initialize parent
        await super.initialize();
        
        // Initialize cache manager
        try {
            await this.cacheManager.initialize();
            this.initialized = true;
            
            // Clear expired chunks periodically
            setInterval(() => {
                this.cacheManager.clearExpiredChunks();
            }, 60 * 60 * 1000); // Every hour
            
        } catch (error) {
            console.warn('IndexedDB initialization failed, using memory cache only:', error);
        }
        
        return this.manifest;
    }
    
    async loadChunk(chunkId) {
        const cacheKey = `chunk_${chunkId}`;
        
        // Check memory cache
        if (this.memoryCache.has(cacheKey)) {
            return this.memoryCache.get(cacheKey);
        }
        
        // Check IndexedDB cache
        if (this.initialized) {
            try {
                const cachedData = await this.cacheManager.getChunk(this.collectionId, chunkId);
                if (cachedData) {
                    // Store in memory cache
                    this.memoryCache.set(cacheKey, cachedData);
                    
                    // Cache individual emails
                    Object.keys(cachedData).forEach(docId => {
                        this.memoryCache.set(docId, cachedData[docId]);
                    });
                    
                    console.log(`Chunk ${chunkId} loaded from IndexedDB`);
                    return cachedData;
                }
            } catch (error) {
                console.warn(`Failed to load chunk ${chunkId} from IndexedDB:`, error);
            }
        }
        
        // Load from network
        const data = await super.loadChunk(chunkId);
        
        // Store in IndexedDB
        if (this.initialized && data) {
            this.cacheManager.storeChunk(this.collectionId, chunkId, data)
                .catch(error => console.warn(`Failed to cache chunk ${chunkId}:`, error));
        }
        
        return data;
    }
    
    async getCacheStats() {
        const memoryStats = super.getCacheStats();
        
        if (this.initialized) {
            try {
                const dbStats = await this.cacheManager.getCacheStats();
                return { ...memoryStats, ...dbStats };
            } catch (error) {
                console.warn('Failed to get IndexedDB stats:', error);
            }
        }
        
        return memoryStats;
    }
}

// Export for use in index.html
window.ChunkLoader = ChunkLoader;
window.CacheManager = CacheManager;
window.EnhancedChunkLoader = EnhancedChunkLoader;