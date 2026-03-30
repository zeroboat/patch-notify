document.addEventListener('DOMContentLoaded', async function() {
  initSimpleDatePicker("#patchDate");

  activeEditors = {};
  const switches = document.querySelectorAll('.section-switch');

  switches.forEach(sw => {
    sw.addEventListener('change', async function () {
      const section = this.getAttribute('data-section');
      const wrapper = document.getElementById(`wrapper-${section}`);
      // 모달 내 textarea ID 매칭
      const editorId = `#editor-${section === 'new' ? 'features' : section === 'improve' ? 'improvements' : section === 'bug' ? 'bugfixes' : section === 'note' ? 'remarks' : 'internals'}`;

      if (this.checked) {
        wrapper.style.display = 'block';
        // 에디터가 없으면 초기화 (initCKEditor 유틸 활용)
        if (!activeEditors[section]) {
          activeEditors[section] = await initCKEditor(editorId);
        }
      } else {
        wrapper.style.display = 'none';
      }
    });
  });
});