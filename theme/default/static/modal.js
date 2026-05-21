/* ===== Card Modal System ===== */
(function() {
    const modal = document.getElementById('card-modal');
    const modalBody = document.getElementById('modal-body');
    const modalClose = document.getElementById('modal-close');
    const tiles = document.querySelectorAll('.card-tile');
    let activeTile = null;
    let activeNodes = [];

    function openModal(tile) {
        activeTile = tile;
        activeNodes = Array.from(tile.childNodes);
        activeNodes.forEach(function(node) {
            modalBody.appendChild(node);
        });
        tile.classList.add('card-tile-empty');
        modal.classList.add('active');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        modal.classList.remove('active');
        document.body.style.overflow = '';
        if (activeTile) {
            activeNodes.forEach(function(node) {
                activeTile.appendChild(node);
            });
            activeTile.classList.remove('card-tile-empty');
            activeTile = null;
            activeNodes = [];
        }
        setTimeout(function() {
            if (!activeTile) modalBody.innerHTML = '';
        }, 250);
    }

    tiles.forEach(function(tile) {
        tile.addEventListener('click', function(e) {
            if (window.matchMedia && window.matchMedia('(max-width: 768px)').matches) {
                return;
            }
            // Don't open modal if clicking on a link or button inside the card
            if (e.target.tagName === 'A' || e.target.tagName === 'BUTTON' || e.target.closest('a') || e.target.closest('button') || e.target.closest('select') || e.target.closest('input')) {
                return;
            }
            openModal(tile);
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
