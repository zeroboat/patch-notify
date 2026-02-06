function initSimpleDatePicker(selector) {
    return flatpickr(selector, {
        locale: "ko",
        dateFormat: "Y-m-d",
        defaultDate: "today",
        // Sneat 테마 컬러와 어울리도록 커스텀 가능
    });
}