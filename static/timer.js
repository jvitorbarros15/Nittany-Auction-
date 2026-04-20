function startTimers() {
    document.querySelectorAll('[data-end]').forEach(function (el) {
        function tick() {
            var end  = new Date(el.dataset.end.replace(' ', 'T')).getTime();
            var diff = end - Date.now();

            if (isNaN(end) || diff <= 0) {
                el.textContent = 'Auction ended';
                el.classList.remove('hp-timer-hot', 'timer-hot');
                el.classList.add('timer-ended');
                return;
            }

            var d = Math.floor(diff / 86400000);
            var h = Math.floor((diff % 86400000) / 3600000);
            var m = Math.floor((diff % 3600000)  / 60000);
            var s = Math.floor((diff % 60000)    / 1000);

            if (d > 0) {
                el.textContent = d + 'd ' + h + 'h left';
            } else if (h > 0) {
                el.textContent = h + 'h ' + m + 'm left';
                if (h < 3) el.classList.add('hp-timer-hot', 'timer-hot');
            } else {
                el.textContent = m + 'm ' + s + 's left';
                el.classList.add('hp-timer-hot', 'timer-hot');
            }

            setTimeout(tick, 1000);
        }
        tick();
    });
}

document.addEventListener('DOMContentLoaded', startTimers);
