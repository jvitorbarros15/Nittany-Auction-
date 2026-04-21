function startTimers() {
    document.querySelectorAll('[data-end]').forEach(function (el) {
        function tick() {
            var raw  = el.dataset.end.replace(' ', 'T');
            var end  = new Date(raw).getTime();
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

            el.classList.remove('timer-hot', 'hp-timer-hot', 'timer-ended');

            if (d > 0) {
                el.textContent = d + 'd ' + h + 'h left';
            } else if (h > 0) {
                el.textContent = h + 'h ' + m + 'm left';
                if (h < 3) el.classList.add('timer-hot', 'hp-timer-hot');
            } else {
                el.textContent = m + 'm ' + s + 's left';
                el.classList.add('timer-hot', 'hp-timer-hot');
            }

            setTimeout(tick, 1000);
        }
        tick();
    });
}

document.addEventListener('DOMContentLoaded', startTimers);
