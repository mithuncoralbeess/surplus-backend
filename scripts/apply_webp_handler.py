why thiwith open('AdminApp/templates/content_blog_form.html', 'r', encoding='utf-8') as f:
    content = f.read()

target = """    // Initialize Quill Rich Text Editor
    const quill = new Quill('#quillEditorContainer', {
        theme: 'snow',
        placeholder: 'Write your rich blog post article content here...',
        modules: {
            toolbar: '#quillToolbar'
        }
    });"""

replacement = """    // Upload image to server and embed URL into Quill (Supports WebP, PNG, JPEG, GIF, SVG)
    async function uploadAndInsertImage(file) {
        if (!file) return;

        if (!file.type.startsWith('image/')) {
            alert('Please select a valid image file (WebP, PNG, JPG, GIF, SVG).');
            return;
        }

        const formData = new FormData();
        formData.append('image', file);

        const range = quill.getSelection(true) || { index: quill.getLength(), length: 0 };
        const cursorIndex = range.index;

        quill.insertText(cursorIndex, '⏳ Uploading image...', { 'italic': true, 'color': '#64748b' });

        try {
            const res = await fetch('/admin/api/content/blogs/upload-image/', {
                method: 'POST',
                headers: {
                    'X-CSRFToken': getCsrfToken()
                },
                body: formData
            });

            const data = await res.json();
            quill.deleteText(cursorIndex, '⏳ Uploading image...'.length);

            if (res.ok && data.success && data.url) {
                quill.insertEmbed(cursorIndex, 'image', data.url);
                quill.setSelection(cursorIndex + 1);
            } else {
                alert(data.message || 'Failed to upload image.');
            }
        } catch (err) {
            quill.deleteText(cursorIndex, '⏳ Uploading image...'.length);
            alert('Server error occurred while uploading image.');
        }
    }

    // Custom toolbar image button handler allowing WebP, PNG, JPG, GIF, SVG
    function selectWYSIWYGImage() {
        const input = document.createElement('input');
        input.setAttribute('type', 'file');
        input.setAttribute('accept', 'image/webp, image/png, image/jpeg, image/jpg, image/gif, image/svg+xml');
        input.click();

        input.onchange = () => {
            if (input.files && input.files[0]) {
                uploadAndInsertImage(input.files[0]);
            }
        };
    }

    // Initialize Quill Rich Text Editor with Custom WebP-Enabled Image Handler
    const quill = new Quill('#quillEditorContainer', {
        theme: 'snow',
        placeholder: 'Write your rich blog post article content here...',
        modules: {
            toolbar: {
                container: '#quillToolbar',
                handlers: {
                    image: selectWYSIWYGImage
                }
            }
        }
    });

    // Support Drag & Drop of WebP / image files directly into Quill editor
    quill.root.addEventListener('drop', (e) => {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            const file = e.dataTransfer.files[0];
            if (file && file.type && file.type.startsWith('image/')) {
                e.preventDefault();
                uploadAndInsertImage(file);
            }
        }
    });

    // Support Pasting of WebP / image files from clipboard
    quill.root.addEventListener('paste', (e) => {
        if (e.clipboardData && e.clipboardData.files && e.clipboardData.files.length > 0) {
            const file = e.clipboardData.files[0];
            if (file && file.type && file.type.startsWith('image/')) {
                e.preventDefault();
                uploadAndInsertImage(file);
            }
        }
    });"""

if target in content:
    content = content.replace(target, replacement, 1)
    with open('AdminApp/templates/content_blog_form.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Replaced successfully")
else:
    print("Target not found!")

