// static/js/ckeditor.js

async function initCKEditor(selector) {
    try {
        const element = document.querySelector(selector);
        if (!element) return null;

        // Super-build에서는 CKEDITOR.ClassicEditor를 사용합니다.
        const editor = await CKEDITOR.ClassicEditor.create(element, {
            // 툴바는 사용자님 요청대로 비웁니다.
            toolbar: [],

            // 핵심: 코드 블록과 자동 포맷 플러그인을 로드합니다.
            plugins: [
                'Essentials', 'Paragraph', 'Bold', 'Link', 'Code', 'List', 'Autoformat'
            ],
            placeholder: '패치 내용을 작성해 주세요. \n ( Ctrl + B : Bold, - + Space : Bullet, ` 코드 ` : Inline Code)'
        });

        return editor;
    } catch (error) {
        console.error('에디터 로드 중 오류:', error);
        return null;
    }
}