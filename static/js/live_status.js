/**
 * Live Status Tracking Script for IUT Appointment System
 */

class LiveStatusTracker {
    constructor(appointmentId, updateInterval = 5000) {
        this.appointmentId = appointmentId;
        this.updateInterval = updateInterval;
        this.statusElement = document.getElementById(`status-${appointmentId}`);
        this.timelineElement = document.getElementById(`timeline-${appointmentId}`);
        this.currentStatus = null;
        this.init();
    }

    init() {
        if (!this.statusElement) {
            console.warn(`Status element not found for appointment ${this.appointmentId}`);
            return;
        }

        // Initial load
        this.updateStatus();

        // Set up polling
        this.pollInterval = setInterval(() => this.updateStatus(), this.updateInterval);
    }

    updateStatus() {
        fetch(`/api/appointments/${this.appointmentId}/status`)
            .then(response => response.json())
            .then(data => {
                if (data.status !== this.currentStatus) {
                    this.currentStatus = data.status;
                    this.renderStatus(data);
                    this.showNotification(data);
                }
            })
            .catch(error => console.error('Error fetching status:', error));
    }

    renderStatus(data) {
        const statusBadge = this.getStatusBadge(data.status);
        
        this.statusElement.innerHTML = `
            <span class="badge ${statusBadge.class}">
                ${statusBadge.icon} ${data.status}
            </span>
        `;

        // Update timeline if available
        if (this.timelineElement && data.timeline) {
            this.updateTimeline(data.timeline);
        }

        // Update estimated wait time if available
        if (data.estimated_wait_time) {
            this.updateWaitTime(data.estimated_wait_time);
        }
    }

    getStatusBadge(status) {
        const badges = {
            'Pending': { class: 'bg-secondary', icon: '⏱️' },
            'Approved': { class: 'bg-info', icon: '✓' },
            'Student Arrived': { class: 'bg-warning', icon: '👤' },
            'In Progress': { class: 'bg-primary', icon: '⟳' },
            'Completed': { class: 'bg-success', icon: '✓✓' },
            'Cancelled': { class: 'bg-danger', icon: '✕' }
        };
        return badges[status] || { class: 'bg-secondary', icon: '?' };
    }

    updateTimeline(timelineEvents) {
        if (!this.timelineElement) return;

        let html = '<div class="timeline-events">';
        
        timelineEvents.forEach(event => {
            const badge = this.getStatusBadge(event.status);
            html += `
                <div class="timeline-event">
                    <span class="badge ${badge.class}">${event.status}</span>
                    <span class="event-time">${this.formatTime(event.created_at)}</span>
                    ${event.note ? `<span class="event-note">${event.note}</span>` : ''}
                </div>
            `;
        });

        html += '</div>';
        this.timelineElement.innerHTML = html;
    }

    updateWaitTime(waitTime) {
        const waitElement = document.getElementById(`wait-time-${this.appointmentId}`);
        if (!waitElement) return;

        let message = '';
        if (waitTime === 0) {
            message = 'Your turn is next!';
        } else if (waitTime < 60) {
            message = `Estimated wait: ${waitTime} minutes`;
        } else {
            const hours = Math.floor(waitTime / 60);
            const minutes = waitTime % 60;
            message = `Estimated wait: ${hours}h ${minutes}m`;
        }

        waitElement.innerHTML = `<small class="text-muted">${message}</small>`;
    }

    showNotification(data) {
        // Show browser notification if permitted
        if ('Notification' in window && Notification.permission === 'granted') {
            new Notification('Appointment Status Update', {
                body: `Your appointment status is now: ${data.status}`,
                icon: '/static/iut_logo.png'
            });
        }

        // Show toast notification
        this.showToast(`Status updated to: ${data.status}`);
    }

    showToast(message) {
        const toast = document.createElement('div');
        toast.className = 'toast-notification';
        toast.textContent = message;
        toast.style.cssText = `
            position: fixed;
            bottom: 20px;
            right: 20px;
            background-color: #0056b3;
            color: white;
            padding: 15px 20px;
            border-radius: 5px;
            box-shadow: 0 2px 10px rgba(0, 0, 0, 0.2);
            z-index: 1000;
            animation: slideIn 0.3s ease-out;
        `;

        document.body.appendChild(toast);

        setTimeout(() => {
            toast.style.animation = 'slideOut 0.3s ease-out';
            setTimeout(() => toast.remove(), 300);
        }, 3000);
    }

    formatTime(dateString) {
        const date = new Date(dateString);
        return date.toLocaleString();
    }

    destroy() {
        if (this.pollInterval) {
            clearInterval(this.pollInterval);
        }
    }
}

// Request notification permission on page load
if ('Notification' in window && Notification.permission === 'default') {
    Notification.requestPermission();
}

// Add CSS animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }

    .timeline-events {
        margin-top: 10px;
    }

    .timeline-event {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 0;
        border-bottom: 1px solid #e0e0e0;
    }

    body.dark-mode .timeline-event {
        border-bottom-color: #444;
    }

    .event-time {
        font-size: 0.85rem;
        color: #666;
    }

    body.dark-mode .event-time {
        color: #999;
    }

    .event-note {
        font-size: 0.85rem;
        color: #555;
        font-style: italic;
    }

    body.dark-mode .event-note {
        color: #aaa;
    }
`;
document.head.appendChild(style);

// Export for use in other scripts
if (typeof module !== 'undefined' && module.exports) {
    module.exports = LiveStatusTracker;
}
