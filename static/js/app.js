// ProcureSphere 360 Client Application JS
document.addEventListener('DOMContentLoaded', function () {
    console.log('ProcureSphere 360 Interface Initialized.');

    // Auto-inject CSRF token into HTMX headers
    document.body.addEventListener('htmx:configRequest', function (evt) {
        const csrfToken = getCookie('csrftoken');
        if (csrfToken) {
            evt.detail.headers['X-CSRFToken'] = csrfToken;
        }
    });

    // Helper to extract cookies
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    // Determine intuitive loading label based on current button text/value
    function getLoadingLabel(btn) {
        if (btn.dataset.loadingText) {
            return btn.dataset.loadingText;
        }
        const text = (btn.textContent || btn.innerText || '').trim().toLowerCase();
        const val = (btn.value || '').trim().toLowerCase();

        if (text.includes('draft') || val.includes('draft')) {
            return 'Saving Draft...';
        }
        if (text.includes('approve') || val.includes('approved')) {
            return 'Approving...';
        }
        if (text.includes('reject') || val.includes('rejected')) {
            return 'Rejecting...';
        }
        if (text.includes('cancel')) {
            return 'Cancelling...';
        }
        if (text.includes('payment') || text.includes('process')) {
            return 'Processing Payment...';
        }
        if (text.includes('resolve')) {
            return 'Resolving...';
        }
        if (text.includes('save')) {
            return 'Saving...';
        }
        if (text.includes('submit')) {
            return 'Submitting...';
        }
        if (text.includes('delete')) {
            return 'Deleting...';
        }
        return 'Processing...';
    }

    // Set button into loading state
    window.setButtonLoading = function (btn, customText) {
        if (!btn || btn.classList.contains('btn-loading')) return;
        btn.dataset.originalHtml = btn.innerHTML;
        btn.dataset.originalDisabled = btn.disabled;
        btn.classList.add('btn-loading');
        btn.disabled = true;

        const label = customText || getLoadingLabel(btn);
        btn.innerHTML = `<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>${label}`;
    };

    // Restore button from loading state
    window.resetButtonLoading = function (btn) {
        if (!btn || !btn.dataset.originalHtml) return;
        btn.innerHTML = btn.dataset.originalHtml;
        btn.disabled = btn.dataset.originalDisabled === 'true';
        btn.classList.remove('btn-loading');
        delete btn.dataset.originalHtml;
    };

    // Track clicked submit button on form and block rapid double-clicks
    document.addEventListener('click', function (e) {
        const btn = e.target.closest('button[type="submit"], input[type="submit"]');
        if (btn && btn.form) {
            if (btn.form.dataset.submitting === 'true' || btn.classList.contains('btn-loading') || btn.disabled) {
                e.preventDefault();
                e.stopImmediatePropagation();
                return false;
            }
            btn.form._ps360_clickedSubmitBtn = btn;
        }
    }, true);

    // Global Form Double-Submit Protection & Loading State
    document.addEventListener('submit', function (e) {
        const form = e.target;
        if (!form || form.tagName !== 'FORM') return;

        // Skip forms marked to ignore auto-loading (e.g. instant download links or search filters)
        if (form.dataset.noLoading === 'true' || form.getAttribute('method') === 'GET') {
            return;
        }

        // 1. Prevent duplicate submission if already processing
        if (form.dataset.submitting === 'true') {
            e.preventDefault();
            e.stopImmediatePropagation();
            return false;
        }

        // 2. Check HTML5 form validity; if invalid, browser stops submission and we shouldn't lock
        if (typeof form.checkValidity === 'function' && !form.checkValidity()) {
            return;
        }

        // 3. Mark form as submitting
        form.dataset.submitting = 'true';

        // 4. Identify clicked button
        const clickedBtn = form._ps360_clickedSubmitBtn;
        const submitButtons = form.querySelectorAll('button[type="submit"], input[type="submit"]');

        // Preserve name & value of clicked button via hidden input so disabling doesn't strip it
        if (clickedBtn && clickedBtn.name && clickedBtn.value) {
            const existingHidden = form.querySelector(`input[type="hidden"][data-dynamic-param="${clickedBtn.name}"]`);
            if (!existingHidden) {
                const hiddenInput = document.createElement('input');
                hiddenInput.type = 'hidden';
                hiddenInput.name = clickedBtn.name;
                hiddenInput.value = clickedBtn.value;
                hiddenInput.setAttribute('data-dynamic-param', clickedBtn.name);
                form.appendChild(hiddenInput);
            }
        }

        // Put clicked button into loading state and disable all submit buttons on this form
        if (clickedBtn) {
            window.setButtonLoading(clickedBtn);
        }

        submitButtons.forEach(function (btn) {
            if (btn !== clickedBtn) {
                btn.disabled = true;
                btn.classList.add('btn-loading');
            }
        });
    }, false);

    // Restore buttons on page show (e.g. back/forward navigation or browser cache)
    window.addEventListener('pageshow', function (event) {
        document.querySelectorAll('form[data-submitting="true"]').forEach(function (form) {
            delete form.dataset.submitting;
            const buttons = form.querySelectorAll('.btn-loading');
            buttons.forEach(function (btn) {
                window.resetButtonLoading(btn);
            });
        });
    });
});
