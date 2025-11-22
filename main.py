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
    full_text: str  # Full document text for search
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
            
            logger.info(f"Generated collection_id: {collection_id}")
            logger.info(f"Original collection_name: '{collection_name}'")
            logger.info(f"Safe collection_name: '{safe_collection_name}'")
            logger.info(f"Final database_name: '{database_name}'")
                
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
            
            # Extract sender information from tags
            sender_email, sender_name = self.extract_person_info(tags_dict, ['from', 'sender', 'author'])
            
            # Extract recipient information from tags
            recipient_email, recipient_name = self.extract_person_info(tags_dict, ['to', 'recipient', 'addressee'])
            
            # Extract subject from tags
            subject = self.extract_tag_value(tags_dict, ['subject', 'title', 'topic'])
            
            # Extract date from tags
            date_sent = self.extract_date(tags_dict, date_format, ['docdate', 'date', 'sent', 'created', 'timestamp'])
            
            # If no metadata found in tags, try regex extraction from document text
            if not any([sender_email, recipient_email, subject, date_sent]):
                logger.info(f"No metadata in tags for document {doc.id}, trying regex extraction")
                regex_metadata = self.extract_email_metadata_from_text(doc_text)
                
                # Use regex results as fallback
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
            preview = self.generate_preview(doc_text)
            
            # Truncate body text to reasonable email size (5KB) for storage efficiency
            # Full text is still available for search via FTS table
            body_text = doc_text[:5000] if len(doc_text) > 5000 else doc_text
            if len(doc_text) > 5000:
                body_text += f"\n\n[Document truncated. Full text available at: https://www.documentcloud.org/documents/{doc.id}]"
            
            return EmailRecord(
                document_id=f"DC_{doc.id}",
                sender_email=sender_email or "unknown@documentcloud.org",
                sender_name=sender_name or "Unknown Sender", 
                recipient_email=recipient_email or "unknown@documentcloud.org",
                recipient_name=recipient_name or "Unknown Recipient",
                subject=subject,
                body=body_text,
                full_text=doc_text,  # Keep full text for search
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
            # ISO formats
            '%Y-%m-%dT%H:%M:%S.%fZ',  # ISO format with milliseconds: 2009-05-02T04:00:00.000Z
            '%Y-%m-%dT%H:%M:%SZ',     # ISO format: 2009-05-02T04:00:00Z
            '%Y-%m-%dT%H:%M:%S',      # ISO format without Z
            
            # Email-specific formats from samples
            '%A, %B %d, %Y %I:%M %p',    # Sunday, November 14, 2004 8:54 PM
            '%A, %B %d, %Y %I:%M:%S %p', # Sunday, November 14, 2004 8:54:32 PM
            '%A, %b %d, %Y %I:%M %p',    # Sun, Nov 14, 2004 8:54 PM
            '%B %d, %Y %I:%M %p',        # November 14, 2004 8:54 PM
            '%b %d, %Y %I:%M %p',        # Nov 14, 2004 8:54 PM
            
            # Standard formats
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
            '%d-%m-%Y'
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
    
    def extract_email_metadata_from_text(self, doc_text: str) -> Dict[str, str]:
        """Extract email metadata using regex patterns when tags are not available"""
        metadata = {}
        
        # Get first part of document (email headers are usually at the top)
        header_text = doc_text[:2000]  # First 2000 characters
        
        # Extract From field
        from_match = self.extract_from_field(header_text)
        if from_match:
            metadata['from'] = from_match
            
        # Extract To field  
        to_match = self.extract_to_field(header_text)
        if to_match:
            metadata['to'] = to_match
            
        # Extract Subject field
        subject_match = self.extract_subject_field(header_text)
        if subject_match:
            metadata['subject'] = subject_match
            
        # Extract Date field
        date_match = self.extract_date_field(header_text)
        if date_match:
            metadata['date'] = date_match
            
        return metadata
    
    def extract_from_field(self, text: str) -> Optional[str]:
        """Extract sender information using regex"""
        patterns = [
            r'From:\s*([^\r\n]+)',           # From: sender@example.com
            r'FROM:\s*([^\r\n]+)',           # FROM: (case insensitive)
            r'Sender:\s*([^\r\n]+)',         # Sender: alternative
            r'From\s+([^\r\n]+@[^\r\n\s]+)', # From email@domain.com (no colon)
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_to_field(self, text: str) -> Optional[str]:
        """Extract recipient information using regex"""
        patterns = [
            r'To:\s*([^\r\n]+)',             # To: recipient@example.com
            r'TO:\s*([^\r\n]+)',             # TO: (case insensitive)  
            r'Recipient:\s*([^\r\n]+)',      # Recipient: alternative
            r'To\s+([^\r\n]+@[^\r\n\s]+)',   # To email@domain.com (no colon)
            r'Cc:\s*([^\r\n]+)',             # Cc: alternative recipients
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                # Clean up common artifacts
                result = match.group(1).strip()
                # Handle semicolon-separated multiple recipients
                if ';' in result:
                    result = result.split(';')[0].strip()
                return result
        return None
    
    def extract_subject_field(self, text: str) -> Optional[str]:
        """Extract subject using regex"""
        patterns = [
            r'Subject:\s*([^\r\n]+)',        # Subject: Email subject
            r'SUBJECT:\s*([^\r\n]+)',        # SUBJECT: (case insensitive)
            r'Re:\s*([^\r\n]+)',             # Re: (reply indicator)
            r'Subj:\s*([^\r\n]+)',           # Subj: abbreviation
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
        return None
    
    def extract_date_field(self, text: str) -> Optional[str]:
        """Extract date using regex"""
        patterns = [
            r'Sent:\s*([^\r\n]+)',           # Sent: Monday, January 1, 2007 11:31 AM
            r'Date:\s*([^\r\n]+)',           # Date: standard email header
            r'SENT:\s*([^\r\n]+)',           # SENT: (case insensitive)
            r'DATE:\s*([^\r\n]+)',           # DATE: (case insensitive)
            r'Received:\s*([^\r\n]+)',       # Received: alternative
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text, re.MULTILINE | re.IGNORECASE)
            if match:
                return match.group(1).strip()
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
            
            # Add to FTS - use full_text for comprehensive search
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
                record.full_text  # Use full document text for search
            ))
        
        conn.commit()
        conn.close()
        
        # Validate the created database
        try:
            with open(db_path, 'rb') as f:
                db_content = f.read()
            logger.info(f"Created database {db_path} with {len(email_records)} records, size: {len(db_content)} bytes")
            
            # Quick validation
            if not db_content.startswith(b'SQLite format 3'):
                logger.error(f"Created database has invalid SQLite header!")
            else:
                logger.info("Database header validation passed")
                
        except Exception as e:
            logger.error(f"Error validating created database: {e}")
        
        return db_path
    
    def deploy_to_github(self, db_path: str, database_name: str, collection_id: str, safe_collection_name: str) -> Optional[str]:
        """Deploy database to same GitHub repository using GitHub API"""
        try:
            # Get repository info from GitHub environment
            github_repo = os.getenv('GITHUB_REPOSITORY')
            github_token = os.getenv('TOKEN') or os.getenv('GITHUB_TOKEN')
            
            if not github_repo:
                logger.error("GITHUB_REPOSITORY environment variable not set")
                return None
                
            if not github_token:
                logger.warning("GITHUB_TOKEN not available, skipping commit to repository")
                # Still return URL for user even if can't commit
                username, repo_name = github_repo.split('/')
                return f"https://{username}.github.io/{repo_name}/?emails={collection_id}_{safe_collection_name}"
            
            # Use GitHub API to commit the file
            logger.info(f"Attempting to commit {database_name} to {github_repo}")
            success = self._commit_via_github_api(
                db_path, 
                database_name, 
                safe_collection_name, 
                github_repo, 
                github_token
            )
            
            # Generate GitHub Pages URL
            username, repo_name = github_repo.split('/')
            pages_url = f"https://{username}.github.io/{repo_name}/?emails={collection_id}_{safe_collection_name}"
            
            if success:
                logger.info(f"Successfully committed to repository: {database_name}")
            else:
                logger.warning(f"Could not commit to repository, but database created: {database_name}")
            
            logger.info(f"Collection available at: {pages_url}")
            return pages_url
            
        except Exception as e:
            logger.error(f"GitHub deployment failed: {e}")
            return None
    
    def _commit_via_github_api(self, db_path: str, database_name: str, collection_name: str, 
                              github_repo: str, github_token: str) -> bool:
        """Commit database file via GitHub API"""
        try:
            from github import Github
            
            logger.info(f"Initializing GitHub client for repository: {github_repo}")
            
            # Initialize GitHub client
            g = Github(github_token)
            repo = g.get_repo(github_repo)
            
            logger.info(f"Reading database file: {db_path}")
            
            # Read and validate database file
            with open(db_path, 'rb') as f:
                content = f.read()
            
            logger.info(f"Database file size: {len(content)} bytes")
            
            # Validate it's a proper SQLite database
            if not content.startswith(b'SQLite format 3'):
                logger.error("Database file does not have valid SQLite header!")
                return False
            
            # Test that the database can be opened
            try:
                test_conn = sqlite3.connect(db_path)
                test_cursor = test_conn.cursor()
                test_cursor.execute("SELECT COUNT(*) FROM emails")
                count = test_cursor.fetchone()[0]
                test_conn.close()
                logger.info(f"Database validation successful: {count} emails")
            except Exception as e:
                logger.error(f"Database validation failed: {e}")
                return False
            
            # Check file size limit (GitHub API limit is 100MB, but we should be conservative)  
            if len(content) > 95 * 1024 * 1024:  # 95MB limit (close to GitHub's 100MB)
                logger.error(f"Database file too large for GitHub API: {len(content)} bytes")
                return False
            
            # PyGithub will handle base64 encoding automatically for binary content
            logger.info(f"Using raw binary content: {len(content)} bytes")
            
            # File path in repository
            file_path = f"collections/{database_name}"
            commit_message = f"Add email collection: {collection_name}\n\n🤖 Generated by Open Inbox DocumentCloud Add-On"
            
            logger.info(f"Committing to path: {file_path}")
            
            try:
                # Try to update existing file
                logger.info("Checking if file already exists...")
                file = repo.get_contents(file_path)
                logger.info("File exists, updating...")
                repo.update_file(
                    file_path,
                    commit_message,
                    content,  # Use raw bytes, not base64
                    file.sha
                )
                logger.info(f"Updated existing file: {file_path}")
            except Exception as e:
                # File doesn't exist, create it
                logger.info(f"File doesn't exist (error: {e}), creating new file...")
                
                # Create file - PyGithub handles binary encoding automatically
                result = repo.create_file(
                    file_path,
                    commit_message,
                    content  # Use raw bytes, PyGithub will handle base64 encoding
                )
                logger.info(f"Created new file: {file_path}")
            
            # Verify the committed file
            try:
                committed_file = repo.get_contents(file_path)
                logger.info(f"Verification: Committed file size: {committed_file.size} bytes")
                if committed_file.size != len(content):
                    logger.warning(f"Size mismatch! Original: {len(content)}, Committed: {committed_file.size}")
            except Exception as e:
                logger.warning(f"Could not verify committed file: {e}")
            
            return True
            
        except Exception as e:
            logger.error(f"GitHub API commit failed: {e}")
            import traceback
            logger.error(f"Full traceback: {traceback.format_exc()}")
            return False
    


if __name__ == "__main__":
    OpenInbox().main()