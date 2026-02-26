/**
 * Patch Note Append Logic
 * - CKEditor 5 데이터 동기화 지원
 * - SweetAlert2 Toast 스타일 알림 (2초 후 자동 종료)
 * - 버튼 로딩 상태 표시
 */

// 1. SweetAlert2 토스트 설정을 위한 공통 Mixin 생성
const Toast = Swal.mixin({
    toast: true,
    position: 'top-end',
    showConfirmButton: false,
    timer: 2000,
    timerProgressBar: true,
    didOpen: (toast) => {
        toast.addEventListener('mouseenter', Swal.stopTimer)
        toast.addEventListener('mouseleave', Swal.resumeTimer)
    }
});

// 2. 일반 에러/경고용 Mixin (중앙 팝업)
const Alert = Swal.mixin({
    customClass: {
        confirmButton: 'btn btn-primary',
        cancelButton: 'btn btn-label-secondary'
    },
    buttonsStyling: false
});

document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('appendForm');
    const submitBtn = document.getElementById('btn-append-patch');

    if (form && submitBtn) {
        form.addEventListener('submit', async function (e) {
            e.preventDefault();


            if (window.activeEditors) {
                Object.values(window.activeEditors).forEach(editor => {
                    // 이 메서드가 실행되어야 <textarea name="...">에 값이 들어갑니다.
                    editor.updateSourceElement();
                });
            } else {
                console.log("non activeEditors")
            }

            // [B] 버튼 로딩 상태로 변경
            const originalBtnHtml = submitBtn.innerHTML;
            submitBtn.disabled = true;
            submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1" role="status"></span> 저장 중...';

            const formData = new FormData(form);
            console.log(formData)

            try {
                // [C] 데이터 전송
                const response = await fetch(form.action, {
                    method: 'POST',
                    headers: {
                        'X-CSRFToken': document.querySelector('[name=csrfmiddlewaretoken]').value
                    },
                    body: formData
                });

                const data = await response.json();

                if (response.ok) {
                    // [D] 성공 시: 우측 상단 토스트 알림 후 페이지 새로고침
                    Toast.fire({
                        icon: 'success',
                        title: '성공적으로 저장되었습니다.'
                    }).then(() => {
                        // 모달 닫기 (선택 사항)
                        const modal = bootstrap.Modal.getInstance(document.getElementById('patchAppendModal'));
                        if (modal) modal.hide();

                        location.reload();
                    });
                } else {
                    // [E] 서버 에러 발생 시: 중앙 경고창
                    Alert.fire({
                        icon: 'error',
                        title: '저장 실패',
                        text: data.error || '입력하신 내용을 다시 확인해주세요.'
                    });
                }
            } catch (err) {
                console.error('Submission Error:', err);
                Alert.fire({
                    icon: 'warning',
                    title: '네트워크 오류',
                    text: '서버와 연결할 수 없습니다.'
                });
            } finally {
                // [F] 버튼 상태 복구
                submitBtn.disabled = false;
                submitBtn.innerHTML = originalBtnHtml;
            }
        });
    }
});