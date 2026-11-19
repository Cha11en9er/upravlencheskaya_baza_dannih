// УБД — vanilla JS без внешних зависимостей.
// Модальные окна: ссылки с data-modal подгружают форму в <dialog> (прогрессивное улучшение:
// без JS всё открывается обычными страницами, POST всегда ведёт на полную страницу).

(function () {
  const dialog = document.getElementById("modal");
  const body = document.getElementById("modal-body");

  function openModal(url) {
    fetch(url + (url.includes("?") ? "&" : "?") + "partial=1")
      .then(r => r.text())
      .then(html => {
        const doc = new DOMParser().parseFromString(html, "text/html");
        const inner = doc.getElementById("modal-body");
        body.innerHTML = inner ? inner.innerHTML : html;
        dialog.showModal();
      })
      .catch(() => { window.location.href = url; });
  }

  document.addEventListener("click", function (e) {
    const link = e.target.closest("a[data-modal]");
    if (!link) return;
    e.preventDefault();
    openModal(link.getAttribute("data-modal"));
  });

  // закрытие по крестику на диалоге и по Esc (нативно) + клик по подложке
  document.addEventListener("click", function (e) {
    if (e.target.closest("[data-close-modal]")) {
      dialog.close();
    }
  });

  // Фильтр объектов по проекту: у <select name=object_id> опции с data-project
  document.addEventListener("change", function (e) {
    if (e.target.matches("select[name=project_id]")) {
      const pid = e.target.value;
      const objSelect = document.querySelector("select[name=object_id]");
      if (!objSelect) return;
      for (const opt of objSelect.options) {
        const belongs = !opt.dataset.project || !pid || opt.dataset.project === pid;
        opt.hidden = !belongs;
      }
    }
  });
})();
