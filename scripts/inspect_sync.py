with open('AdminApp/views.py', 'r', encoding='utf-8') as f:
    text = f.read()

idx = text.find('def _sync_blog_image_to_frontends')
if idx != -1:
    print(text[idx:idx+800])

