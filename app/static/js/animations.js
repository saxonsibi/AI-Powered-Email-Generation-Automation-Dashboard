// GSAP Animations for AI Email Dashboard

// Register GSAP plugins
if (typeof gsap !== 'undefined') {
    gsap.registerPlugin(ScrollTrigger);
}

// Initialize animations when DOM is ready
document.addEventListener('DOMContentLoaded', function() {
    if (typeof gsap === 'undefined') {
        console.warn('GSAP not loaded. Animations will not work.');
        return;
    }
    
    // Initialize page entrance animations
    initPageEntranceAnimations();
    
    // Initialize scroll animations
    initScrollAnimations();
    
    // Initialize hover animations
    initHoverAnimations();
    
    // Initialize loading animations
    initLoadingAnimations();
    
    // Initialize micro-interactions
    initMicroInteractions();
});

// Page entrance animations
function initPageEntranceAnimations() {
    // Animate sidebar
    const sidebar = document.getElementById('sidebar');
    if (sidebar) {
        gsap.from(sidebar, {
            duration: 0.8,
            x: -100,
            opacity: 0,
            ease: "power3.out"
        });
    }
    
    // Animate navbar
    const navbar = document.querySelector('header');
    if (navbar) {
        gsap.from(navbar, {
            duration: 0.8,
            y: -50,
            opacity: 0,
            ease: "power3.out",
            delay: 0.2
        });
    }
    
    // Animate main content
    const mainContent = document.querySelector('main');
    if (mainContent) {
        gsap.from(mainContent, {
            duration: 0.8,
            y: 30,
            opacity: 0,
            ease: "power3.out",
            delay: 0.4
        });
    }
    
    // Animate cards with stagger
    const cards = document.querySelectorAll('.glass, .neumorphic');
    if (cards.length > 0) {
        gsap.from(cards, {
            duration: 0.6,
            y: 20,
            opacity: 0,
            stagger: 0.1,
            ease: "power2.out",
            delay: 0.6
        });
    }
}

// Scroll animations
function initScrollAnimations() {
    // Animate elements as they come into view
    const animateElements = document.querySelectorAll('.animate-on-scroll');
    
    animateElements.forEach(element => {
        gsap.from(element, {
            scrollTrigger: {
                trigger: element,
                start: "top 80%",
                toggleActions: "play none none reverse"
            },
            duration: 0.8,
            y: 30,
            opacity: 0,
            ease: "power2.out"
        });
    });
    
    // Parallax effect for hero sections
    const heroSections = document.querySelectorAll('.hero-section');
    heroSections.forEach(section => {
        gsap.to(section.querySelector('.hero-content'), {
            scrollTrigger: {
                trigger: section,
                start: "top top",
                end: "bottom top",
                scrub: true
            },
            y: 100,
            ease: "none"
        });
    });
}

// Hover animations
function initHoverAnimations() {
    // Card hover effects
    const cards = document.querySelectorAll('.glass, .neumorphic');
    cards.forEach(card => {
        card.addEventListener('mouseenter', function() {
            gsap.to(this, {
                duration: 0.3,
                scale: 1.02,
                y: -5,
                ease: "power2.out"
            });
        });
        
        card.addEventListener('mouseleave', function() {
            gsap.to(this, {
                duration: 0.3,
                scale: 1,
                y: 0,
                ease: "power2.out"
            });
        });
    });
    
    // Button hover effects
    const buttons = document.querySelectorAll('button:not([disabled])');
    buttons.forEach(button => {
        button.addEventListener('mouseenter', function() {
            gsap.to(this, {
                duration: 0.2,
                scale: 1.05,
                ease: "power2.out"
            });
        });
        
        button.addEventListener('mouseleave', function() {
            gsap.to(this, {
                duration: 0.2,
                scale: 1,
                ease: "power2.out"
            });
        });
        
        // Button press effect
        button.addEventListener('mousedown', function() {
            gsap.to(this, {
                duration: 0.1,
                scale: 0.95,
                ease: "power2.out"
            });
        });
        
        button.addEventListener('mouseup', function() {
            gsap.to(this, {
                duration: 0.1,
                scale: 1.05,
                ease: "power2.out"
            });
        });
    });
}

// Loading animations
function initLoadingAnimations() {
    // Skeleton loading animation
    const skeletonElements = document.querySelectorAll('.skeleton');
    skeletonElements.forEach(element => {
        gsap.to(element, {
            duration: 1.5,
            backgroundPosition: "200% 0",
            ease: "none",
            repeat: -1
        });
    });
    
    // Spinner animation
    const spinners = document.querySelectorAll('.fa-spinner');
    spinners.forEach(spinner => {
        gsap.to(spinner, {
            duration: 1,
            rotation: 360,
            ease: "none",
            repeat: -1
        });
    });
}

