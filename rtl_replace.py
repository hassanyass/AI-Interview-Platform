import os
import re

directory = r'C:\Users\hassa\Documents\AI-Interview-Platform\frontend\src'

def replace_classes(content):
    # Word boundary \b is important to not match 'example-l'
    # but hyphen in class names makes \b tricky.
    
    # We will use regex to find class names starting with these prefixes inside className strings.
    # Actually, a simpler regex for Tailwind classes:
    content = re.sub(r'\bml-(\d+)', r'ms-\1', content)
    content = re.sub(r'\bmr-(\d+)', r'me-\1', content)
    content = re.sub(r'\bpl-(\d+)', r'ps-\1', content)
    content = re.sub(r'\bpr-(\d+)', r'pe-\1', content)
    content = re.sub(r'\bborder-l\b', r'border-s', content)
    content = re.sub(r'\bborder-r\b', r'border-e', content)
    content = re.sub(r'\bborder-l-(\d+)', r'border-s-\1', content)
    content = re.sub(r'\bborder-r-(\d+)', r'border-e-\1', content)
    content = re.sub(r'\bspace-x-(\d+)', r'gap-\1', content)
    content = re.sub(r'\bleft-(\d+)', r'start-\1', content)
    content = re.sub(r'\bright-(\d+)', r'end-\1', content)
    content = re.sub(r'\btext-left\b', r'text-start', content)
    content = re.sub(r'\btext-right\b', r'text-end', content)
    return content

for root, _, files in os.walk(directory):
    for file in files:
        if file.endswith('.tsx'):
            path = os.path.join(root, file)
            with open(path, 'r', encoding='utf-8') as f:
                content = f.read()
            new_content = replace_classes(content)
            if new_content != content:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"Updated {file}")
