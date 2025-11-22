#!/usr/bin/env python3
"""
Test script for regex email extraction
"""
import os
import sys
sys.path.append('.')
from main import OpenInbox

def test_regex_extraction():
    """Test regex extraction on sample emails"""
    addon = OpenInbox()
    
    sample_dir = "sample_emails"
    if not os.path.exists(sample_dir):
        print(f"Sample directory {sample_dir} not found")
        return
    
    # Test with a few sample files
    test_files = [
        "2006c_Jul-Sept_GovernF-COMPLIMENTS.txt",
        "2006d_Oct-Dec_GovernF-Analysts-Lauren-Boot camp issue-answered_bc.txt", 
        "2006c_Jul-Sept_GovernF-Forwarded.txt",
        "2006c_Jul-Sept_GovernF-Daily OPB Forwards.txt"
    ]
    
    for filename in test_files:
        filepath = os.path.join(sample_dir, filename)
        if not os.path.exists(filepath):
            print(f"File not found: {filepath}")
            continue
            
        print(f"\n=== Testing {filename} ===")
        
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            text = f.read()
        
        # Test regex extraction
        metadata = addon.extract_email_metadata_from_text(text)
        
        print(f"Extracted metadata:")
        for key, value in metadata.items():
            print(f"  {key}: {value}")
        
        # Test individual field extractions
        print(f"\nIndividual field tests:")
        print(f"  From: {addon.extract_from_field(text)}")
        print(f"  To: {addon.extract_to_field(text)}")
        print(f"  Subject: {addon.extract_subject_field(text)}")
        print(f"  Date: {addon.extract_date_field(text)}")
        
        # Test parsing person strings
        if metadata.get('from'):
            email, name = addon.parse_person_string(metadata['from'])
            print(f"  Parsed From - Email: {email}, Name: {name}")
            
        if metadata.get('to'):
            email, name = addon.parse_person_string(metadata['to'])
            print(f"  Parsed To - Email: {email}, Name: {name}")

if __name__ == "__main__":
    test_regex_extraction()