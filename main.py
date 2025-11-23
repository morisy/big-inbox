#!/usr/bin/env python3
"""
Open Inbox - DocumentCloud Add-On with Progressive Loading Architecture
Converts DocumentCloud documents into a browsable email-like interface with chunked content storage.
"""

import os
import sys
import sqlite3
import json
import re
import requests
import hashlib
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, asdict
from documentcloud.addon import SoftTimeOutAddOn
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

CHUNK_SIZE = 500  # Emails per chunk
MAX_PREVIEW_LENGTH = 200  # Characters for preview
MAX_BODY_LENGTH = 50000  # Max body length to store (50KB)


@dataclass
class EmailMetadata:
    """Lightweight email metadata for quick browsing"""
    email_id: int
    document_id: str
    sender_email: str
    sender_name: str
    recipient_email: str
    recipient_name: str
    subject: str
    preview: str
    date_sent: Optional[datetime]
    chunk_id: int
    
    
@dataclass
class EmailContent:
    """Full email content stored in chunks"""
    email_id: int
    document_id: str
    body: str
    full_text: str  # For search
    source: str
    document_url: str
    page_count: int
    file_type: str
    tags: List[str]


@dataclass
class EmailRecord:
    """Complete email record (metadata + content)"""
    document_id: str
    sender_email: str
    sender_name: str
    recipient_email: str
    recipient_name: str
    subject: str
    body: str
    full_text: str
    preview: str
    date_sent: Optional[datetime]
    source: str
    document_url: str
    page_count: int
    file_type: str
    tags: List[str]


