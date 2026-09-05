// Menú móvil (abrir/cerrar), sin dependencias externas
document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.getElementById("navToggle");
  const nav = document.getElementById("mainNav");
  if (!toggle || !nav) return;

  toggle.addEventListener("click", () => {
    const isOpen = nav.classList.toggle("is-open");
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  // Cerrar el menú al elegir una opción (útil en móvil)
  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
    });
  });

  // Cerrar con la tecla Escape
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && nav.classList.contains("is-open")) {
      nav.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
  });

  // Avisar si se seleccionan mas de 5 imagenes en un campo de multiples archivos
  document.querySelectorAll('input[type="file"][multiple]').forEach((input) => {
    input.addEventListener("change", () => {
      if (input.files.length > 5) {
        alert("Solo se permiten 5 imagenes maximo. Se subiran las primeras 5.");
      }
    });
  });
});
