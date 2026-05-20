#!/usr/bin/env python3
"""Convert raw git diff to styled HTML5 page and optionally serve it."""

import sys
import os
import subprocess
from datetime import datetime
from pathlib import Path


def get_git_diff():
    """Get raw git diff from current directory."""
    result = subprocess.run(
        ['git', 'diff'],
        capture_output=True,
        text=True,
        cwd=os.getcwd()
    )
    return result.stdout


def parse_diff(diff_text):
    """Parse git diff text into file sections with stats."""
    files = []
    current_file = None
    current_diff_lines = []
    additions = 0
    deletions = 0
    
    lines = diff_text.split('\n')
    i = 0
    
    while i < len(lines):
        line = lines[i]
        
        if line.startswith('diff --git a/'):
            # Save previous file
            if current_file:
                files.append({
                    'name': current_file,
                    'diff': current_diff_lines,
                    'additions': additions,
                    'deletions': deletions
                })
            
            # Extract filename
            fname = line.replace('diff --git a/', '').replace(' b/', ' → ')
            current_file = fname
            current_diff_lines = [line]
            additions = 0
            deletions = 0
        elif current_file:
            current_diff_lines.append(line)
            if line.startswith('+') and not line.startswith('+++'):
                additions += 1
            elif line.startswith('-') and not line.startswith('---'):
                deletions += 1
        i += 1
    
    # Save last file
    if current_file:
        files.append({
            'name': current_file,
            'diff': current_diff_lines,
            'additions': additions,
            'deletions': deletions
        })
    
    return files


def style_diff_lines(diff_lines):
    """Apply HTML styling to diff lines."""
    styled = []
    
    for line in diff_lines:
        if line.startswith('diff ') or line.startswith('index ') or \
           line.startswith('--- ') or line.startswith('+++ ') or \
           line.startswith('@@ '):
            styled.append(f'<span class="diff-header">{line}</span>')
        elif line.startswith('+'):
            styled.append(f'<span class="diff-add"><span class="diff-sign">+</span>{line[1:]}</span>')
        elif line.startswith('-'):
            styled.append(f'<span class="diff-del"><span class="diff-sign">-</span>{line[1:]}</span>')
        else:
            styled.append(f'<span class="diff-plain"><span class="diff-sign"> </span>{line}</span>')
    
    return styled


def generate_html(files, raw_diff):
    """Generate HTML from parsed diff data."""
    # Read template
    template_path = Path(__file__).parent.parent / 'templates' / 'git-diff.html'
    with open(template_path, 'r') as f:
        template = f.read()
    
    # Calculate stats
    total_added = sum(f['additions'] for f in files)
    total_removed = sum(f['deletions'] for f in files)
    
    # Generate file sections
    file_sections = []
    for idx, f in enumerate(files):
        styled_lines = style_diff_lines(f['diff'])
        diff_html = '\n'.join(styled_lines)
        
        file_section = f'''<div class="file-group">
  <div class="file-header" onclick="toggleFile('file-{idx}')">
    <h2>{f['name']}</h2>
    <span class="badge">+{f['additions']} -{f['deletions']}</span>
  </div>
  <div class="file-diff open" id="file-{idx}">
    <pre>{diff_html}</pre>
  </div>
</div>'''
        file_sections.append(file_section)
    
    # Fill template
    html = template.replace('{{GENERATED_AT}}', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    html = html.replace('{{FILE_COUNT}}', str(len(files)))
    html = html.replace('{{LINES_ADDED}}', str(total_added))
    html = html.replace('{{LINES_REMOVED}}', str(total_removed))
    html = html.replace('{{FILE_SECTIONS}}', '\n'.join(file_sections))
    html = html.replace('{{RAW_DIFF}}', raw_diff.replace('`', '\\`'))
    
    return html


def main():
    """Main entry point."""
    if len(sys.argv) > 1:
        # Read from file argument
        input_file = sys.argv[1]
        with open(input_file, 'r') as f:
            raw_diff = f.read()
    else:
        # Get from git diff
        raw_diff = get_git_diff()
    
    if not raw_diff:
        print("No diff found.")
        sys.exit(1)
    
    # Parse and generate
    files = parse_diff(raw_diff)
    html = generate_html(files, raw_diff)
    
    # Output
    output_file = '/tmp/git-diff.html'
    with open(output_file, 'w') as f:
        f.write(html)
    
    print(f"✓ Generated: {output_file}")
    print(f"✓ Files changed: {len(files)}")
    print(f"✓ Lines added: {sum(f['additions'] for f in files)}")
    print(f"✓ Lines removed: {sum(f['deletions'] for f in files)}")
    print(f"\nServe with: cd /tmp && python3 -m http.server 8899")
    print(f"Open: http://aya.crayfish-monitor.ts.net:8899/git-diff.html")


if __name__ == '__main__':
    main()
