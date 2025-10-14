document.addEventListener('DOMContentLoaded', function() {
    // Initialize AOS animations
    AOS.init({
        duration: 800,
        once: true,
        offset: 100
    });

    // Add smooth transitions for molecule editor
    const editor = document.querySelector('.jsme-editor');
    if (editor) {
        editor.addEventListener('mouseover', () => {
            editor.style.transform = 'scale(1.02)';
        });
        editor.addEventListener('mouseout', () => {
            editor.style.transform = 'scale(1)';
        });
    }

    // Add loading animation to predict button
    const predictButton = document.querySelector('#predict-btn');
    if (predictButton) {
        predictButton.addEventListener('click', () => {
            predictButton.innerHTML = `
                <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                Processing...
            `;
            predictButton.disabled = true;
        });
    }

    // Smooth scroll for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(anchor => {
        anchor.addEventListener('click', function (e) {
            e.preventDefault();
            document.querySelector(this.getAttribute('href')).scrollIntoView({
                behavior: 'smooth'
            });
        });
    });
});