class ChunkedOpenInbox(SoftTimeOutAddOn):
    """Open Inbox with progressive loading architecture for 10K+ emails"""
    
    soft_time_limit = 240  # 4 minutes timeout
    
    def __init__(self):
        super().__init__()
        self.timed_out = False
        self.processed_doc_ids = set()
        self.chunk_storage = []  # Accumulate emails for chunking
        
    def restore(self):
        """Restore processing state from previous run if timeout occurred"""
        if os.path.exists("cache/processed_docs.json"):
            with open("cache/processed_docs.json", "r") as f:
                self.processed_doc_ids = set(json.load(f))
            logger.info(f"Restored state: {len(self.processed_doc_ids)} documents already processed")
        else:
            logger.info("Starting fresh processing")
    
    def cleanup(self):
        """Save processing state when timeout occurs"""
        os.makedirs("cache", exist_ok=True)
        with open("cache/processed_docs.json", "w") as f:
            json.dump(list(self.processed_doc_ids), f)
        logger.info(f"Timeout occurred. Saved state: {len(self.processed_doc_ids)} documents processed")
        self.timed_out = True
    
    def main(self):
        """Main Add-On execution with chunked architecture"""
        try:
            self.restore()
            
            # Get parameters
            collection_name = self.data.get("collection_name", "").strip()
            date_format = self.data.get("date_format", "auto")
            
            if not collection_name:
                self.set_message("❌ Collection name is required")
                return
                
            self.set_message("🔍 Processing documents...")
            self.set_progress(0)
            
            # Get documents to process
            all_documents = self.get_documents()
            if not all_documents:
                self.set_message("❌ No documents found to process")
                return
            
            # Filter out already processed documents
            remaining_documents = [doc for doc in all_documents if str(doc.id) not in self.processed_doc_ids]
            
            total_docs = len(all_documents)
            processed_count = len(self.processed_doc_ids)
            remaining_count = len(remaining_documents)
            
            logger.info(f"Total: {total_docs}, Processed: {processed_count}, Remaining: {remaining_count}")
            
            if remaining_count == 0:
                self.set_message("✅ All documents already processed!")
                return
            
            # Process all remaining documents
            self.set_message(f"📄 Processing {remaining_count} documents...")
            
            # Extract email records
            email_records = []
            for i, doc in enumerate(remaining_documents):
                try:
                    record = self.extract_email_record(doc, date_format)
                    if record:
                        email_records.append(record)
                        self.processed_doc_ids.add(str(doc.id))
                    
                    # Update progress
                    progress = int((i + 1) / remaining_count * 40)
                    self.set_progress(progress)
                    self.set_message(f"📄 Extracting emails... ({i+1}/{remaining_count})")
                    
                except Exception as e:
                    logger.error(f"Error processing document {doc.id}: {e}")
                    continue
            
            if not email_records:
                self.set_message("❌ No valid email records could be extracted")
                return
            
            # Generate collection identifiers
            collection_id = str(uuid.uuid4())[:8]
            safe_collection_name = re.sub(r'[^a-zA-Z0-9_-]', '_', collection_name)[:30]
            display_name = collection_name
            
            logger.info(f"Processing {len(email_records)} emails into chunks")
            
            self.set_progress(50)
            self.set_message(f"📦 Creating chunked database...")
            
            # Create metadata database and content chunks
            db_path, manifest_path, chunk_files = self.create_chunked_storage(
                email_records, collection_id, safe_collection_name, display_name
            )
            
            self.set_progress(85)
            self.set_message("🚀 Deploying to GitHub Pages...")
            
            # Deploy to GitHub
            if not self.timed_out:
                deployed_url = self.deploy_chunked_collection(
                    db_path, manifest_path, chunk_files, 
                    collection_id, safe_collection_name, len(email_records)
                )
                
                self.set_progress(95)
                
                # Upload metadata database for user download
                try:
                    with open(db_path, 'rb') as f:
                        self.upload_file(f)
                    logger.info(f"Uploaded metadata database")
                except Exception as e:
                    logger.error(f"Failed to upload database: {e}")
                
                if deployed_url:
                    self.set_progress(100)
                    self.set_message(f"✅ Open Inbox ready! View at: {deployed_url}")
                    
                    # Send notification
                    email_subject = f"Open Inbox Collection Ready: {collection_name}"
                    email_body = f"""Your email collection '{collection_name}' has been created!
                    
📧 {len(email_records)} emails processed
🗂️ {len(chunk_files)} content chunks created
🌐 View online: {deployed_url}

The collection uses progressive loading for optimal performance with large datasets.
You can browse, search, and explore emails instantly while content loads on-demand.

Generated by Open Inbox DocumentCloud Add-On"""
                    
                    self.send_mail(email_subject, email_body)
                else:
                    self.set_message("❌ Deployment failed. Database available for download.")
                    
        except Exception as e:
            logger.error(f"Add-On execution failed: {e}")
            self.set_message(f"❌ Error: {str(e)}")
    
    def create_chunked_storage(
        self, 
        email_records: List[EmailRecord],
        collection_id: str,
        safe_collection_name: str,
        display_name: str
    ) -> Tuple[str, str, List[str]]:
        """Create metadata database and content chunks"""
        
        # Sort emails by date (newest first)
        email_records.sort(key=lambda x: x.date_sent or datetime.min, reverse=True)
        
        # Paths
        db_name = f"{collection_id}_{safe_collection_name}_metadata.db"
        manifest_name = f"{collection_id}_{safe_collection_name}_manifest.json"
        
        # Create metadata database
        logger.info("Creating metadata database...")
        db_path = self.create_metadata_database(
            email_records, db_name, collection_id, display_name
        )
        
        # Create content chunks
        logger.info("Creating content chunks...")
        chunk_files = self.create_content_chunks(
            email_records, collection_id, safe_collection_name
        )
        
        # Create manifest
        logger.info("Creating manifest...")
        manifest_path = self.create_manifest(
            collection_id, safe_collection_name, display_name,
            len(email_records), chunk_files
        )
        
        return db_path, manifest_path, chunk_files
    
    def create_metadata_database(
        self,
        email_records: List[EmailRecord],
        db_name: str,
        collection_id: str,
        display_name: str
    ) -> str:
        """Create lightweight metadata database with FTS5"""
        
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                email_id INTEGER PRIMARY KEY,
                document_id TEXT UNIQUE NOT NULL,
                sender_email TEXT NOT NULL,
                sender_name TEXT,
                recipient_email TEXT NOT NULL,
                recipient_name TEXT,
                subject TEXT NOT NULL,
                preview TEXT,
                date_sent TEXT,
                chunk_id INTEGER NOT NULL,
                FOREIGN KEY (chunk_id) REFERENCES chunks(chunk_id)
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chunks (
                chunk_id INTEGER PRIMARY KEY,
                start_email_id INTEGER,
                end_email_id INTEGER,
                storage_location TEXT,
                file_path TEXT
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collection_info (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                record_count INTEGER DEFAULT 0
            )
        """)
        
        # FTS5 for search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS email_search USING fts5(
                email_id UNINDEXED,
                sender_name,
                sender_email,
                recipient_name,
                recipient_email,
                subject,
                preview,
                content='emails',
                content_rowid='email_id'
            )
        """)
        
        # Insert collection info
        cursor.execute("""
            INSERT INTO collection_info (id, name, display_name, record_count)
            VALUES (?, ?, ?, ?)
        """, (collection_id, collection_id + "_" + display_name, display_name, len(email_records)))
        
        # Calculate chunks
        num_chunks = (len(email_records) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        # Insert chunk info
        for i in range(num_chunks):
            start_idx = i * CHUNK_SIZE
            end_idx = min((i + 1) * CHUNK_SIZE - 1, len(email_records) - 1)
            
            cursor.execute("""
                INSERT INTO chunks (chunk_id, start_email_id, end_email_id, storage_location, file_path)
                VALUES (?, ?, ?, ?, ?)
            """, (
                i, 
                start_idx + 1, 
                end_idx + 1,
                'repo',
                f"content/{collection_id}_{display_name}/chunk-{i:04d}.json"
            ))
        
        # Insert email metadata
        for idx, record in enumerate(email_records):
            email_id = idx + 1
            chunk_id = idx // CHUNK_SIZE
            
            cursor.execute("""
                INSERT INTO emails (
                    email_id, document_id, sender_email, sender_name,
                    recipient_email, recipient_name, subject, preview, 
                    date_sent, chunk_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email_id,
                record.document_id,
                record.sender_email,
                record.sender_name,
                record.recipient_email,
                record.recipient_name,
                record.subject,
                record.preview,
                record.date_sent.isoformat() if record.date_sent else None,
                chunk_id
            ))
            
            # Add to FTS index
            cursor.execute("""
                INSERT INTO email_search (
                    email_id, sender_name, sender_email, 
                    recipient_name, recipient_email, subject, preview
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                email_id,
                record.sender_name,
                record.sender_email,
                record.recipient_name,
                record.recipient_email,
                record.subject,
                record.preview
            ))
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_date ON emails(date_sent DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_chunk ON emails(chunk_id)")
        
        conn.commit()
        conn.close()
        
        # Validate size
        size = os.path.getsize(db_name)
        logger.info(f"Metadata database created: {db_name} ({size:,} bytes)")
        
        return db_name
    
    def create_content_chunks(
        self,
        email_records: List[EmailRecord],
        collection_id: str,
        safe_collection_name: str
    ) -> List[str]:
        """Create compressed JSON chunks with full email content"""
        
        chunk_files = []
        num_chunks = (len(email_records) + CHUNK_SIZE - 1) // CHUNK_SIZE
        
        os.makedirs(f"content/{collection_id}_{safe_collection_name}", exist_ok=True)
        
        for chunk_idx in range(num_chunks):
            start_idx = chunk_idx * CHUNK_SIZE
            end_idx = min(start_idx + CHUNK_SIZE, len(email_records))
            chunk_records = email_records[start_idx:end_idx]
            
            # Create chunk data
            chunk_data = {}
            for idx, record in enumerate(chunk_records, start=start_idx + 1):
                chunk_data[record.document_id] = {
                    'email_id': idx,
                    'body': record.body[:MAX_BODY_LENGTH],
                    'full_text': record.full_text,
                    'source': record.source,
                    'document_url': record.document_url,
                    'page_count': record.page_count,
                    'file_type': record.file_type,
                    'tags': record.tags
                }
            
            # Write uncompressed chunk for GitHub Pages compatibility
            chunk_filename = f"content/{collection_id}_{safe_collection_name}/chunk-{chunk_idx:04d}.json"
            
            with open(chunk_filename, 'w', encoding='utf-8') as f:
                json.dump(chunk_data, f, separators=(',', ':'))
            
            chunk_files.append(chunk_filename)
            
            # Log chunk info
            size = os.path.getsize(chunk_filename)
            logger.info(f"Created chunk {chunk_idx}: {chunk_filename} ({size:,} bytes)")
        
        return chunk_files
    
    def create_manifest(
        self,
        collection_id: str,
        safe_collection_name: str,
        display_name: str,
        total_emails: int,
        chunk_files: List[str]
    ) -> str:
        """Create manifest file describing the collection structure"""
        
        manifest = {
            'collection_id': collection_id,
            'collection_name': safe_collection_name,
            'display_name': display_name,
            'total_emails': total_emails,
            'chunk_size': CHUNK_SIZE,
            'created_at': datetime.utcnow().isoformat() + 'Z',
            'chunks': []
        }
        
        for idx, chunk_file in enumerate(chunk_files):
            start_email_id = idx * CHUNK_SIZE + 1
            end_email_id = min((idx + 1) * CHUNK_SIZE, total_emails)
            
            manifest['chunks'].append({
                'chunk_id': idx,
                'start_email_id': start_email_id,
                'end_email_id': end_email_id,
                'storage': 'repo',
                'path': chunk_file,
                'size_bytes': os.path.getsize(chunk_file)
            })
        
        manifest_path = f"{collection_id}_{safe_collection_name}_manifest.json"
        
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        logger.info(f"Created manifest: {manifest_path}")
        return manifest_path
    
    def deploy_chunked_collection(
        self,
        db_path: str,
        manifest_path: str,
        chunk_files: List[str],
        collection_id: str,
        safe_collection_name: str,
        email_count: int
    ) -> Optional[str]:
        """Deploy chunked collection to GitHub"""
        
        try:
            github_repo = os.getenv('GITHUB_REPOSITORY')
            github_token = os.getenv('TOKEN') or os.getenv('GITHUB_TOKEN')
            
            if not github_repo or not github_token:
                logger.error("GitHub credentials not available")
                return None
            
            from github import Github
            g = Github(github_token)
            repo = g.get_repo(github_repo)
            
            # Commit metadata database
            with open(db_path, 'rb') as f:
                content = f.read()
            
            repo.create_file(
                f"databases/{os.path.basename(db_path)}",
                f"Add metadata database for {safe_collection_name}",
                content
            )
            
            # Commit manifest
            with open(manifest_path, 'r') as f:
                content = f.read()
            
            repo.create_file(
                f"databases/{collection_id}_{safe_collection_name}/manifest.json",
                f"Add manifest for {safe_collection_name}",
                content
            )
            
            # Commit chunks (check size limits)
            for chunk_file in chunk_files:
                with open(chunk_file, 'rb') as f:
                    content = f.read()
                
                # GitHub API limit: 25MB
                if len(content) < 20 * 1024 * 1024:
                    repo.create_file(
                        chunk_file,
                        f"Add content chunk for {safe_collection_name}",
                        content
                    )
                else:
                    logger.warning(f"Chunk too large for GitHub API: {chunk_file}")
            
            # Generate URL
            username, repo_name = github_repo.split('/')
            pages_url = f"https://{username}.github.io/{repo_name}/?collection={collection_id}_{safe_collection_name}"
            
            logger.info(f"Deployed collection to: {pages_url}")
            return pages_url
            
        except Exception as e:
            logger.error(f"Deployment failed: {e}")
            return None
    
    # Include all existing extraction methods from original main.py
    def get_documents(self) -> List[Any]:
        """Get documents to process"""
        if self.documents:
            documents = []
            for item in self.documents:
                if isinstance(item, (int, str)):
                    try:
                        doc = self.client.documents.get(item)
                        documents.append(doc)
                    except Exception as e:
                        logger.error(f"Failed to fetch document {item}: {e}")
                else:
                    documents.append(item)
            return documents
        elif self.query:
            return list(self.client.documents.search(self.query))
        else:
            return []
    
    def extract_email_record(self, doc: Any, date_format: str) -> Optional[EmailRecord]:
        """Extract email-like data from a DocumentCloud document"""
        try:
            # Get document text
            try:
                doc_text = doc.full_text or ""
            except:
                doc_text = ""
            
            if not doc_text.strip():
                logger.warning(f"Document {doc.id} has no text content")
                doc_text = f"[Document {doc.id} - {doc.title}]\n\nNo text content available."
            
            # Extract metadata from tags
            tags_dict = {}
            if hasattr(doc, 'data') and doc.data:
                if hasattr(doc.data, 'get'):
                    data_obj = doc.data
                elif hasattr(doc.data, '__dict__'):
                    data_obj = doc.data.__dict__
                else:
                    data_obj = {}
                
                for key, values in data_obj.items():
                    if isinstance(values, list) and values:
                        tags_dict[key.lower().strip('_')] = values[0]
                    elif isinstance(values, str):
                        tags_dict[key.lower().strip('_')] = values
            
            # Extract metadata (using existing methods)
            sender_email, sender_name = self.extract_person_info(tags_dict, ['from', 'sender', 'author'])
            recipient_email, recipient_name = self.extract_person_info(tags_dict, ['to', 'recipient', 'addressee'])
            subject = self.extract_tag_value(tags_dict, ['subject', 'title', 'topic'])
            date_sent = self.extract_date(tags_dict, date_format, ['docdate', 'date', 'sent', 'created', 'timestamp'])
            
            # Regex fallback if no metadata in tags
            if not any([sender_email, recipient_email, subject, date_sent]):
                regex_metadata = self.extract_email_metadata_from_text(doc_text)
                
                if not sender_email and 'from' in regex_metadata:
                    sender_email, sender_name = self.parse_person_string(regex_metadata['from'])
                if not recipient_email and 'to' in regex_metadata:
                    recipient_email, recipient_name = self.parse_person_string(regex_metadata['to'])
                if not subject and 'subject' in regex_metadata:
                    subject = regex_metadata['subject']
                if not date_sent and 'date' in regex_metadata:
                    date_sent = self.parse_date_string(regex_metadata['date'], date_format)
            
            # Final fallbacks
            subject = subject or doc.title or f"Document {doc.id}"
            date_sent = date_sent or doc.created_at
            
            # Generate preview
            preview = self.generate_preview(doc_text, MAX_PREVIEW_LENGTH)
            
            # Prepare body and search text
            body_text = doc_text[:MAX_BODY_LENGTH]
            if len(doc_text) > MAX_BODY_LENGTH:
                body_text += f"\n\n[Truncated. View full: https://www.documentcloud.org/documents/{doc.id}]"
            
            return EmailRecord(
                document_id=f"DC_{doc.id}",
                sender_email=sender_email or "unknown@documentcloud.org",
                sender_name=sender_name or "Unknown Sender",
                recipient_email=recipient_email or "unknown@documentcloud.org",
                recipient_name=recipient_name or "Unknown Recipient",
                subject=subject,
                body=body_text,
                full_text=doc_text[:100000],  # Search text limit
                preview=preview,
                date_sent=date_sent,
                source=f"DocumentCloud - {doc.source}" if hasattr(doc, 'source') else "DocumentCloud",
                document_url=f"https://www.documentcloud.org/documents/{doc.id}",
                page_count=getattr(doc, 'page_count', 0),
                file_type=getattr(doc, 'file_type', 'unknown'),
                tags=list(tags_dict.values())
            )
            
        except Exception as e:
            logger.error(f"Error extracting email record from document {doc.id}: {e}")
            return None
    
    # Include all helper methods from original main.py
    def extract_person_info(self, tags_dict: Dict[str, str], field_names: List[str]) -> tuple[str, str]:
        """Extract email and name from tags for a person field"""
        for field in field_names:
            if field in tags_dict:
                value = tags_dict[field]
                email, name = self.parse_person_string(value)
                if email or name:
                    return email, name
        return None, None
    
    def parse_person_string(self, person_str: str) -> tuple[str, str]:
        """Parse a person string that might contain name and/or email"""
        if not person_str:
            return None, None
        
        match = re.match(r'^(.*?)\s*<([^>]+@[^>]+)>$', person_str.strip())
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return email, name
        
        if '@' in person_str:
            email = person_str.strip()
            name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            return email, name
        
        return None, person_str.strip()
    
    def extract_tag_value(self, tags_dict: Dict[str, str], field_names: List[str]) -> Optional[str]:
        """Extract a simple tag value by field names"""
        for field in field_names:
            if field in tags_dict:
                return tags_dict[field]
        return None
    
    def extract_date(self, tags_dict: Dict[str, str], date_format: str, field_names: List[str] = None) -> Optional[datetime]:
        """Extract and parse date from tags"""
        date_fields = field_names or ['date', 'sent', 'created', 'timestamp']
        
        for field in date_fields:
            if field in tags_dict:
                date_str = tags_dict[field]
                parsed_date = self.parse_date_string(date_str, date_format)
                if parsed_date:
                    return parsed_date
        return None
    
    def parse_date_string(self, date_str: str, format_hint: str) -> Optional[datetime]:
        """Parse date string using various formats"""
        if not date_str:
            return None
        
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S',
            '%A, %B %d, %Y %I:%M %p',
            '%A, %B %d, %Y %I:%M:%S %p',
            '%A, %b %d, %Y %I:%M %p',
            '%B %d, %Y %I:%M %p',
            '%b %d, %Y %I:%M %p',
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M',
            '%m/%d/%Y',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y'
        ]
        
        if format_hint != 'auto':
            try:
                return datetime.strptime(date_str, format_hint)
            except:
                pass
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
        
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    def extract_email_metadata_from_text(self, doc_text: str) -> Dict[str, str]:
        """Extract email metadata using regex patterns"""
        metadata = {}
        header_text = doc_text[:2000]
        
        from_match = self.extract_from_field(header_text)
        if from_match:
            metadata['from'] = from_match
        
        to_match = self.extract_to_field(header_text)
        if to_match:
            metadata['to'] = to_match
        
        subject_match = self.extract_subject_field(header_text)
        if subject_match:
            metadata['subject'] = subject_match
        
        date_match = self.extract_date_field(header_text)
        if date_match:
            metadata['date'] = date_match
        
        return metadata
    
    def extract_from_field(self, text: str) -> Optional[str]:
        """Extract sender information using regex"""
        patterns = [
            r'From:\s*([^\r\n]+)',
            r'FROM:\s*([^\r\n]+)',
            r'Sender:\s*([^\r\n]+)',
            r'From\s+([^\r\n]+@[^\r\n\s]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_to_field(self, text: str) -> Optional[str]:
        """Extract recipient information using regex"""
        patterns = [
            r'To:\s*([^\r\n]+)',
            r'TO:\s*([^\r\n]+)',
            r'Recipient:\s*([^\r\n]+)',
            r'To\s+([^\r\n]+@[^\r\n\s]+)',
            r'Cc:\s*([^\r\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                result = match.group(1).strip()
                if ';' in result:
                    result = result.split(';')[0].strip()
                return result
        return None
    
    def extract_subject_field(self, text: str) -> Optional[str]:
        """Extract subject using regex"""
        patterns = [
            r'Subject:\s*([^\r\n]+)',
            r'SUBJECT:\s*([^\r\n]+)',
            r'Re:\s*([^\r\n]+)',
            r'Subj:\s*([^\r\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_date_field(self, text: str) -> Optional[str]:
        """Extract date using regex"""
        patterns = [
            r'Sent:\s*([^\r\n]+)',
            r'Date:\s*([^\r\n]+)',
            r'SENT:\s*([^\r\n]+)',
            r'DATE:\s*([^\r\n]+)',
            r'Received:\s*([^\r\n]+)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def generate_preview(self, text: str, max_length: int = 200) -> str:
        """Generate a preview of the email content"""
        if not text:
            return ""
        
        clean_text = ' '.join(text.strip().split())
        
        if len(clean_text) <= max_length:
            return clean_text
        
        preview = clean_text[:max_length]
        last_period = preview.rfind('.')
        last_space = preview.rfind(' ')
        
        if last_period > max_length - 30:
            preview = preview[:last_period + 1]
        elif last_space > max_length - 20:
            preview = preview[:last_space] + "..."
        else:
            preview = preview + "..."
        
        return preview


if __name__ == "__main__":
    ChunkedOpenInbox().main()