// Micro-interactions
function initMicroInteractions() {
    // Checkbox animation
    const checkboxes = document.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            if (this.checked) {
                gsap.from(this, {
                    duration: 0.2,
                    scale: 1.2,
                    ease: "back.out(1.7)"
                });
            }
        });
    });
    
    // Radio button animation
    const radioButtons = document.querySelectorAll('input[type="radio"]');
    radioButtons.forEach(radio => {
        radio.addEventListener('change', function() {
            if (this.checked) {
                gsap.from(this, {
                    duration: 0.2,
                    scale: 1.2,
                    ease: "back.out(1.7)"
                });
            }
        });
    });
    
    // Input focus animation
    const inputs = document.querySelectorAll('input, textarea, select');
    inputs.forEach(input => {
        input.addEventListener('focus', function() {
            gsap.to(this, {
                duration: 0.2,
                boxShadow: "0 0 0 3px rgba(99, 102, 241, 0.3)",
                ease: "power2.out"
            });
        });
        
        input.addEventListener('blur', function() {
            gsap.to(this, {
                duration: 0.2,
                boxShadow: "0 0 0 0px rgba(99, 102, 241, 0)",
                ease: "power2.out"
            });
        });
    });
    
    // Star rating animation
    const starButtons = document.querySelectorAll('.star-btn');
    starButtons.forEach(button => {
        button.addEventListener('click', function() {
            const icon = this.querySelector('i');
            if (icon.classList.contains('text-yellow-500')) {
                gsap.to(icon, {
                    duration: 0.3,
                    scale: 0,
                    rotation: 180,
                    ease: "back.in(1.7)",
                    onComplete: function() {
                        icon.classList.remove('text-yellow-500');
                        gsap.set(icon, { scale: 1, rotation: 0 });
                    }
                });
            } else {
                icon.classList.add('text-yellow-500');
                gsap.from(icon, {
                    duration: 0.3,
                    scale: 0,
                    rotation: -180,
                    ease: "back.out(1.7)"
                });
            }
        });
    });
}

// Typewriter effect
function typewriter(element, text, speed = 50) {
    element.textContent = '';
    let i = 0;
    
    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }
    
    type();
}

// Counting animation
function countUp(element, target, duration = 1000) {
    const start = 0;
    const increment = target / (duration / 16);
    let current = start;
    
    function updateCount() {
        current += increment;
        if (current < target) {
            element.textContent = Math.floor(current);
            requestAnimationFrame(updateCount);
        } else {
            element.textContent = target;
        }
    }
    
    updateCount();
}

// Progress bar animation
function animateProgressBar(element, targetWidth, duration = 1000) {
    gsap.to(element, {
        duration: duration / 1000,
        width: targetWidth + '%',
        ease: "power2.out"
    });
}

// Notification badge animation
function animateNotificationBadge(element) {
    gsap.from(element, {
        duration: 0.5,
        scale: 0,
        ease: "back.out(1.7)"
    });
    
    // Pulse animation
    gsap.to(element, {
        duration: 2,
        scale: 1.1,
        repeat: -1,
        yoyo: true,
        ease: "power1.inOut"
    });
}

// Email list animations
function animateEmailList() {
    const emailItems = document.querySelectorAll('.email-item');
    
    gsap.from(emailItems, {
        duration: 0.5,
        x: -20,
        opacity: 0,
        stagger: 0.05,
        ease: "power2.out"
    });
}

// Modal animations
function animateModalIn(modal) {
    const modalContent = modal.querySelector('.modal-content, .bg-white');
    
    gsap.fromTo(modalContent, 
        {
            scale: 0.8,
            opacity: 0,
            rotation: 5
        },
        {
            duration: 0.3,
            scale: 1,
            opacity: 1,
            rotation: 0,
            ease: "back.out(1.7)"
        }
    );
}

function animateModalOut(modal, callback) {
    const modalContent = modal.querySelector('.modal-content, .bg-white');
    
    gsap.to(modalContent, {
        duration: 0.2,
        scale: 0.8,
        opacity: 0,
        rotation: -5,
        ease: "back.in(1.7)",
        onComplete: callback
    });
}

// Toast notification animations
function animateToastIn(toast) {
    gsap.from(toast, {
        duration: 0.3,
        x: 100,
        opacity: 0,
        ease: "back.out(1.7)"
    });
}

function animateToastOut(toast, callback) {
    gsap.to(toast, {
        duration: 0.2,
        x: 100,
        opacity: 0,
        ease: "back.in(1.7)",
        onComplete: callback
    });
}

// Export animation functions
window.Animations = {
    typewriter,
    countUp,
    animateProgressBar,
    animateNotificationBadge,
    animateEmailList,
    animateModalIn,
    animateModalOut,
    animateToastIn,
    animateToastOut
};