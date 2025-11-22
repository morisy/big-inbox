#!/usr/bin/env python3
"""
Debug script to analyze database size breakdown
"""
import sqlite3
import json
import os

def analyze_db_size(db_path):
    """Analyze what's taking up space in the database"""
    if not os.path.exists(db_path):
        print(f"Database {db_path} not found")
        return
        
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Get overall file size
    file_size = os.path.getsize(db_path)
    print(f"Total database file size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
    print()
    
    # Check table sizes
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for (table_name,) in tables:
        try:
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            count = cursor.fetchone()[0]
            print(f"Table '{table_name}': {count} rows")
            
            if table_name == 'emails':
                # Analyze email record sizes
                cursor.execute("SELECT body, preview, metadata, subject FROM emails LIMIT 3")
                for i, (body, preview, metadata, subject) in enumerate(cursor.fetchall()):
                    print(f"  Email {i+1}:")
                    print(f"    Subject: {len(subject) if subject else 0} chars")
                    print(f"    Body: {len(body) if body else 0} chars") 
                    print(f"    Preview: {len(preview) if preview else 0} chars")
                    print(f"    Metadata: {len(metadata) if metadata else 0} chars")
                    if metadata:
                        try:
                            meta_obj = json.loads(metadata)
                            print(f"    Metadata content: {list(meta_obj.keys())}")
                        except:
                            pass
                    
            elif table_name == 'email_search':
                # Analyze FTS table sizes
                cursor.execute("SELECT body FROM email_search LIMIT 3")
                for i, (body,) in enumerate(cursor.fetchall()):
                    print(f"  FTS record {i+1}: {len(body) if body else 0} chars")
                    
        except Exception as e:
            print(f"Error analyzing {table_name}: {e}")
    
    # Check for any large columns
    print("\nLarge text analysis:")
    try:
        cursor.execute("SELECT MAX(LENGTH(body)), AVG(LENGTH(body)) FROM emails")
        max_body, avg_body = cursor.fetchone()
        print(f"Email body - Max: {max_body}, Avg: {avg_body:.0f}")
        
        cursor.execute("SELECT MAX(LENGTH(body)), AVG(LENGTH(body)) FROM email_search")
        max_search, avg_search = cursor.fetchone()
        print(f"Search text - Max: {max_search}, Avg: {avg_search:.0f}")
    except Exception as e:
        print(f"Error analyzing text sizes: {e}")
    
    conn.close()

# Look for any existing database files
if __name__ == "__main__":
    # Check if there are any .db files in current directory
    db_files = [f for f in os.listdir('.') if f.endswith('.db')]
    if db_files:
        print("Found database files:")
        for db_file in db_files:
            print(f"  {db_file}")
            analyze_db_size(db_file)
            print("-" * 50)
    else:
        print("No database files found in current directory")