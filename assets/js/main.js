// JS opzionale: micro-interazioni non invasive
(function () {
  'use strict';
  document.addEventListener('DOMContentLoaded', function () {
    // Sincronizza stato pill (aggiunge classi utili al tema)
    var pill = document.querySelector('.pill');
    if (pill) {
      var state = (pill.getAttribute('data-state') || '').toUpperCase();
      pill.classList.toggle('is-on', state === 'ON');
      pill.classList.toggle('is-off', state === 'OFF');
    }
    // Hide landing extras se vuoti (degrado pulito)
    ['.landing__client', '.landing__upload', '.landing__help'].forEach(function (sel) {
      var el = document.querySelector(sel);
      if (el && !el.textContent.trim()) {
        el.style.display = 'none';
      }
    });
  });
})();
