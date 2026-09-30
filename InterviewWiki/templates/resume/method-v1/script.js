(() => {
  const pages = Array.from(document.querySelectorAll(".resume-page"));
  const buttons = Array.from(document.querySelectorAll(".lang-toggle button[data-lang]"));
  const status = document.getElementById("language-status");

  function setActiveLanguage(language) {
    const selected = language === "ja" ? "ja" : "en";
    pages.forEach((page) => page.classList.toggle("active", page.dataset.language === selected));
    buttons.forEach((button) => {
      const active = button.dataset.lang === selected;
      button.classList.toggle("active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    document.documentElement.lang = selected;
    if (status) status.textContent = selected === "ja" ? "日本語の履歴書を表示中" : "English resume displayed";
  }

  buttons.forEach((button) => button.addEventListener("click", () => setActiveLanguage(button.dataset.lang)));
  const requested = new URLSearchParams(window.location.search).get("lang");
  setActiveLanguage(requested === "ja" ? "ja" : "en");
})();
