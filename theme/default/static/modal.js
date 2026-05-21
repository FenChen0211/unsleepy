/* ===== Card Modal System ===== */
(function() {
    const modal = document.getElementById('card-modal');
    const modalBody = document.getElementById('modal-body');
    const modalClose = document.getElementById('modal-close');
    const tiles = document.querySelectorAll('.card-tile');

    function openModal(cardName, htmlContent) {
        modalBody.innerHTML = htmlContent;
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
        setTimeout(function() {
            modalBody.innerHTML = '';
        }, 250);
    }

    tiles.forEach(function(tile) {
        tile.addEventListener('click', function(e) {
            // Don't open modal if clicking on a link or button inside the card
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.closest('a') || e.target.closest('button')) {
                return;
            }
            const name = tile.dataset.card;
            const content = tile.innerHTML;
            openModal(name, content);
        });
    });

    modalClose.addEventListener('click', closeModal);

    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            closeModal();
        }
    });

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && modal.classList.contains('active')) {
            closeModal();
        }
    });
})();
