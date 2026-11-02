with open('AdminApp/templates/content_blog_form.html', 'r', encoding='utf-8') as f:
    lines = f.readlines()

for i in range(435, min(len(lines), 480)):
    print(f"{i+1}: {lines[i]}", end="")

