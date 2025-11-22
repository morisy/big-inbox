#!/usr/bin/env python3
"""
Open Inbox - DocumentCloud Add-On

Converts DocumentCloud documents into a browsable email-like interface.
Extracts metadata from document tags and creates a SQLite database 
that can be viewed using the Open Inbox web interface.
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
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from documentcloud.addon import AddOn
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@dataclass
class EmailRecord:
    """Represents an email-like record extracted from a DocumentCloud document"""
    document_id: str
    sender_email: str
    sender_name: str
    recipient_email: str
    recipient_name: str
    subject: str
    body: str
    date_sent: Optional[datetime]
    source: str
    document_url: str
    page_count: int
    file_type: str
    tags: List[str]


class OpenInbox(AddOn):
    """Open Inbox - DocumentCloud Add-On for creating email-like interfaces from documents"""
    
    def main(self):
        """Main Add-On execution"""
        try:
            # Get parameters
            collection_name = self.data.get("collection_name", "").strip()
            date_format = self.data.get("date_format", "auto")
            
            if not collection_name:
                self.set_message("❌ Collection name is required")
                return
                
            self.set_message("🔍 Processing documents...")
            self.set_progress(0)
            
            # Get documents to process
            documents = self.get_documents()
            if not documents:
                self.set_message("❌ No documents found to process")
                return
                
            logger.info(f"Processing {len(documents)} documents")
            self.set_message(f"📄 Found {len(documents)} documents to process")
            
            # Extract email records from documents
            email_records = []
            for i, doc in enumerate(documents):
                try:
                    record = self.extract_email_record(doc, date_format)
                    if record:
                        email_records.append(record)
                    
                    # Update progress (first 60% is document processing)
                    progress = int((i + 1) / len(documents) * 60)
                    self.set_progress(progress)
                    self.set_message(f"📄 Processing documents... ({i+1}/{len(documents)})")
                    
                except Exception as e:
                    logger.error(f"Error processing document {doc.id}: {e}")
                    continue
                    
            if not email_records:
                self.set_message("❌ No valid email records could be extracted")
                return
                
            # Generate database filename with UUID and collection name
            collection_id = str(uuid.uuid4())[:8]  # First 8 chars of UUID
            safe_collection_name = re.sub(r'[^a-zA-Z0-9_-]', '_', collection_name)[:30]
            database_name = f"{collection_id}_{safe_collection_name}.db"
            collection_path = f"collections/{database_name}"
                
            self.set_progress(70)
            self.set_message(f"📦 Creating database: {database_name}")
            
            # Create SQLite database with collection metadata
            db_path = self.create_database(email_records, database_name, collection_name, collection_id)

            self.set_progress(85)
            self.set_message("🚀 Deploying to GitHub Pages...")
            
            # Deploy to GitHub (commit to same repository)
            deployed_url = self.deploy_to_github(db_path, database_name, collection_id, safe_collection_name)
            
            self.set_progress(95)
            
            # Upload database file for user download
            try:
                with open(db_path, 'rb') as f:
                    self.upload_file(f)
                logger.info(f"Uploaded database file: {database_name}")
            except Exception as e:
                logger.error(f"Failed to upload database file: {e}")
            
            if deployed_url:
                self.set_progress(100)
                self.set_message(f"✅ Open Inbox ready! View at: {deployed_url}")
                
                # Send completion notification
                self.send_mail(
                    f"Open Inbox Collection Ready: {collection_name}",
                    f"Your email collection '{collection_name}' has been created!\n\n"
                    f"📧 {len(email_records)} emails processed\n"
                    f"🌐 View online: {deployed_url}\n"
                    f"💾 Database: {database_name}\n\n"
                    f"The collection is now browsable with a Gmail-like interface. "
                    f"You can search, filter by contacts, and explore the email threads.\n\n"
                    f"Generated by Open Inbox DocumentCloud Add-On"
                )
            else:
                self.set_message("❌ Deployment failed. Database available for download.")
                
        except Exception as e:
            logger.error(f"Add-On execution failed: {e}")
            self.set_message(f"❌ Error: {str(e)}")
    
    def get_documents(self) -> List[Any]:
        """Get documents to process (either selected or from query)"""
        if self.documents:
            # Handle both document objects and document IDs
            documents = []
            for item in self.documents:
                if isinstance(item, (int, str)):
                    # It's a document ID, fetch the document
                    try:
                        doc = self.client.documents.get(item)
                        documents.append(doc)
                    except Exception as e:
                        logger.error(f"Failed to fetch document {item}: {e}")
                else:
                    # It's already a document object
                    documents.append(item)
            return documents
        elif self.query:
            # Search for documents matching the query
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
            
            # Extract metadata from DocumentCloud data._tag format
            # Tags are stored as {"_tag": ["important"], "from": ["john@example.com"]} 
            tags_dict = {}
            if hasattr(doc, 'data') and doc.data:
                # Handle both dict-like and object-like data access
                if hasattr(doc.data, 'get'):
                    data_obj = doc.data
                elif hasattr(doc.data, '__dict__'):
                    data_obj = doc.data.__dict__
                else:
                    data_obj = {}
                
                # Process all data keys, not just _tag
                for key, values in data_obj.items():
                    if isinstance(values, list):
                        # Use first value if multiple values exist
                        if values:
                            tags_dict[key.lower().strip('_')] = values[0]
                    elif isinstance(values, str):
                        tags_dict[key.lower().strip('_')] = values
            
            # Extract sender information
            sender_email, sender_name = self.extract_person_info(tags_dict, ['from', 'sender', 'author'])
            
            # Extract recipient information  
            recipient_email, recipient_name = self.extract_person_info(tags_dict, ['to', 'recipient', 'addressee'])
            
            # Extract subject
            subject = self.extract_tag_value(tags_dict, ['subject', 'title', 'topic']) or doc.title or f"Document {doc.id}"
            
            # Extract date (try docDate first, then other date fields)
            date_sent = self.extract_date(tags_dict, date_format, ['docdate', 'date', 'sent', 'created', 'timestamp']) or doc.created_at
            
            # Generate preview
            preview = self.generate_preview(doc_text)
            
            return EmailRecord(
                document_id=f"DC_{doc.id}",
                sender_email=sender_email or "unknown@documentcloud.org",
                sender_name=sender_name or "Unknown Sender", 
                recipient_email=recipient_email or "unknown@documentcloud.org",
                recipient_name=recipient_name or "Unknown Recipient",
                subject=subject,
                body=doc_text,
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
    
    def extract_person_info(self, tags_dict: Dict[str, str], field_names: List[str]) -> tuple[str, str]:
        """Extract email and name from tags for a person field"""
        for field in field_names:
            if field in tags_dict:
                value = tags_dict[field]
                # Try to parse email and name from the tag value
                email, name = self.parse_person_string(value)
                if email or name:
                    return email, name
        return None, None
    
    def parse_person_string(self, person_str: str) -> tuple[str, str]:
        """Parse a person string that might contain name and/or email"""
        if not person_str:
            return None, None
            
        # Pattern for "Name <email@domain.com>"
        match = re.match(r'^(.*?)\s*<([^>]+@[^>]+)>$', person_str.strip())
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return email, name
            
        # Check if it's just an email
        if '@' in person_str:
            email = person_str.strip()
            # Extract name from email prefix
            name = email.split('@')[0].replace('.', ' ').replace('_', ' ').title()
            return email, name
            
        # Just a name
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
            
        # Common date formats to try
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with milliseconds: 2009-05-02T04:00:00.000Z
            '%Y-%m-%dT%H:%M:%SZ',     # ISO format: 2009-05-02T04:00:00Z
            '%Y-%m-%dT%H:%M:%S',      # ISO format without Z
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%Y-%m-%d',
            '%m/%d/%Y %H:%M:%S',
            '%m/%d/%Y %H:%M', 
            '%m/%d/%Y',
            '%d/%m/%Y %H:%M:%S',
            '%d/%m/%Y %H:%M',
            '%d/%m/%Y',
            '%B %d, %Y',
            '%b %d, %Y',
            '%d %B %Y',
            '%d %b %Y',
            '%Y/%m/%d',
            '%m-%d-%Y',
            '%d--%Y'
        ]
        
        # Try the hint format first if provided
        if format_hint != 'auto':
            try:
                return datetime.strptime(date_str, format_hint)
            except:
                pass
        
        # Try common formats
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt)
            except:
                continue
                
        logger.warning(f"Could not parse date: {date_str}")
        return None
    
    def generate_preview(self, text: str, max_length: int = 200) -> str:
        """Generate a preview of the document text"""
        if not text:
            return ""
        
        # Clean up text
        clean_text = ' '.join(text.strip().split())
        
        if len(clean_text) <= max_length:
            return clean_text
            
        # Find a good break point near the limit
        preview = clean_text[:max_length]
        last_space = preview.rfind(' ')
        
        if last_space > max_length - 50:  # If we find a space reasonably close to the end
            preview = preview[:last_space]
            
        return preview + "..."
    
    def create_database(self, email_records: List[EmailRecord], database_name: str, collection_name: str, collection_id: str) -> str:
        """Create SQLite database with email records"""
        db_path = database_name
        
        # Create database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Create schema
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emails (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id TEXT UNIQUE NOT NULL,
                sender_email TEXT,
                sender_name TEXT,
                recipient_email TEXT, 
                recipient_name TEXT,
                subject TEXT,
                body TEXT,
                preview TEXT,
                date_sent DATETIME,
                thread_id TEXT,
                message_id TEXT,
                has_attachments BOOLEAN DEFAULT 0,
                folder TEXT DEFAULT 'inbox',
                source TEXT,
                metadata JSON,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create collection metadata table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS collection_info (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                display_name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                record_count INTEGER DEFAULT 0
            )
        """)
        
        # Insert collection metadata
        cursor.execute("""
            INSERT OR REPLACE INTO collection_info (id, name, display_name, record_count)
            VALUES (?, ?, ?, ?)
        """, (collection_id, collection_name, collection_name.replace('_', ' ').replace('-', ' ').title(), len(email_records)))
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS contacts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                name TEXT,
                display_name TEXT,
                email_count INTEGER DEFAULT 0,
                first_seen DATE,
                last_seen DATE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Create FTS table for search
        cursor.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS email_search USING fts5(
                document_id UNINDEXED,
                sender_name,
                sender_email,
                recipient_name, 
                recipient_email,
                subject,
                body
            )
        """)
        
        # Create indexes
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(sender_email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_recipient_email ON emails(recipient_email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_emails_date_sent ON emails(date_sent)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contacts_email ON contacts(email)")
        
        # Insert email records
        for record in email_records:
            # Generate preview
            preview = self.generate_preview(record.body)
            
            # Create metadata
            metadata = {
                'document_url': record.document_url,
                'page_count': record.page_count,
                'file_type': record.file_type,
                'tags': record.tags
            }
            
            cursor.execute("""
                INSERT OR REPLACE INTO emails (
                    document_id, sender_email, sender_name, recipient_email, recipient_name,
                    subject, body, preview, date_sent, folder, source, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                record.document_id,
                record.sender_email,
                record.sender_name, 
                record.recipient_email,
                record.recipient_name,
                record.subject,
                record.body,
                preview,
                record.date_sent.isoformat() if record.date_sent else None,
                'inbox',
                record.source,
                json.dumps(metadata)
            ))
            
            # Update contacts
            for email, name in [(record.sender_email, record.sender_name), 
                               (record.recipient_email, record.recipient_name)]:
                if email and email != "unknown@documentcloud.org":
                    cursor.execute("""
                        INSERT INTO contacts (email, name, display_name, email_count, first_seen, last_seen)
                        VALUES (?, ?, ?, 1, ?, ?)
                        ON CONFLICT(email) DO UPDATE SET
                            email_count = email_count + 1,
                            last_seen = excluded.last_seen,
                            name = COALESCE(contacts.name, excluded.name)
                    """, (email, name, name or email, record.date_sent, record.date_sent))
            
            # Add to FTS
            cursor.execute("""
                INSERT INTO email_search (
                    document_id, sender_name, sender_email, recipient_name, 
                    recipient_email, subject, body
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                record.document_id,
                record.sender_name,
                record.sender_email,
                record.recipient_name,
                record.recipient_email, 
                record.subject,
                record.body
            ))
        
        conn.commit()
        conn.close()
        
        logger.info(f"Created database {db_path} with {len(email_records)} records")
        return db_path
    
    def deploy_to_github(self, db_path: str, database_name: str, collection_id: str, collection_name: str) -> Optional[str]:
        """Deploy database to same GitHub repository"""
        try:
            # Get repository name from GitHub environment
            github_repo = os.getenv('GITHUB_REPOSITORY')
            if not github_repo:
                logger.error("GITHUB_REPOSITORY environment variable not set")
                return None
            
            # Move database to collections directory
            collections_path = f"collections/{database_name}"
            os.makedirs("collections", exist_ok=True)
            os.rename(db_path, collections_path)
            
            # Git operations to commit new collection
            self._commit_collection(collections_path, collection_name)
            
            # Generate GitHub Pages URL using collection ID and name
            username, repo_name = github_repo.split('/')
            pages_url = f"https://{username}.github.io/{repo_name}/?emails={collection_id}_{collection_name}"
            
            logger.info(f"Deployed successfully: {pages_url}")
            return pages_url
            
        except Exception as e:
            logger.error(f"GitHub deployment failed: {e}")
            return None
    
    def _commit_collection(self, collections_path: str, collection_name: str):
        """Commit new collection to repository"""
        try:
            # Configure git
            os.system('git config user.name "DocumentCloud Add-On"')
            os.system('git config user.email "addon@documentcloud.org"')
            
            # Add and commit new collection
            os.system(f'git add "{collections_path}"')
            commit_message = f"Add email collection: {collection_name}"
            os.system(f'git commit -m "{commit_message}"')
            os.system('git push')
            
            logger.info(f"Committed collection: {collections_path}")
            
        except Exception as e:
            logger.error(f"Git commit failed: {e}")
            raise
    


if __name__ == "__main__":
    OpenInbox().main()