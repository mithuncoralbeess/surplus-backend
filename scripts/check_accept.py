with open('AdminApp/templates/content_blog_form.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if 'blogImageFileInput' in line or 'accept=' in line:
        print(f"{i+1}: {line.strip()}")

